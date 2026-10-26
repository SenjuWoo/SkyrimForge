"""Real Windows filesystem regressions for independent, preserving Skyrim skill installs."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


@unittest.skipUnless(os.name == 'nt', 'Windows provider integration')
class SkillOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'Forge source'
        self.root.mkdir()
        for name in ('Install-Skyrim-Pack.ps1', 'Install-Forge-Skill.ps1'):
            shutil.copy2(ROOT / name, self.root / name)
        (self.root / 'scripts').mkdir()
        helper = ROOT / 'scripts/Provider-Skills.ps1'
        if helper.exists():
            shutil.copy2(helper, self.root / 'scripts/Provider-Skills.ps1')
        self.source = self.root / 'integrations/skyrim-pack/skills/skyrim-forge'
        self.source.mkdir(parents=True)
        (self.source / 'SKILL.md').write_text('---\nname: skyrim-forge\ndescription: fixture\n---\nversion one\n', encoding='utf-8')
        legacy = self.root / 'integrations/skyrim-forge'
        legacy.mkdir()
        shutil.copy2(self.source / 'SKILL.md', legacy / 'SKILL.md')
        (self.root / 'INSTALLATION.json').write_text(json.dumps({'root': str(self.root), 'python': sys.executable}), encoding='utf-8')
        self.user, self.local, self.claude = (self.base / name for name in ('user', 'local', 'claude'))
        self.env = os.environ.copy()
        self.env.update(USERPROFILE=str(self.user), LOCALAPPDATA=str(self.local), CLAUDE_CONFIG_DIR=str(self.claude))
        self.target = self.claude / 'skills/skyrim-forge'

    def run_install(self, provider='Claude', script='Install-Skyrim-Pack.ps1', harness=None):
        path = self.root / script
        if harness:
            path = self.base / 'fault.ps1'
            path.write_text(harness + '\n& $args[0] -Provider $args[1]\n', encoding='utf-8-sig')
            args = [str(self.root / script), provider]
        else:
            args = ['-Provider', provider]
        return subprocess.run([str(PS), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(path), *args], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def good(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fresh_codex_uses_agents_even_with_custom_codex_home(self):
        self.env['CODEX_HOME'] = str(self.base / 'codex-config')
        self.good(self.run_install('Codex'))
        self.assertTrue((self.user / '.agents/skills/skyrim-forge/SKILL.md').is_file())
        self.assertFalse((self.base / 'codex-config/skills').exists())
        self.good(self.run_install('Codex', 'Install-Forge-Skill.ps1'))
        self.assertFalse((self.user / '.codex/skills').exists())

    def test_unknown_personal_skill_is_preserved(self):
        self.target.mkdir(parents=True)
        personal = b'---\nname: skyrim-forge\n---\nmy personal instructions\n'
        (self.target / 'SKILL.md').write_bytes(personal)
        result = self.run_install()
        self.good(result)
        self.assertEqual((self.target / 'SKILL.md').read_bytes(), personal)
        self.assertIn('preserv', result.stdout.lower())

    def test_edited_owned_skill_is_never_replaced(self):
        self.good(self.run_install())
        path = self.target / 'SKILL.md'
        path.write_bytes(path.read_bytes() + b'personal edit\n')
        personal = path.read_bytes()
        (self.target / 'personal.txt').write_text('keep', encoding='utf-8')
        (self.source / 'SKILL.md').write_text('new upstream version\n', encoding='utf-8')
        self.good(self.run_install())
        self.good(self.run_install(script='Install-Forge-Skill.ps1'))
        self.assertEqual(path.read_bytes(), personal)
        self.assertTrue((self.target / 'personal.txt').is_file())

    def test_owned_upgrade_keeps_recoverable_backup_outside_index(self):
        self.good(self.run_install())
        old = (self.target / 'SKILL.md').read_bytes()
        (self.source / 'SKILL.md').write_bytes(old + b'upstream update\n')
        self.good(self.run_install())
        self.assertEqual((self.target / 'SKILL.md').read_bytes(), old + b'upstream update\n')
        backups = [p for p in self.base.rglob('SKILL.md') if 'backup-' in str(p) and p.read_bytes() == old]
        self.assertTrue(backups, 'last-known-good payload was discarded')
        self.assertTrue(all(self.claude / 'skills' not in p.parents for p in backups))

    def test_active_hermes_profile_resolves_real_home(self):
        home = self.base / 'hermes'
        profile = home / 'profiles/code'
        profile.mkdir(parents=True)
        config = home / 'config.yaml'
        config.write_bytes(b'model:\n  default: personal-model\n')
        self.env['HERMES_HOME'] = str(profile)
        self.good(self.run_install('Hermes'))
        self.assertTrue((home / 'skills/skyrim-forge/SKILL.md').is_file())
        self.assertFalse((profile / 'skills').exists())
        self.assertEqual(config.read_bytes(), b'model:\n  default: personal-model\n')

    def test_antigravity_home_matches_general_bundle(self):
        self.env['ANTIGRAVITY_HOME'] = str(self.base / 'ag-correct')
        self.env['ANTIGRAVITY_CONFIG_DIR'] = str(self.base / 'ag-legacy')
        self.good(self.run_install('Antigravity'))
        self.assertTrue((self.base / 'ag-correct/skills/skyrim-forge/SKILL.md').is_file())
        self.assertFalse((self.base / 'ag-legacy').exists())

    def test_failed_swap_restores_previous_payload(self):
        self.good(self.run_install())
        old = (self.target / 'SKILL.md').read_bytes()
        (self.source / 'SKILL.md').write_bytes(old + b'upstream update\n')
        harness = r'''
function Move-Item {
    param($LiteralPath, $Destination, [switch]$Force)
    if ($LiteralPath -like '*stage-*' -and (Split-Path -Leaf $Destination) -eq 'skyrim-forge') { throw 'injected swap failure' }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
}
'''
        result = self.run_install(harness=harness)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('injected swap failure', result.stderr)
        self.assertEqual((self.target / 'SKILL.md').read_bytes(), old)

    def test_failed_restore_retains_the_only_backup(self):
        self.good(self.run_install())
        old = (self.target / 'SKILL.md').read_bytes()
        (self.source / 'SKILL.md').write_bytes(old + b'upstream update\n')
        harness = r'''
function Move-Item {
    param($LiteralPath, $Destination, [switch]$Force)
    if ($LiteralPath -like '*stage-*' -or $LiteralPath -like '*backup-*') { throw 'injected write and restore failure' }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
}
'''
        result = self.run_install(harness=harness)
        self.assertNotEqual(result.returncode, 0)
        backups = [p for p in self.base.rglob('SKILL.md') if 'backup-' in str(p) and p.read_bytes() == old]
        self.assertTrue(backups, result.stdout + result.stderr)


    def prepare_old_tooling(self, owned=True):
        old=self.source.parent/'ai-tooling-stack'; old.mkdir()
        (old/'SKILL.md').write_text('old Forge tooling index\n', encoding='utf-8')
        if owned: self.good(self.run_install())
        else:
            target=self.claude/'skills/ai-tooling-stack'; target.mkdir(parents=True)
            shutil.copy2(old/'SKILL.md',target/'SKILL.md')
        old.rename(old.with_name('skyrim-tooling-stack'))
        return self.claude/'skills/ai-tooling-stack'

    def test_old_forge_tooling_name_migrates_with_own_digest_proof(self):
        target=self.prepare_old_tooling()
        old=(target/'SKILL.md').read_bytes()
        self.good(self.run_install())
        self.assertFalse(target.exists())
        self.assertTrue((self.claude/'skills/skyrim-tooling-stack/SKILL.md').is_file())
        backups=[p for p in self.base.rglob('SKILL.md') if 'backup-ai-tooling-stack-' in str(p)]
        self.assertTrue(backups)
        self.assertEqual(backups[0].read_bytes(),old)
        self.assertTrue(all(self.claude/'skills' not in p.parents for p in backups))

    def test_edited_old_tooling_name_is_preserved(self):
        target=self.prepare_old_tooling()
        (target/'SKILL.md').write_text('personal changes\n',encoding='utf-8')
        self.good(self.run_install())
        self.assertEqual((target/'SKILL.md').read_text(),'personal changes\n')

    def test_unowned_old_tooling_name_is_preserved(self):
        target=self.prepare_old_tooling(owned=False)
        self.good(self.run_install())
        self.assertTrue((target/'SKILL.md').is_file())

    def test_migration_rolls_back_if_ledger_commit_fails(self):
        target=self.prepare_old_tooling()
        old=(target/'SKILL.md').read_bytes()
        harness=r'''
function Move-Item {
    param($LiteralPath,$Destination,[switch]$Force)
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
    if ((Split-Path -Leaf $LiteralPath) -eq 'ai-tooling-stack') {
        $ledger=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Skyrim-Forge\managed-skills') -Filter '*.json' | Select-Object -First 1
        $global:blockedLedger=[IO.File]::Open($ledger.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    }
}
'''
        result=self.run_install(harness=harness)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((target/'SKILL.md').read_bytes(),old)
        self.assertFalse((self.claude/'skills/skyrim-tooling-stack').exists())


if __name__ == '__main__':
    unittest.main()
