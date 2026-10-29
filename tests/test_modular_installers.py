"""Owner boundaries and installed-path regressions, using isolated files only."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ModularInstallerTests(unittest.TestCase):
    def test_external_skill_pack_is_complete_and_registry_is_valid(self):
        skills = ROOT / 'integrations/skyrim-pack/skills'
        self.assertEqual(len(list(skills.glob('*/SKILL.md'))), 50)
        registry = json.loads((skills / 'skyrim-memory/references/ERROR-REGISTRY.json').read_text(encoding='utf-8-sig'))
        entries = registry['entries']
        self.assertEqual(len({e['id'] for e in entries}), len(entries))
        for entry in entries:
            for field in ('id','title','symptom','root_cause','prevention','evidence_status'):
                self.assertTrue(entry.get(field), (entry.get('id'), field))

    @unittest.skipUnless(os.name == 'nt', 'Windows path fixture')
    def test_housecarl_preserves_flat_and_server_layouts_and_root_only_hint(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            flat = base / 'flat'
            flat.mkdir()
            (flat / 'housecarl-mcp.exe').write_bytes(b'fixture, never executed')
            script = base / 'test.ps1'
            text = r"""$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($env:HC_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
foreach($fn in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $fn.Extent.Text}
$exe=Join-Path $env:HC_FIXTURE 'flat\housecarl-mcp.exe'
$location=Get-HouseCarlLocation $exe
if($location.mcp -ne $exe -or $location.server -ne (Split-Path $exe -Parent)){throw 'Flat executable path changed'}
$candidates=@(Get-HouseCarlCandidates -McpPaths @() -Roots @((Split-Path $exe -Parent)))
if($candidates.Count -ne 1 -or $candidates[0] -ne $exe){throw 'Root-only registration ignored'}
$serverExe=Join-Path $env:HC_FIXTURE 'normal\server\housecarl-mcp.exe'
$location=Get-HouseCarlLocation $serverExe
if($location.mcp -ne $serverExe -or $location.root -ne (Join-Path $env:HC_FIXTURE 'normal')){throw 'Server layout changed'}
"""
            script.write_text(text, encoding='utf-8')
            env=dict(os.environ, HC_SOURCE=str(ROOT/'Install-HouseCarl.ps1'), HC_FIXTURE=td)
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__ == '__main__':
    unittest.main()
