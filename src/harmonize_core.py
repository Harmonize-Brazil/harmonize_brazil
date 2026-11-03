"""
harmonize_core.py
Núcleo do plugin Harmonize Brazil Catalog: catálogo STAC e download.
Não depende da interface; pode ser testado no Console Python do QGIS.
"""
import json
import os
import re
import urllib.parse

from qgis.core import (Qgis, QgsBlockingNetworkRequest, QgsColorRampShader,
                       QgsDateTimeRange, QgsFeedback, QgsNetworkAccessManager, QgsSettings,
                       QgsGraduatedSymbolRenderer, QgsMessageLog, QgsProject,
                       QgsRasterBandStats, QgsRasterLayer, QgsRasterShader,
                       QgsRendererRange, QgsSingleBandPseudoColorRenderer, QgsStyle,
                       QgsSymbol, QgsVectorLayer, QgsCategorizedSymbolRenderer,
                       QgsRendererCategory)
from qgis.PyQt.QtCore import (QCoreApplication, QDateTime, QEventLoop, QThread, QTimer, Qt, QUrl,
                              QT_TRANSLATE_NOOP)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

# Endereço do catálogo STAC. O valor efetivo vem de load_config(), nesta ordem:
# 1) data/harmonize_config.json no GitHub (permite trocar a URL sem nova versão do plugin);
# 2) última cópia válida baixada (guardada nas configurações do QGIS);
# 3) data/harmonize_config.json distribuído com o plugin;
# 4) DEFAULT_STAC_URL.
DEFAULT_STAC_URL = "https://geolab.inpe.br/bdc/harmonize/stac/v1"
CONFIG_URL = ("https://raw.githubusercontent.com/Harmonize-Brazil/harmonize_brazil/"
              "main/src/data/harmonize_config.json")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "data", "harmonize_config.json")
CONFIG_SETTINGS_KEY = "harmonize_brazil/remote_config"
CONFIG_TIMEOUT_MS = 5000              # o GitHub fora do ar não pode travar a abertura do plugin
STAC_URL = DEFAULT_STAC_URL
CONFIG_SOURCE = "default"
USER_AGENT = "QGIS-HarmonizeBrazil/0.1"
LOG_TAG = "Harmonize Brazil"
REGIONS = {"ne": "NE", "no": "NO"}
SIZE_WARNING_MB = 50                  # acima disso, o usuário confirma o download
MAX_PARALLEL_HEAD = 8                 # requisições HEAD simultâneas na verificação de tamanho
MAX_RETRIES = 8                       # retomadas automáticas após queda de conexão

# Estilos de clima (mesmas classes e cores do GeoServer), em styles/*.txt
STYLES_DIR = os.path.join(os.path.dirname(__file__), "styles")
CLIMATE_OPACITY = 0.75                # opacidade do preenchimento: 0 = transparente, 1 = opaco
CLIMATE_STROKE_COLOR = (0, 0, 0, 255) # contorno dos municípios: R, G, B, alfa (255 = sem transparência)
CLIMATE_STROKE_WIDTH = 0.1            # espessura do contorno, em mm
PALETTE_NODATA = -9999                # valor sem dado: não é desenhado (fica transparente)
# Estilo dos dados de saúde (mesmas cores dos SLD do GeoServer), sobre a coluna VALUE_FIELD
VALUE_FIELD = "value"                 # coluna com o valor do indicador
HEALTH_OPACITY = 0.7                  # fill-opacity dos SLD de saúde
ALERT_LEVELS = [                      # nível de alerta (alert_level.sld): valor, cor, rótulo
    (1, "#008000", QT_TRANSLATE_NOOP("@default", "Low risk")),
    (2, "#ffff00", QT_TRANSLATE_NOOP("@default", "Moderate risk")),
    (3, "#ffa500", QT_TRANSLATE_NOOP("@default", "High risk")),
    (4, "#ff0000", QT_TRANSLATE_NOOP("@default", "Very high risk")),
]
HEALTH_COLORS = ["#d9d9d9", "#f1b066", "#e56d46", "#c5444d", "#922042"]   # health.sld, 5 classes

CLIMATE_PALETTES = [                  # (prefixo do id da coleção, trecho do id, arquivo)
    ("anomaly_", "_month_", "color_anomaly_month.txt"),
    ("anomaly_", "", "color_anomaly_epiweek.txt"),
    ("precip_", "", "color_precipitation.txt"),
    ("humidity_", "", "color_relative_humidity.txt"),
    ("temp_", "", "color_temperature.txt"),
]
DRONE_WORKSPACE = "harmonize_drone"   # prefixo do layerName das coleções de drone
DRONE_KEYWORDS = ("drone", "uav", "uas", "rpa", "rpas")         # palavras-chave de drone
DRONE_NAME = re.compile(r"mavic|phantom|drone|uav", re.IGNORECASE)  # modelos/termos no id ou título

# Formatos de download por tipo de coleção (chave interna -> rótulo)
VECTOR_FORMATS = ["geojson", "shapefile"]
RASTER_FORMATS = ["geotiff"]
ASSET_PREFIX = "asset:"               # formato "asset:<chave>": uma banda específica do cubo
DATACUBE_KEYWORDS = ("data cube", "datacube")   # palavras-chave que identificam cubos de dados
TIFF_EXTS = (".tif", ".tiff")
ALLOWED_SCHEMES = ("https", "http")   # nenhum outro esquema (file:, ftp:...) é aceito

try:
    _NO_ERROR = QgsBlockingNetworkRequest.ErrorCode.NoError
except AttributeError:
    _NO_ERROR = QgsBlockingNetworkRequest.NoError


def tr(message):
    """Tradução no contexto do núcleo (veja i18n/HarmonizeBrazil_pt_BR.ts)."""
    return QCoreApplication.translate("@default", message)


def log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, LOG_TAG, level)


# ----------------------------------------------------------------- HTTP
# Todas as requisições passam por QgsBlockingNetworkRequest, que usa o
# gerenciador de rede do QGIS (proxy, SSL e autenticação configurados no QGIS).


class HttpError(RuntimeError):
    """Erro de rede ou resposta HTTP de erro."""


def _check_url(url):
    """Aceita apenas http(s); bloqueia file: e esquemas personalizados."""
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(tr("URL scheme not allowed: {0}").format(url))


def _request(url, method="get", accept=None, progress=None, is_canceled=None):
    """Executa GET ou HEAD e retorna o QgsNetworkReplyContent."""
    _check_url(url)
    req = QNetworkRequest(QUrl(url))
    req.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
    if accept:
        req.setRawHeader(b"Accept", accept.encode("utf-8"))

    blocking = QgsBlockingNetworkRequest()
    feedback = QgsFeedback()
    if progress or is_canceled:
        def on_progress(received, total):
            if is_canceled and is_canceled():
                feedback.cancel()
            if progress and total > 0:
                progress(received / total)
        # DirectConnection: o sinal é emitido na thread da requisição; sem isso
        # ele só seria entregue após o fim do download (sem progresso nem cancelamento)
        blocking.downloadProgress.connect(on_progress, Qt.ConnectionType.DirectConnection)

    if is_canceled and is_canceled():
        raise RuntimeError(tr("Canceled by the user."))

    if method == "head":
        err = blocking.head(req, True, feedback)
    else:
        err = blocking.get(req, True, feedback)

    if feedback.isCanceled():
        raise RuntimeError(tr("Canceled by the user."))
    if err != _NO_ERROR:
        raise HttpError(blocking.errorMessage())
    return blocking.reply()


def _get_json(url):
    reply = _request(url, accept="application/json")
    return json.loads(bytes(reply.content()).decode("utf-8"))


# ----------------------------------------------------------------- configuração remota
def _fetch_text(url, timeout_ms):
    """GET curto, sem cache, com limite de tempo próprio. Retorna o texto da resposta."""
    _check_url(url)
    req = QNetworkRequest(QUrl(url))
    req.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
    req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                     QNetworkRequest.CacheLoadControl.AlwaysNetwork)
    reply = QgsNetworkAccessManager.instance().get(req)
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(reply.abort)
    reply.finished.connect(loop.quit)
    timer.start(timeout_ms)
    loop.exec()
    timer.stop()
    try:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            raise HttpError(reply.errorString())
        return bytes(reply.readAll()).decode("utf-8")
    finally:
        reply.deleteLater()


def _parse_config(text):
    """Converte o JSON e valida o campo stac_url; erro se for inválido."""
    cfg = json.loads(text)
    url = cfg.get("stac_url") if isinstance(cfg, dict) else None
    if not isinstance(url, str) or not url.strip():
        raise ValueError("stac_url ausente")
    _check_url(url.strip())
    return cfg


def load_config():
    """Define STAC_URL a partir do GitHub, com recuo para a cópia salva e para o arquivo local."""
    global STAC_URL, CONFIG_SOURCE
    settings = QgsSettings()
    cfg, source = None, None
    try:
        text = _fetch_text(CONFIG_URL, CONFIG_TIMEOUT_MS)
        cfg, source = _parse_config(text), "GitHub"
        settings.setValue(CONFIG_SETTINGS_KEY, text)          # última cópia válida
    except Exception as exc:  # noqa: BLE001
        log(tr("Could not read the configuration from GitHub ({0}). Using the saved copy.").format(exc),
            Qgis.Warning)
    if cfg is None:
        try:
            cfg, source = _parse_config(settings.value(CONFIG_SETTINGS_KEY, "") or ""), "cache"
        except Exception:  # noqa: BLE001
            cfg = None
    if cfg is None:
        try:
            with open(CONFIG_FILE, encoding="utf-8") as fh:
                cfg, source = _parse_config(fh.read()), "plugin"
        except Exception:  # noqa: BLE001
            cfg = None
    STAC_URL = cfg["stac_url"].strip().rstrip("/") if cfg else DEFAULT_STAC_URL
    CONFIG_SOURCE = source or "default"
    log(tr("STAC catalog: {0} (source: {1})").format(STAC_URL, CONFIG_SOURCE))
    return STAC_URL


# ----------------------------------------------------------------- STAC
def is_drone(c, layer_name, keywords):
    """Coleção de drone: qualquer um destes sinais basta (nem todas têm WMS publicado)."""
    if layer_name.startswith(DRONE_WORKSPACE):
        return True
    if (c.get("bdc:type") or "").lower() == "drone":
        return True
    if any(k.strip().lower() in DRONE_KEYWORDS for k in keywords):
        return True
    return bool(DRONE_NAME.search("{0} {1}".format(c.get("id", ""), c.get("title", ""))))


def raster_asset_keys(item_assets):
    """Chaves de item_assets que são rasters de dados (bandas do cubo), sem miniaturas."""
    keys = []
    for key, a in item_assets.items():
        roles = a.get("roles") or []
        mtype = (a.get("type") or "").lower()
        if key == "thumbnail" or "thumbnail" in roles:
            continue
        if "tiff" in mtype or "data" in roles:
            keys.append(key)
    return keys


def formats_for(col):
    """Formatos de download oferecidos para a coleção."""
    if col.get("type") == "datacube" and col.get("band_assets"):
        return [ASSET_PREFIX + k for k in col["band_assets"]]
    if col.get("type") in ("drone", "datacube"):
        return list(RASTER_FORMATS)
    return list(VECTOR_FORMATS)


def is_raster_format(fmt):
    return fmt in RASTER_FORMATS or fmt.startswith(ASSET_PREFIX)


def list_collections():
    """Lista resumida das coleções, pronta para popular a interface.
    Campos ausentes ou nulos no STAC (null) viram valores vazios."""
    data = _get_json(f"{STAC_URL}/collections")
    out = []
    for c in data.get("collections") or []:
        cid = c.get("id")
        if not cid:
            continue
        extent = c.get("extent") or {}
        intervals = (extent.get("temporal") or {}).get("interval") or [[None, None]]
        bboxes = (extent.get("spatial") or {}).get("bbox") or [None]
        parts = cid.lower().split("_")
        wms = ((c.get("bdc:metadata") or {}).get("wms") or {})
        layer_name = (wms.get("layerName") or "").lower()
        keywords = [k for k in (c.get("keywords") or []) if k]
        if is_drone(c, layer_name, keywords):
            ctype = "drone"
        elif any(k.strip().lower() in DATACUBE_KEYWORDS for k in keywords):
            ctype = "datacube"
        else:
            ctype = c.get("bdc:type") or ""
        out.append({
            "id": cid,
            "title": c.get("title") or cid,
            "description": c.get("description") or "",
            "type": ctype,                               # climate | health | drone | datacube
            "region": next((REGIONS[p] for p in parts if p in REGIONS), ""),
            "keywords": keywords,
            "band_assets": raster_asset_keys(c.get("item_assets") or {}),
            "temporal": intervals[0] or [None, None],
            "bbox": bboxes[0],
        })
    out.sort(key=lambda d: (d["type"], d["region"], d["title"].lower()))
    return out


def list_items(collection_id, start=None, end=None, limit=100, is_canceled=None):
    """Itens da coleção, seguindo a paginação rel=next."""
    base = f"{STAC_URL}/collections/{collection_id}/items"
    params = {"limit": limit}
    if start and end:
        params["datetime"] = f"{start}T00:00:00Z/{end}T23:59:59Z"
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        first = _get_json(url)
    except HttpError:
        # servidor não aceita o filtro: busca tudo e filtra localmente depois
        log(tr("Server rejected the datetime filter; fetching all items."), Qgis.Warning)
        first = _get_json(f"{base}?limit={limit}")

    items, page = [], first
    while True:
        items.extend(page.get("features", []))
        nxt = next((link for link in page.get("links", []) if link.get("rel") == "next"), None)
        if not nxt or (is_canceled and is_canceled()):
            break
        page = _get_json(nxt["href"])
    items.sort(key=lambda f: f.get("properties", {}).get("datetime") or "")
    return items


# ----------------------------------------------------------------- download
def find_asset(item, fmt):
    """Retorna (chave, asset) do formato pedido ou (None, None).
    geojson/shapefile: chave direta. asset:<chave>: banda específica (cubos).
    geotiff: primeiro asset .tif/.tiff ou image/tiff que não seja miniatura."""
    assets = item.get("assets") or {}
    if fmt.startswith(ASSET_PREFIX):
        key = fmt[len(ASSET_PREFIX):]
        a = assets.get(key)
        return (key, a) if a else (None, None)
    if fmt != "geotiff":
        a = assets.get(fmt)
        return (fmt, a) if a else (None, None)
    for key, a in assets.items():
        href = (a.get("href") or "").lower().split("?")[0]
        mtype = (a.get("type") or "").lower()
        roles = a.get("roles") or []
        if "thumbnail" in roles or key == "thumbnail":
            continue
        if href.endswith(TIFF_EXTS) or "image/tiff" in mtype:
            return key, a
    return None, None


def asset_local_path(item, fmt, out_dir):
    """(url, caminho local) do asset no formato pedido."""
    _key, asset = find_asset(item, fmt)
    if not asset:
        raise KeyError(tr("Item {0} has no asset '{1}'.").format(item["id"], fmt))
    href = asset["href"]
    return href, os.path.join(out_dir, os.path.basename(urllib.parse.urlparse(href).path))


def asset_sizes(items, fmt, progress=None, is_canceled=None):
    """Tamanho em bytes de cada item (lista na mesma ordem; None se desconhecido).
    Usa file:size do STAC quando existe; senão faz requisições HEAD assíncronas,
    até MAX_PARALLEL_HEAD ao mesmo tempo, pelo gerenciador de rede do QGIS."""
    nam = QgsNetworkAccessManager.instance()
    results = {}
    queue = list(enumerate(items))
    active = {}
    loop = QEventLoop()
    state = {"done": False}

    def finish_if_idle():
        if not active and not queue:
            state["done"] = True
            loop.quit()

    def on_finished(reply):
        idx = active.pop(reply, None)
        if idx is None:
            return
        length = None
        if reply.error() == QNetworkReply.NetworkError.NoError:
            length = reply.header(QNetworkRequest.KnownHeaders.ContentLengthHeader)
        results[idx] = int(length) if length not in (None, "") else None
        reply.deleteLater()
        if progress:
            progress(len(results) / len(items))
        if is_canceled and is_canceled():
            queue.clear()
            for r in list(active):
                r.abort()
        start_next()

    def start_next():
        while queue and len(active) < MAX_PARALLEL_HEAD:
            idx, item = queue.pop(0)
            asset = find_asset(item, fmt)[1] or {}
            size = asset.get("file:size")
            if isinstance(size, (int, float)) and size > 0:
                results[idx] = int(size)
                continue
            href = asset.get("href") or ""
            try:
                _check_url(href)
            except ValueError:
                results[idx] = None
                continue
            req = QNetworkRequest(QUrl(href))
            req.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
            reply = nam.head(req)
            active[reply] = idx
            reply.finished.connect(lambda r=reply: on_finished(r))
        finish_if_idle()

    start_next()
    if not state["done"]:
        loop.exec()
    if is_canceled and is_canceled():
        raise RuntimeError(tr("Canceled by the user."))
    return [results.get(i) for i in range(len(items))]


def format_size(n_bytes):
    """Tamanho legível: 12.3 MB, 1.2 GB."""
    mb = n_bytes / 1024 ** 2
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.1f} MB"


def _stream_to_file(url, path, offset, progress=None, is_canceled=None):
    """Uma tentativa de GET gravando direto no disco a partir de 'offset'.
    Se offset > 0, pede só o restante (cabeçalho Range) e acrescenta ao arquivo.
    Retorna dict com 'error' (None se completou) e 'canceled'."""
    nam = QgsNetworkAccessManager.instance()
    req = QNetworkRequest(QUrl(url))
    req.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
    # sem cache: o cache de disco do QGIS não deve receber arquivos de vários GB
    req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                     QNetworkRequest.CacheLoadControl.AlwaysNetwork)
    req.setAttribute(QNetworkRequest.Attribute.CacheSaveControlAttribute, False)
    req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                     QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
    if offset:
        req.setRawHeader(b"Range", f"bytes={offset}-".encode("ascii"))

    state = {"error": None, "canceled": False, "base": None}
    fh = open(path, "ab" if offset else "wb")
    reply = nam.get(req)
    loop = QEventLoop()

    def check_mode():
        if state["base"] is None:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if offset and status == 206:
                state["base"] = offset           # servidor aceitou retomar
            else:
                state["base"] = 0                # resposta completa: recomeça do zero
                if offset:
                    fh.seek(0)
                    fh.truncate()

    def on_ready():
        if not reply.isOpen():
            return
        check_mode()
        data = reply.readAll()
        if data:
            fh.write(bytes(data))
        if is_canceled and is_canceled() and not state["canceled"]:
            state["canceled"] = True
            reply.abort()

    def on_progress(received, total):
        if progress and total > 0 and state["base"] is not None:
            progress((state["base"] + received) / (state["base"] + total))

    reply.readyRead.connect(on_ready)
    reply.downloadProgress.connect(on_progress)
    reply.finished.connect(loop.quit)
    loop.exec()
    if not state["canceled"]:
        on_ready()
    fh.close()

    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    if state["canceled"]:
        pass
    elif offset and status == 416:
        state["error"] = None                    # nada a retomar: arquivo já completo
    elif reply.error() != QNetworkReply.NetworkError.NoError:
        state["error"] = reply.errorString()
    elif status not in (200, 206):
        state["error"] = "HTTP {0}".format(status)
    reply.deleteLater()
    return state


def download_asset(item, fmt, out_dir, progress=None, is_canceled=None):
    """Baixa o asset no formato pedido (geojson | shapefile | geotiff). Usa cache local.
    Grava no disco à medida que os dados chegam e, se a conexão cair, retoma do
    ponto em que parou (até MAX_RETRIES vezes). O arquivo .part é mantido em caso
    de falha, para que uma nova tentativa continue de onde parou."""
    href, dest = asset_local_path(item, fmt, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(dest):
        return dest
    _check_url(href)

    name = os.path.basename(dest)
    tmp = dest + ".part"
    attempt = 0
    log(tr("Downloading {0}").format(name))
    while True:
        if is_canceled and is_canceled():
            raise RuntimeError(tr("Canceled by the user."))
        offset = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        result = _stream_to_file(href, tmp, offset, progress, is_canceled)
        if result["canceled"]:
            raise RuntimeError(tr("Canceled by the user."))
        if result["error"] is None:
            break
        attempt += 1
        done = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if attempt > MAX_RETRIES:
            raise HttpError(tr("Download of {0} failed after {1} attempts ({2} saved; run it again "
                               "to resume): {3}").format(name, attempt, format_size(done), result["error"]))
        log(tr("Connection interrupted while downloading {0} at {1} ({2}). Resuming, attempt {3} of {4}.")
            .format(name, format_size(done), result["error"], attempt, MAX_RETRIES), Qgis.Warning)
        for _ in range(min(2 ** attempt, 30) * 10):      # espera crescente, atenta ao cancelamento
            if is_canceled and is_canceled():
                raise RuntimeError(tr("Canceled by the user."))
            QThread.msleep(100)

    os.replace(tmp, dest)
    log(tr("Download completed: {0} ({1})").format(name, format_size(os.path.getsize(dest))))
    return dest


def palette_file(collection_id):
    """Arquivo de cores do GeoServer para a coleção, ou None (ex.: saúde)."""
    cid = (collection_id or "").lower()
    for prefix, part, filename in CLIMATE_PALETTES:
        if cid.startswith(prefix) and part in cid:
            return os.path.join(STYLES_DIR, filename)
    return None


def read_palette(path):
    """Lê linhas 'valor R:G:B' e retorna [(valor, QColor)] em ordem crescente.
    O valor PALETTE_NODATA é ignorado: feições com ele ficam sem desenho."""
    stops = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != 2:
                continue
            value = float(parts[0])
            if value <= PALETTE_NODATA:
                continue
            r, g, b = (int(x) for x in parts[1].split(":")[:3])
            stops.append((value, QColor(r, g, b)))
    stops.sort(key=lambda s: s[0])
    return stops


def fill_symbol(layer, color, opacity=None):
    """Símbolo com preenchimento semitransparente e contorno opaco."""
    fill = QColor(color)
    fill.setAlphaF(CLIMATE_OPACITY if opacity is None else opacity)   # só no preenchimento
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    symbol.setColor(fill)
    sl = symbol.symbolLayer(0)
    if hasattr(sl, "setStrokeColor"):            # contorno opaco nos polígonos
        sl.setStrokeColor(QColor(*CLIMATE_STROKE_COLOR))
        sl.setStrokeWidth(CLIMATE_STROKE_WIDTH)
    return symbol


def value_field(layer):
    """Retorna (atributo, campo) para a simbologia.
    'atributo' é o que o renderizador usa: o nome da coluna VALUE_FIELD ou, se ela
    estiver gravada como texto (ex.: "2"), a expressão to_real("value").
    'campo' é o nome real da coluna. Sem VALUE_FIELD, usa a heurística antiga."""
    for f in layer.fields():
        if f.name().lower() == VALUE_FIELD:
            if f.isNumeric():
                return f.name(), f.name()
            return 'to_real("{0}")'.format(f.name()), f.name()
    name = first_numeric_field(layer)
    return name, name


def numeric_values(layer, field):
    """Valores distintos da coluna convertidos para número (texto incluído).
    NULL, NaN e textos não numéricos são descartados."""
    values = set()
    for v in layer.uniqueValues(layer.fields().indexOf(field)):
        if isinstance(v, str):
            try:
                v = float(v.strip().replace(",", "."))
            except ValueError:
                continue
        if isinstance(v, (int, float)) and v == v:
            values.add(float(v))
    return sorted(values)


def _fmt(v):
    """Número com até 2 casas decimais, sem zeros à direita: 62.2, 755.08, 167."""
    return ("{0:.2f}".format(v)).rstrip("0").rstrip(".")


def health_renderer(layer, attribute, field, collection_id=None):
    """Saúde, com as cores dos SLD do GeoServer:
    - nível de alerta: uma cor fixa por nível (1 a 4), com rótulos de risco;
    - demais indicadores: 5 classes de intervalos iguais entre 0 e o valor máximo
      da camada (mesmo cálculo das legendas do explorer: passo = máximo / 5).
    Valores nulos ou não numéricos não são desenhados."""
    if "alert_level" in (collection_id or "").lower():
        expr = 'to_real("{0}")'.format(field)    # funciona com coluna numérica ou texto
        categories = [QgsRendererCategory(float(v), fill_symbol(layer, color, HEALTH_OPACITY), tr(label))
                      for v, color, label in ALERT_LEVELS]
        return QgsCategorizedSymbolRenderer(expr, categories)

    values = numeric_values(layer, field)
    if not values:
        return None
    vmin, vmax = values[0], values[-1]
    base = min(0.0, vmin)
    n = len(HEALTH_COLORS)
    if vmax <= base:                             # todos iguais (ex.: semana sem casos)
        rng = QgsRendererRange(vmin - 1e-9, vmax, fill_symbol(layer, HEALTH_COLORS[0], HEALTH_OPACITY),
                               _fmt(vmax))
        return QgsGraduatedSymbolRenderer(attribute, [rng])

    step = (vmax - base) / n
    breaks = [base + step * k for k in range(1, n)]          # 4 limites internos
    ranges = []
    for k, color in enumerate(HEALTH_COLORS):
        lower = -1e12 if k == 0 else breaks[k - 1]
        upper = 1e12 if k == n - 1 else breaks[k]
        if k == 0:
            label = tr("Lower than {0}").format(_fmt(breaks[0]))
        elif k == n - 1:
            label = tr("Greater than {0}").format(_fmt(breaks[-1]))
        else:
            label = tr("Between {0} and {1}").format(_fmt(lower), _fmt(upper))
        ranges.append(QgsRendererRange(lower, upper, fill_symbol(layer, color, HEALTH_OPACITY), label))
    return QgsGraduatedSymbolRenderer(attribute, ranges)


def palette_renderer(layer, field, stops):
    """Simbologia graduada com as classes do GeoServer: cada classe vai de um
    valor da paleta até o seguinte e usa a cor do valor inicial."""
    def fmt(v):
        return "{0:g}".format(v)

    ranges = []
    for i, (value, color) in enumerate(stops):
        last = i == len(stops) - 1
        upper = 1e12 if last else stops[i + 1][0]
        label = ">= {0}".format(fmt(value)) if last else "{0} - {1}".format(fmt(value), fmt(upper))
        symbol = fill_symbol(layer, color)
        ranges.append(QgsRendererRange(value, upper, symbol, label))
    return QgsGraduatedSymbolRenderer(field, ranges)


def load_vector(path, name, group=None, collection_id=None):
    """Carrega GeoJSON ou shapefile zipado.
    Clima: classes e cores do GeoServer (styles/), preenchimento com transparência
    CLIMATE_OPACITY e contorno opaco CLIMATE_STROKE_COLOR.
    Saúde: cores dos SLD do GeoServer pela coluna VALUE_FIELD (veja health_renderer)."""
    src = f"/vsizip/{path}" if path.lower().endswith(".zip") else path
    layer = QgsVectorLayer(src, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(tr("Could not open {0}").format(path))
    attribute, field = value_field(layer)
    pfile = palette_file(collection_id)
    if attribute and pfile and os.path.exists(pfile):
        layer.setRenderer(palette_renderer(layer, attribute, read_palette(pfile)))
    elif attribute:
        renderer = health_renderer(layer, attribute, field, collection_id)
        if renderer:
            layer.setRenderer(renderer)
    _add(layer, group)
    return layer


def load_raster(path, name, group=None):
    """Carrega GeoTIFF. Banda única com 'ndvi' no nome recebe rampa RdYlGn;
    RGB e multiespectral mantêm a renderização padrão do QGIS."""
    layer = QgsRasterLayer(path, name, "gdal")
    if not layer.isValid():
        raise RuntimeError(tr("Could not open {0}").format(path))
    if layer.bandCount() == 1 and "ndvi" in name.lower():
        prov = layer.dataProvider()
        stats = prov.bandStatistics(1, QgsRasterBandStats.Min | QgsRasterBandStats.Max)
        ramp = QgsStyle.defaultStyle().colorRamp("RdYlGn")
        if ramp:
            fn = QgsColorRampShader(stats.minimumValue, stats.maximumValue, ramp)
            fn.setColorRampType(QgsColorRampShader.Interpolated)
            fn.classifyColorRamp(10, 1, layer.extent(), prov)
            shader = QgsRasterShader()
            shader.setRasterShaderFunction(fn)
            renderer = QgsSingleBandPseudoColorRenderer(prov, 1, shader)
            renderer.setClassificationMin(stats.minimumValue)
            renderer.setClassificationMax(stats.maximumValue)
            layer.setRenderer(renderer)
    _add(layer, group)
    return layer


def first_numeric_field(layer, skip=("id", "fid", "cod", "geocod", "cd_mun", "ibge", "pop",
                                     "year", "ano", "month", "mes", "week", "semana",
                                     "epiweek", "date", "data")):
    """Campo numérico com mais valores distintos, ignorando identificadores e datas."""
    best, best_n = None, 1
    for idx, f in enumerate(layer.fields()):
        name = f.name().lower()
        if not f.isNumeric() or any(s in name for s in skip):
            continue
        n = len(layer.uniqueValues(idx))
        if n > best_n:
            best, best_n = f.name(), n
    return best


def set_temporal(layer, start_iso, end_iso):
    """Associa um intervalo fixo à camada (vetor ou raster) para o Controlador Temporal."""
    if not start_iso:
        return
    start = QDateTime.fromString(start_iso[:19], "yyyy-MM-ddTHH:mm:ss")
    end = QDateTime.fromString((end_iso or start_iso)[:19], "yyyy-MM-ddTHH:mm:ss").addDays(1)
    if not start.isValid():
        return
    start.setTimeSpec(Qt.TimeSpec.UTC)
    end.setTimeSpec(Qt.TimeSpec.UTC)
    props = layer.temporalProperties()
    if isinstance(layer, QgsRasterLayer):
        try:
            mode = Qgis.RasterTemporalMode.FixedTemporalRange       # QGIS >= 3.38
        except AttributeError:
            from qgis.core import QgsRasterLayerTemporalProperties
            mode = QgsRasterLayerTemporalProperties.ModeFixedTemporalRange
    else:
        try:
            mode = Qgis.VectorTemporalMode.FixedTemporalRange       # QGIS >= 3.30
        except AttributeError:
            from qgis.core import QgsVectorLayerTemporalProperties
            mode = QgsVectorLayerTemporalProperties.ModeFixedTemporalRange
    props.setMode(mode)
    props.setFixedTemporalRange(QgsDateTimeRange(start, end, True, False))
    props.setIsActive(True)


# ----------------------------------------------------------------- util
def _add(layer, group):
    project = QgsProject.instance()
    if group is None:
        project.addMapLayer(layer)
    else:
        project.addMapLayer(layer, False)
        group.addLayer(layer)
