"""Tarefas em segundo plano: verificação (itens + tamanho) e download dos assets."""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from qgis.core import QgsTask

from qgis.PyQt.QtCore import QCoreApplication

from . import harmonize_core as hc


def tr(message):
    return QCoreApplication.translate("@default", message)


def _overlaps(item, start, end):
    """True se o período do item intersecta [start, end] (datas AAAA-MM-DD)."""
    props = item.get("properties", {})
    i_start = (props.get("start_datetime") or props.get("datetime") or "")[:10]
    i_end = (props.get("end_datetime") or props.get("datetime") or "")[:10]
    return bool(i_start) and i_start <= end and i_end >= start


class HarmonizePrepareTask(QgsTask):
    """Busca os itens do período e soma o tamanho do que ainda não está em cache."""

    def __init__(self, params, on_done):
        col = params["collection"]
        super().__init__(tr("Harmonize: checking files ({0})").format(col["id"]))
        self.params = params
        self.on_done = on_done
        self.out_dir = os.path.join(params["out_dir"], col["id"])
        self.items = []          # itens com o asset escolhido
        self.to_download = 0     # quantos não estão em cache
        self.total_bytes = 0     # soma dos tamanhos conhecidos
        self.unknown = 0         # quantos sem tamanho conhecido
        self.error = None

    def run(self):
        p = self.params
        try:
            items = hc.list_items(p["collection"]["id"], p["start"], p["end"],
                                  is_canceled=self.isCanceled)
            items = [i for i in items if _overlaps(i, p["start"], p["end"])]
            self.items = [i for i in items if hc.find_asset(i, p["fmt"])[1]]
            if not self.items:
                self.error = tr("No items found in the selected period.")
                return False

            pending = [i for i in self.items
                       if not os.path.exists(hc.asset_local_path(i, p["fmt"], self.out_dir)[1])]
            self.to_download = len(pending)
            if not pending:
                return True

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(hc.asset_size, i, p["fmt"]) for i in pending]
                for k, fut in enumerate(as_completed(futures)):
                    if self.isCanceled():
                        for f in futures:
                            f.cancel()
                        return False
                    size = fut.result()
                    if size is None:
                        self.unknown += 1
                    else:
                        self.total_bytes += size
                    self.setProgress((k + 1) / len(pending) * 100)
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            return False

    def finished(self, result):
        self.on_done(self, result)


class HarmonizeDownloadTask(QgsTask):
    def __init__(self, params, items, on_done):
        col = params["collection"]
        super().__init__(tr("Harmonize: {0} ({1} to {2})").format(col["id"], params["start"], params["end"]))
        self.params = params
        self.items = items
        self.on_done = on_done
        self.out_dir = os.path.join(params["out_dir"], col["id"])
        self.files = []   # lista de (caminho, item)
        self.error = None

    def run(self):
        p = self.params
        try:
            total = len(self.items)
            hc.log(tr("{0} item(s) to download into {1}").format(total, self.out_dir))
            for k, item in enumerate(self.items):
                if self.isCanceled():
                    return False
                path = hc.download_asset(
                    item, p["fmt"], self.out_dir,
                    progress=lambda frac, k=k: self.setProgress((k + frac) / total * 100),
                    is_canceled=self.isCanceled)
                self.files.append((path, item))
                self.setProgress((k + 1) / total * 100)
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            return False

    def finished(self, result):
        # Executado na thread principal: seguro para adicionar camadas
        self.on_done(self, result)
