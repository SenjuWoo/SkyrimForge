"""Exercise tracked and Git-free runtime inventories rather than filesystem denylisting."""
import hashlib, importlib.util, json, os, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from skyrim_forge.delivery import product_files,source_files
from skyrim_forge.version import VERSION
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('archive_builder',ROOT/'scripts/build_release_archive.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class DeliveryTests(unittest.TestCase):
    def test_tracked_allowlist_and_git_free_rebuild(self):
        with tempfile.TemporaryDirectory(prefix='Forge Ω ! ') as td:
            root=Path(td)/'source';root.mkdir()
            subprocess.run(['git','init','-q',str(root)],check=True,capture_output=True)
            for name in ['VERSION.txt','LICENSE','README.md','skyrim_forge/main.py','docs/usage.md','STATE.md','CHANGELOG.txt','tests/test.py']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('original')
            subprocess.run(['git','-C',str(root),'add','.'],check=True,capture_output=True)
            (root/'skyrim_forge/private.py').write_text('untracked private')
            (root/'docs/private.txt').write_text('untracked private')
            expected={'VERSION.txt','LICENSE','README.md','skyrim_forge/main.py','docs/usage.md'}
            self.assertEqual({p.relative_to(root).as_posix() for p in product_files(root)},expected)
            a=Path(td)/'a.zip';b=Path(td)/'b.zip'
            with patch.object(builder,'ROOT',root):
                builder.build(a);builder.build(b)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            extracted=Path(td)/'extracted'
            with zipfile.ZipFile(a) as archive:
                self.assertIsNone(archive.testzip());archive.extractall(extracted)
            delivery=extracted/f'Skyrim-Forge-{VERSION}'
            self.assertEqual({p.relative_to(delivery).as_posix() for p in source_files(delivery)},expected|{'MANIFEST.json'})
            (delivery/'docs/private.txt').write_text('private')
            self.assertEqual(len(source_files(delivery)),len(expected)+1)
            (delivery/'README.md').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'mismatch'):source_files(delivery)

    def test_actual_product_entrypoints_outside_git(self):
        with tempfile.TemporaryDirectory(prefix='Forge product Ω ! ') as td:
            base=Path(td); archive=base/'product.zip'
            builder.build(archive)
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip()); z.extractall(base/'extracted')
            product=base/'extracted'/f'Skyrim-Forge-{VERSION}'
            for name in ('STATE.md','PLAN.md','WORKSPACE_OWNERSHIP.md','CHANGELOG.txt','CHANGELOG.md','tests','.github'):
                self.assertFalse((product/name).exists(), name)
            self.assertTrue((product/'LICENSE').is_file())
            env=dict(os.environ,SKYRIM_FORGE_CONFIG=str(base/'private-config.toml'),SKYRIM_FORGE_ROOT=str(product))
            probe='import sys;sys.path.insert(0,sys.argv.pop(1));from skyrim_forge.cli import main;raise SystemExit(main())'
            result=subprocess.run([sys.executable,'-I','-c',probe,str(product),'self-test'],cwd=product,env=env,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            platform='win-x64' if os.name=='nt' else 'linux-x64'
            native=product/'writer/published'/platform/('SkyrimForge.Native.exe' if os.name=='nt' else 'SkyrimForge.Native')
            if os.name!='nt':native.chmod(0o755)
            result=subprocess.run([str(native),'self-test'],cwd=product,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            if os.name=='nt':
                result=subprocess.run(['cmd.exe','/d','/c','call',str(product/'START-HERE.bat'),'--validate-only'],cwd=product,env=env,capture_output=True,text=True,timeout=45)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_duplicate_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'file').write_bytes(b'a')
            row={'path':'file','sha256':hashlib.sha256(b'a').hexdigest(),'size':1}
            (root/'MANIFEST.json').write_text(json.dumps({'files':[row,row]}))
            with self.assertRaisesRegex(ValueError,'duplicate'):source_files(root)

if __name__=='__main__':unittest.main()
