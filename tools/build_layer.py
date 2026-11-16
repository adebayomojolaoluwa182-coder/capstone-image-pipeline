"""Build the pinned Linux Pillow layer without requiring Docker on Windows."""
from pathlib import Path
import subprocess
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/"build/layer/python"
if target.exists() and any(target.iterdir()):
    raise SystemExit("Layer build folder is not empty. Use a fresh checkout or review and remove the old build before rebuilding.")
target.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,"-m","pip","install","--platform","manylinux_2_28_x86_64",
    "--implementation","cp","--python-version","3.12","--only-binary=:all:","--no-deps",
    "-r",str(ROOT/"requirements-layer.txt"),"--target",str(target)],check=True)
out=ROOT/"build/pillow-layer.zip"
with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
    for file in target.rglob("*"):
        if file.is_file(): archive.write(file,file.relative_to(target.parent))
print(out)
