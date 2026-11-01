"""
harmonize_core.py
Núcleo do plugin Harmonize Brazil Catalog: catálogo STAC e download.
Não depende da interface; pode ser testado no Console Python do QGIS.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from qgis.core import (Qgis, QgsColorRampShader, QgsDateTimeRange,
                       QgsGraduatedSymbolRenderer, QgsMessageLog, QgsProject,
                       QgsRasterBandStats, QgsRasterLayer, QgsRasterShader,
                       QgsSingleBandPseudoColorRenderer, QgsStyle, QgsVectorLayer)
from qgis.PyQt.QtCore import QCoreApplication, QDateTime, Qt

STAC_URL = "https://geolab.inpe.br/bdc/harmonize/stac/v1"
USER_AGENT = "QGIS-HarmonizeBrazil/0.1"
LOG_TAG = "Harmonize Brazil"
REGIONS = {"ne": "NE", "no": "NO"}
SIZE_WARNING_MB = 50
DRONE_WORKSPACE = "harmonize_drone"   # prefixo do layerName das coleções de drone

# Formatos de download por tipo de coleção (chave interna -> rótulo)
VECTOR_FORMATS = ["geojson", "shapefile"]
RASTER_FORMATS = ["geotiff"]
TIFF_EXTS = (".tif", ".tiff")                  # acima disso, o usuário confirma o download   # códigos; o rótulo traduzido fica no diálogo


def tr(message):
    """Tradução no contexto do núcleo (veja i18n/HarmonizeBrazil_pt_BR.ts)."""
    return QCoreApplication.translate("@default", message)


def log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, LOG_TAG, level)


# ----------------------------------------------------------------- HTTP
def _get_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ----------------------------------------------------------------- STAC
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
        ctype = "drone" if layer_name.startswith(DRONE_WORKSPACE) else (c.get("bdc:type") or "")
        out.append({
            "id": cid,
            "title": c.get("title") or cid,
            "description": c.get("description") or "",
            "type": ctype,                               # climate | health | drone
            "region": next((REGIONS[p] for p in parts if p in REGIONS), ""),
            "keywords": [k for k in (c.get("keywords") or []) if k],
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
    except urllib.error.HTTPError:
        # servidor não aceita o filtro: busca tudo e filtra localmente depois
        log(tr("Server rejected the datetime filter; fetching all items."), Qgis.Warning)
        first = _get_json(f"{base}?limit={limit}")

    items, page = [], first
    while True:
        items.extend(page.get("features", []))
        nxt = next((l for l in page.get("links", []) if l.get("rel") == "next"), None)
        if not nxt or (is_canceled and is_canceled()):
            break
        page = _get_json(nxt["href"])
    items.sort(key=lambda f: f.get("properties", {}).get("datetime") or "")
    return items


# ----------------------------------------------------------------- download
def find_asset(item, fmt):
    """Retorna (chave, asset) do formato pedido ou (None, None).
    geojson/shapefile: chave direta. geotiff: primeiro asset .tif/.tiff ou
    image/tiff que não seja miniatura."""
    assets = item.get("assets") or {}
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


def asset_size(item, fmt, timeout=30):
    """Tamanho do asset em bytes: usa file:size do STAC ou um HEAD HTTP.
    Retorna None se o tamanho não puder ser determinado."""
    asset = find_asset(item, fmt)[1] or {}
    size = asset.get("file:size")
    if isinstance(size, (int, float)) and size > 0:
        return int(size)
    try:
        req = urllib.request.Request(asset["href"], method="HEAD",
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            length = resp.headers.get("Content-Length")
            return int(length) if length else None
    except Exception:  # noqa: BLE001
        return None


def format_size(n_bytes):
    """Tamanho legível: 12.3 MB, 1.2 GB."""
    mb = n_bytes / 1024 ** 2
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.1f} MB"


def download_asset(item, fmt, out_dir, progress=None, is_canceled=None):
    """Baixa o asset no formato pedido (geojson | shapefile | geotiff). Usa cache local."""
    href, dest = asset_local_path(item, fmt, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(dest):
        return dest
    tmp = dest + ".part"
    req = urllib.request.Request(href, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if is_canceled and is_canceled():
                raise RuntimeError(tr("Canceled by the user."))
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    os.replace(tmp, dest)
    return dest


def load_vector(path, name, group=None, ramp="Spectral", invert=True, classes=5):
    """Carrega GeoJSON ou shapefile zipado com simbologia graduada."""
    src = f"/vsizip/{path}" if path.lower().endswith(".zip") else path
    layer = QgsVectorLayer(src, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(tr("Could not open {0}").format(path))
    field = first_numeric_field(layer)
    if field:
        renderer = QgsGraduatedSymbolRenderer(field)
        color_ramp = QgsStyle.defaultStyle().colorRamp(ramp)
        if color_ramp:
            if invert:
                color_ramp.invert()
            renderer.setSourceColorRamp(color_ramp)
        renderer.updateClasses(layer, QgsGraduatedSymbolRenderer.Jenks, classes)
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
