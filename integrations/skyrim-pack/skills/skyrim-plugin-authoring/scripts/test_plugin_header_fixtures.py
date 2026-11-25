#!/usr/bin/env python3
from pathlib import Path
import struct, subprocess, sys, tempfile

def sr(tag,data): return tag+struct.pack('<H',len(data))+data

def make_plugin(path, hedr, masters, local_id, light=True, idx=None):
    hdata=sr(b'HEDR',struct.pack('<fII',hedr,1,0))
    for m in masters: hdata+=sr(b'MAST',m.encode('ascii')+b'\0')+sr(b'DATA',b'\0'*8)
    flags=0x200 if light else 0
    tes4=b'TES4'+struct.pack('<II',len(hdata),flags)+b'\0'*8+struct.pack('<H',44)+b'\0\0'+hdata
    idx=len(masters) if idx is None else idx; formid=(idx<<24)|local_id
    rec=b'KYWD'+struct.pack('<II',0,0)+struct.pack('<I',formid)+b'\0'*4+struct.pack('<H',44)+b'\0\0'
    path.write_bytes(tes4+rec)

def run(script,path,*args): return subprocess.run([sys.executable,str(script),str(path),*args],capture_output=True,text=True)

def main():
    script=Path(__file__).with_name('audit_plugin_headers.py')
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        cases=[
            ('legacy-pass',1.70,['Skyrim.esm'],0x800,0),
            ('extended-pass',1.71,['Skyrim.esm'],0x001,0),
            ('extended-no-master-fail',1.71,[],0x001,1),
            ('extended-old-header-fail',1.70,['Skyrim.esm'],0x001,1),
        ]
        for name,h,masters,lid,expected in cases:
            p=root/f'{name}.esp'; make_plugin(p,h,masters,lid)
            r=run(script,p,'--expect-light','--require-form-version','44')
            if r.returncode!=expected:
                print(r.stdout); print(r.stderr); raise SystemExit(f'{name}: expected {expected}, got {r.returncode}')
        # Header-chain audit with --master-root. A full HEDR 1.71 master (AE Skyrim.esm)
        # imposes nothing on a 1.70 dependent; only reaching a 1.71 LIGHT master's
        # 0x001-0x7FF range does.
        masters=root/'masters'; masters.mkdir()
        make_plugin(masters/'Skyrim.esm',1.71,[],0x800,light=False)
        make_plugin(masters/'LightMaster.esp',1.71,['Skyrim.esm'],0x001)
        chain=[
            ('full-170-on-ae-skyrim-pass',1.70,['Skyrim.esm'],0x800,False,None,['--expect-full'],0,None),
            ('light-170-on-ae-skyrim-pass',1.70,['Skyrim.esm'],0x800,True,None,['--expect-light'],0,None),
            ('override-extended-light-master-170-fail',1.70,['Skyrim.esm','LightMaster.esp'],0x001,True,1,['--expect-light'],1,'override(s) of extended-range records'),
            ('new-record-on-light-master-170-warn',1.70,['Skyrim.esm','LightMaster.esp'],0x800,True,None,['--expect-light'],0,'WARN: light master LightMaster.esp'),
            ('override-extended-light-master-171-pass',1.71,['Skyrim.esm','LightMaster.esp'],0x001,True,1,['--expect-light'],0,None),
        ]
        for name,h,mast,lid,light,idx,flags,expected,needle in chain:
            p=root/f'{name}.esp'; make_plugin(p,h,mast,lid,light=light,idx=idx)
            r=run(script,p,*flags,'--require-form-version','44','--master-root',str(masters))
            if r.returncode!=expected or (needle and needle not in r.stdout):
                print(r.stdout); print(r.stderr); raise SystemExit(f'{name}: expected {expected} with {needle!r}, got {r.returncode}')
    print('PLUGIN FIXTURE TESTS: PASS')
if __name__=='__main__': main()
