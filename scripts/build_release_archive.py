"""Build the runnable Forge product from an explicit inventory; source/dev archives are separate."""
from __future__ import annotations
import argparse, hashlib, json, os, re, zipfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from skyrim_forge.delivery import product_files
VERSION=re.search(r'^VERSION\s*=\s*"([^"]+)"',(ROOT/"skyrim_forge"/"version.py").read_text(encoding="utf-8"),re.M).group(1)
FIXED=(2026,7,26,0,0,0)
EXCLUDED={".git",".venv","venv",".go-cache","__pycache__","dist","build",".pytest_cache","REPORTS","INSTALLATION.json"}

def files():
    return product_files(ROOT)

def build(output: Path):
    output=output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix(output.suffix+".tmp")
    payload={p.relative_to(ROOT).as_posix():p.read_bytes() for p in files()}
    # This manifest describes only delivered runtime files, not repository-only ledgers/tests.
    manifest={"product":"Skyrim Forge","version":VERSION,"files":[
        {"path":name,"size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        for name,data in sorted(payload.items())]}
    payload["MANIFEST.json"]=(json.dumps(manifest,indent=2)+"\n").encode()
    prefix=f"Skyrim-Forge-{VERSION}/"
    with zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(payload.items(),key=lambda row:row[0].casefold()):
            info=zipfile.ZipInfo(prefix+name,FIXED);info.create_system=3
            executable=name.endswith("linux-x64/SkyrimForge.Native")
            info.external_attr=(0o100755 if executable else 0o100644)<<16
            z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(tmp) as z:
        bad=z.testzip()
        if bad:raise RuntimeError(f"CRC failure: {bad}")
        if set(z.namelist())!={prefix+n for n in payload}:raise RuntimeError("Product archive inventory mismatch")
    os.replace(tmp,output)
    return hashlib.sha256(output.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("output",nargs="?",default=str(ROOT.parent/f"Skyrim-Forge-{VERSION}.zip"))
    out=Path(ap.parse_args().output);print(build(out),out)
if __name__=="__main__":main()
