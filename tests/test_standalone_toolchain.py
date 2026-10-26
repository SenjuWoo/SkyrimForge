"""Offline owner-update/runtime and receipt-reuse regressions; no installed tools are launched."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from skyrim_forge.config import ForgeConfig, ToolConfig, default_tools, save_config
from skyrim_forge.toolchain import reuse_reverse_tools, resolve_capability
from skyrim_forge.errors import SafetyError

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'

class ReverseReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.kit=self.root/'kit'; self.kit.mkdir()
        self.workspace=self.root/'workspace'; self.workspace.mkdir()
        self.cfg=ForgeConfig(config_path=self.root/'config.toml',workspace_root=self.workspace,audit_log=self.root/'audit.jsonl',tools=default_tools())
        save_config(self.cfg)
        records={}
        for ident,name in [('directxtex','texconv.exe'),('7zip','7z.exe')]:
            folder=self.kit/'sandbox/tools'/ident; folder.mkdir(parents=True)
            exe=folder/name; exe.write_bytes(b'not executed fixture')
            if ident=='7zip': (folder/'7z.dll').write_bytes(b'sidecar')
            records[ident]={'id':ident,'dir':folder.relative_to(self.kit).as_posix(),'sha256':{name:hashlib.sha256(exe.read_bytes()).hexdigest()}}
        installed=self.kit/'sandbox/installed.json'; installed.write_text(json.dumps({'schema':1,'kit_root':str(self.kit),'tools':records}))
        self.pointer=self.root/'kit.json'; self.pointer.write_text(json.dumps({'kit_root':str(self.kit),'installed_json':str(installed)}))

    def test_receipt_reuses_actual_exes_with_pins_and_no_copy(self):
        report=reuse_reverse_tools(self.cfg,approved=True,pointer=self.pointer)
        self.assertFalse(report['copied']); self.assertEqual(len(report['configured']),2)
        self.assertTrue(all(not r['copied'] for r in report['configured']))
        self.assertEqual(resolve_capability(self.cfg,'texture.dds.convert')['result'],'PASS')
        self.assertEqual(self.cfg.seven_zip,self.kit/'sandbox/tools/7zip/7z.exe')
        self.assertTrue(list(self.root.glob('config.toml.before-reverse-*.bak')))
        self.assertFalse((self.root/'tool-vault').exists())

    def test_user_paths_and_pins_are_preserved(self):
        custom=self.root/'texconv.exe'; custom.write_bytes(b'personal')
        self.cfg.tools['texconv']=ToolConfig(executable=custom,sha256='personal-pin')
        reuse_reverse_tools(self.cfg,approved=True,pointer=self.pointer)
        self.assertEqual(self.cfg.tools['texconv'].sha256,'personal-pin')
        self.assertEqual(self.cfg.tools['texconv'].executable,custom)

    def test_only_automatic_bindings_refresh_after_owner_update(self):
        reuse_reverse_tools(self.cfg,approved=True,pointer=self.pointer)
        old=self.cfg.tools['texconv'].sha256
        exe=self.kit/'sandbox/tools/directxtex/texconv.exe'; exe.write_bytes(b'new owner version')
        installed=self.kit/'sandbox/installed.json'; manifest=json.loads(installed.read_text())
        manifest['tools']['directxtex']['sha256']['texconv.exe']=hashlib.sha256(exe.read_bytes()).hexdigest()
        installed.write_text(json.dumps(manifest))
        reuse_reverse_tools(self.cfg,approved=True,pointer=self.pointer)
        self.assertNotEqual(self.cfg.tools['texconv'].sha256,old)
        self.cfg.tools['texconv'].sha256='personal-pin'
        reuse_reverse_tools(self.cfg,approved=True,pointer=self.pointer)
        self.assertEqual(self.cfg.tools['texconv'].sha256,'personal-pin')

    def test_bad_owner_hash_fails_before_changing_config(self):
        before=self.cfg.config_path.read_bytes()
        (self.kit/'sandbox/tools/directxtex/texconv.exe').write_bytes(b'changed')
        with self.assertRaises(SafetyError): reuse_reverse_tools(self.cfg,approved=True,pointer=self.pointer)
        self.assertEqual(self.cfg.config_path.read_bytes(),before)

@unittest.skipUnless(os.name=='nt','real Windows PowerShell fixtures')
class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.owner=self.base/'Forge installed'; self.owner.mkdir()
        self.env=dict(os.environ,LOCALAPPDATA=str(self.base/'local'),PSModulePath='')
        self.write_release(self.owner,'8.0.0',obsolete=True)
        (self.owner/'settings.toml').write_text('personal=true')
        (self.owner/'owned/private.txt').write_text('nested private data')
        (self.owner/'.venv/Scripts').mkdir(parents=True); (self.owner/'.venv/Scripts/keep.txt').write_text('healthy app venv')
        payload=self.base/'Skyrim-Forge-9.0.0'; payload.mkdir(); self.write_release(payload,'9.0.0')
        self.payload=payload
        self.archive=self.base/'release.zip'
        self.write_archive()

    def write_archive(self):
        payload=self.payload
        with zipfile.ZipFile(self.archive,'w') as z:
            for path in payload.rglob('*'):
                if path.is_file(): z.write(path,'Skyrim-Forge-9.0.0/'+path.relative_to(payload).as_posix())
        self.sha=hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def write_release(self,folder,version,obsolete=False):
        (folder/'VERSION.txt').write_text('Skyrim Forge '+version+'\n')
        (folder/'Install-AI-Bridge.ps1').write_text("throw 'fixture never called'\n")
        (folder/'owner.txt').write_text(version)
        (folder/'owned').mkdir(exist_ok=True); (folder/'owned/release.txt').write_text(version)
        if obsolete: (folder/'obsolete.txt').write_text('old owner file')
        files=[{'path':p.relative_to(folder).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in folder.rglob('*') if p.is_file()]
        (folder/'MANIFEST.json').write_text(json.dumps({'product':'Skyrim Forge','version':version,'files':files}))

    def run_ps(self,path,*args):
        return subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(path),*args],env=self.env,capture_output=True,text=True,timeout=45)

    def update(self,*args):
        return self.run_ps(ROOT/'Update-Forge.ps1','-Root',str(self.owner),'-Archive',str(self.archive),'-ReleaseVersion','9.0.0','-Sha256',self.sha,'-SkipSetup',*args)

    def test_offline_owner_update_retains_venv_settings_and_rollback(self):
        venv_inode=(self.owner/'.venv/Scripts/keep.txt').stat().st_ino
        result=self.update(); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'9.0.0')
        self.assertFalse((self.owner/'obsolete.txt').exists())
        self.assertEqual((self.owner/'settings.toml').read_text(),'personal=true')
        self.assertEqual((self.owner/'owned/private.txt').read_text(),'nested private data')
        self.assertEqual((self.owner/'.venv/Scripts/keep.txt').stat().st_ino,venv_inode)
        backups=list(self.base.glob('.forge-backup-*')); self.assertEqual(len(backups),1)
        self.assertTrue((backups[0]/'obsolete.txt').exists())
        result=self.update(); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('already matches the verified owner payload',result.stdout)
        result=self.update('-CheckOnly'); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('same version',result.stdout)
        self.assertEqual(len(list(self.base.glob('.forge-backup-*'))),1)

    def test_private_workspace_junction_moves_without_copy_or_traversal(self):
        external=self.base/'external workspace'; external.mkdir()
        sentinel=external/'project.txt'; sentinel.write_text('private work')
        inode=sentinel.stat().st_ino
        script=self.base/'junction.ps1'
        script.write_text("New-Item -ItemType Junction -Path $args[0] -Target $args[1] | Out-Null\n",encoding='ascii')
        junction=self.owner/'Workspaces'
        result=self.run_ps(script,str(junction),str(external)); self.assertEqual(result.returncode,0,result.stderr)
        result=self.update(); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(junction.is_junction())
        self.assertEqual((junction/'project.txt').stat().st_ino,inode)
        self.assertFalse(any((backup/'Workspaces').exists() for backup in self.base.glob('.forge-backup-*')))
        self.assertEqual(sentinel.read_text(),'private work')

    def test_local_source_ignores_private_content_and_allows_version_marker(self):
        (self.owner/'VERSION.txt').write_text('Skyrim Forge '+'0.0.1\n')
        (self.payload/'.venv').mkdir(); (self.payload/'.venv/private.txt').write_text('not release content')
        (self.payload/'.git').mkdir()
        result=self.run_ps(ROOT/'Update-Forge.ps1','-Root',str(self.owner),'-SourceDir',str(self.payload),'-SkipSetup')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'9.0.0')
        self.assertTrue((self.owner/'.venv/Scripts/keep.txt').exists())
        self.assertFalse((self.owner/'.venv/private.txt').exists())
        self.assertFalse((self.owner/'.git').exists())

    def test_private_path_collision_fails_before_swap(self):
        added=self.payload/'settings.toml'; added.write_text('release template')
        manifest=self.payload/'MANIFEST.json'; data=json.loads(manifest.read_text())
        data['files'].append({'path':'settings.toml','sha256':hashlib.sha256(added.read_bytes()).hexdigest()})
        manifest.write_text(json.dumps(data)); self.write_archive()
        result=self.update(); self.assertNotEqual(result.returncode,0)
        self.assertIn('Private path conflicts',result.stderr)
        self.assertEqual((self.owner/'settings.toml').read_text(),'personal=true')
        self.assertEqual((self.owner/'owned/private.txt').read_text(),'nested private data')
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        self.assertFalse(list(self.base.glob('.forge-backup-*')))

    def test_setup_failure_returns_private_content_before_restoring_owner(self):
        inode=(self.owner/'.venv/Scripts/keep.txt').stat().st_ino
        result=self.run_ps(ROOT/'Update-Forge.ps1','-Root',str(self.owner),'-Archive',str(self.archive),'-ReleaseVersion','9.0.0','-Sha256',self.sha)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('fixture never called',result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        self.assertEqual((self.owner/'settings.toml').read_text(),'personal=true')
        self.assertEqual((self.owner/'owned/private.txt').read_text(),'nested private data')
        self.assertEqual((self.owner/'.venv/Scripts/keep.txt').stat().st_ino,inode)

    def test_edited_owner_file_is_preserved_before_mutation(self):
        edited=self.owner/'owned/release.txt'; edited.write_text('personal owner edit')
        result=self.update(); self.assertNotEqual(result.returncode,0)
        self.assertIn('Edited owner file preserved',result.stderr)
        self.assertEqual(edited.read_text(),'personal owner edit')
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        self.assertFalse(list(self.base.glob('.forge-backup-*')))

    def test_same_version_different_payload_is_explicitly_refused(self):
        (self.owner/'VERSION.txt').write_text('Skyrim Forge '+'9.0.0\n')
        result=self.update(); self.assertNotEqual(result.returncode,0)
        self.assertIn('Same-version owner payload differs',result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        self.assertFalse(list(self.base.glob('.forge-backup-*')))

    def test_nonzero_setup_exit_rolls_back_owner_and_private_files(self):
        setup=self.payload/'Install-AI-Bridge.ps1'; setup.write_text('exit 7\n')
        manifest=self.payload/'MANIFEST.json'; data=json.loads(manifest.read_text())
        for entry in data['files']:
            if entry['path']=='Install-AI-Bridge.ps1': entry['sha256']=hashlib.sha256(setup.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(data)); self.write_archive()
        result=self.run_ps(ROOT/'Update-Forge.ps1','-Root',str(self.owner),'-Archive',str(self.archive),'-ReleaseVersion','9.0.0','-Sha256',self.sha)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Forge setup failed with exit code 7',result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        self.assertEqual((self.owner/'settings.toml').read_text(),'personal=true')
        self.assertEqual((self.owner/'owned/private.txt').read_text(),'nested private data')

    def test_concurrent_owner_lock_fails_before_installation_changes(self):
        lock=self.base/('.'+self.owner.name+'.forge-update.lock')
        with lock.open('a+b'):
            result=self.update()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('owner update lock is unavailable',result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        self.assertFalse(list(self.base.glob('.forge-backup-*')))
        self.assertFalse(list(self.base.glob('.forge-stage-*')))

    def test_game_target_is_rejected_before_creating_owner_lock(self):
        (self.base/'SkyrimSE.exe').write_bytes(b'game marker')
        result=self.update(); self.assertNotEqual(result.returncode,0)
        self.assertIn('cannot target a game installation',result.stderr)
        self.assertFalse((self.base/('.'+self.owner.name+'.forge-update.lock')).exists())
        self.assertFalse(list(self.base.glob('.forge-backup-*')))
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')

    def test_digest_mismatch_leaves_install_untouched(self):
        self.sha='0'*64; result=self.update()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('SHA-256 mismatch',result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')

    def test_newer_or_git_checkout_is_preserved_without_network(self):
        (self.owner/'VERSION.txt').write_text('Skyrim Forge '+'10.0.0\n')
        result=self.update(); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        (self.owner/'.git').mkdir()
        result=self.run_ps(ROOT/'Update-Forge.ps1','-Root',str(self.owner))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Git development checkout preserved',result.stdout)

    def test_shared_python_process_selection_precedes_existing_venv(self):
        script=self.base/'probe.ps1'
        script.write_text(r'''$ErrorActionPreference='Stop'
$Root=$env:FORGE_FIXTURE
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($env:FORGE_INSTALLER,[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
foreach($fn in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$python=Find-Python
if($python.Source -cne 'UABS_PYTHON:Process'){throw 'Shared Python was not preferred'}
''',encoding='utf-8')
        self.env.update(FORGE_FIXTURE=str(self.owner),FORGE_INSTALLER=str(ROOT/'Install-or-Update.ps1'),UABS_PYTHON=sys.executable)
        result=self.run_ps(script); self.assertEqual(result.returncode,0,result.stdout+result.stderr)


    def test_manager_update_preserves_its_feature_line_without_network(self):
        manager=self.base/'pymanager.cmd'
        line=f'{sys.version_info.major}.{sys.version_info.minor}'
        inventory={'versions':[{'company':'PythonCore','tag':line+'-64','executable':sys._base_executable}]}
        manager.write_text('@echo off\n@echo '+json.dumps(inventory)+'\n',encoding='ascii')
        script=self.base/'manager-probe.ps1'
        script.write_text(r'''$ErrorActionPreference='Stop'
$Root=$env:FORGE_FIXTURE
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($env:FORGE_INSTALLER,[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
foreach($fn in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
function Get-Command { param($Name,$ErrorAction) if($Name -eq 'pymanager'){return [pscustomobject]@{Source=$env:MANAGER_FIXTURE}} }
function Invoke-Checked { param($Label,$Command,$Arguments) [IO.File]::WriteAllText($env:MANAGER_MARKER,($Arguments -join '|')) }
Update-SharedPython ([pscustomobject]@{Exe=$env:PYTHON_FIXTURE;Args=@()})
''',encoding='utf-8')
        marker=self.base/'manager-args.txt'
        self.env.update(FORGE_FIXTURE=str(self.owner),FORGE_INSTALLER=str(ROOT/'Install-or-Update.ps1'),MANAGER_FIXTURE=str(manager),MANAGER_MARKER=str(marker),PYTHON_FIXTURE=sys.executable)
        result=self.run_ps(script); self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(marker.read_text(),f'install|--update|--yes|{line}-64')

    def test_owner_swap_failure_restores_the_complete_previous_root(self):
        script=self.base/'fault.ps1'
        script.write_text(r'''$ErrorActionPreference='Stop'
function Move-Item {
    param($LiteralPath,$Destination,[switch]$Force)
    if ((Split-Path -Leaf $LiteralPath) -like '.forge-stage-*') { throw 'injected owner swap failure' }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
}
& $args[0] -Root $args[1] -Archive $args[2] -ReleaseVersion '9.0.0' -Sha256 $args[3] -SkipSetup
''',encoding='utf-8')
        result=self.run_ps(script,str(ROOT/'Update-Forge.ps1'),str(self.owner),str(self.archive),self.sha)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('injected owner swap failure',result.stderr)
        self.assertEqual((self.owner/'owner.txt').read_text(),'8.0.0')
        self.assertTrue((self.owner/'settings.toml').exists())

if __name__=='__main__': unittest.main()
