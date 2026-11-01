"""
make_zip.py
Gera o pacote do plugin Harmonize Brazil Catalog para o repositório oficial
(plugins.qgis.org).

Uso (na raiz do repositório, no OSGeo4W Shell ou em qualquer Python 3):
    python make_zip.py            # código em ./src
    python make_zip.py caminho    # código em outra pasta

Saída: dist/harmonize_brazil-<versão>.zip, com uma única pasta
harmonize_brazil/ contendo apenas os arquivos necessários ao plugin.
"""
import configparser
import os
import sys
import zipfile

PLUGIN_DIR = "harmonize_brazil"          # nome da pasta dentro do zip
MAX_MB = 20                              # limite do repositório oficial

# Arquivos da raiz do plugin que vão no pacote
FILES = [
    "__init__.py",
    "metadata.txt",
    "LICENSE",
    "icon.png",
    "harmonize_brazil.py",
    "harmonize_brazil_dialog.py",
    "harmonize_brazil_dialog_base.ui",
    "harmonize_core.py",
    "harmonize_tasks.py",
]
# Pastas incluídas, com as extensões aceitas em cada uma
DIRS = {
    "i18n": (".qm",),                    # só as traduções compiladas
    "styles": (".txt",),                 # tabelas de cores de clima
}
REQUIRED_METADATA = ["name", "qgisMinimumVersion", "description", "about", "version",
                     "author", "email", "repository", "tracker"]


def fail(msg):
    print("ERRO:", msg)
    sys.exit(1)


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    src = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(root, "src")
    if not os.path.isfile(os.path.join(src, "metadata.txt")):
        fail(f"metadata.txt não encontrado em {src}")

    # 1. Metadados
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(src, "metadata.txt"), encoding="utf-8")
    if "general" not in cfg:
        fail("metadata.txt sem a seção [general]")
    meta = cfg["general"]
    missing = [k for k in REQUIRED_METADATA if not meta.get(k, "").strip()]
    if missing:
        fail("campos obrigatórios vazios no metadata.txt: " + ", ".join(missing))
    version = meta["version"].strip()
    if "changelog" not in meta or version not in meta.get("changelog", ""):
        print(f"AVISO: o changelog não menciona a versão {version}.")

    # 2. Lista de arquivos
    entries = []
    for name in FILES:
        path = os.path.join(src, name)
        if not os.path.isfile(path):
            fail(f"arquivo obrigatório ausente: {name}")
        entries.append((path, f"{PLUGIN_DIR}/{name}"))
    for folder, exts in DIRS.items():
        base = os.path.join(src, folder)
        if not os.path.isdir(base):
            fail(f"pasta ausente: {folder}")
        found = sorted(f for f in os.listdir(base) if f.lower().endswith(exts))
        if not found:
            fail(f"nenhum arquivo {exts} em {folder}")
        entries += [(os.path.join(base, f), f"{PLUGIN_DIR}/{folder}/{f}") for f in found]

    # 3. Zip (caminhos internos sempre com "/")
    out_dir = os.path.join(root, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{PLUGIN_DIR}-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in entries:
            zf.write(path, arcname)

    # 4. Conferência
    size_mb = os.path.getsize(out) / 1024 ** 2
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    roots = {n.split("/")[0] for n in names}
    print(f"\nPacote: {out}")
    print(f"Versão: {version} | {len(names)} arquivos | {size_mb:.2f} MB")
    for n in names:
        print("  ", n)
    if roots != {PLUGIN_DIR}:
        fail(f"o zip deve ter uma única pasta raiz ({PLUGIN_DIR}), encontrado: {roots}")
    if size_mb > MAX_MB:
        fail(f"o pacote passa de {MAX_MB} MB")
    print("\nOK: pacote pronto para envio.")


if __name__ == "__main__":
    main()
