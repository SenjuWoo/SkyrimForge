"""Prove runtime-only mod ZIPs, stable input bytes and safe output boundaries with real files."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from skyrim_forge.errors import SafetyError, ValidationError
from skyrim_forge.release import build_release, validate_release_tree

class RuntimePayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.workspace=Path(self.temp.name);self.root=self.workspace/'payload';self.root.mkdir()
        (self.root/'MyMod_english.txt').write_text('runtime translation')
        (self.root/'LICENSE.MyMod.txt').write_text('required licence')
    def test_runtime_text_and_licence_survive_without_developer_metadata(self):
        output=self.workspace/'product.zip'
        report=build_release(self.root,output,self.workspace,approved=True)
        self.assertEqual(report['result'],'PASS')
        with zipfile.ZipFile(output) as z:
            self.assertEqual(set(z.namelist()),{'MyMod_english.txt','LICENSE.MyMod.txt'})
            self.assertEqual(z.read('MyMod_english.txt'),b'runtime translation')
    def test_source_notes_and_changelogs_are_refused_including_nested_case_variants(self):
        for name in ('CHANGELOG.txt','Changelog.md','STATE.md','WORKSPACE_OWNERSHIP.md','README.txt','RIGHTS-MANIFEST.json'):
            with self.subTest(name=name):
                path=self.root/name;path.write_text('source metadata')
                self.assertEqual(validate_release_tree(self.root)['result'],'FAIL')
                path.unlink()
        folder=self.root/'TeStS';folder.mkdir();(folder/'private.txt').write_text('not read')
        self.assertEqual(validate_release_tree(self.root)['result'],'FAIL')
    def test_empty_payload_and_output_inside_payload_fail_before_creating_output(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(validate_release_tree(Path(td))['result'],'FAIL')
        output=self.root/'mod.zip'
        with self.assertRaisesRegex(SafetyError,'outside'):
            build_release(self.root,output,self.workspace,approved=True)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob('*.tmp')))
    def test_changed_validated_input_never_becomes_a_release_or_leaves_temp(self):
        original=validate_release_tree
        def change(root):
            report=original(root)
            (root/'MyMod_english.txt').write_text('changed after validation')
            return report
        output=self.workspace/'mod.zip'
        with patch('skyrim_forge.release.validate_release_tree',side_effect=change):
            with self.assertRaisesRegex(ValidationError,'changed after validation'):
                build_release(self.root,output,self.workspace,approved=True)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.workspace.glob('*.forge.tmp')))
    def test_concurrent_output_is_preserved(self):
        import skyrim_forge.release as release
        original=release.validate_release_tree
        output=self.workspace/'mod.zip'
        def create(root):
            report=original(root);output.write_bytes(b'other owner');return report
        with patch('skyrim_forge.release.validate_release_tree',side_effect=create):
            with self.assertRaises(SafetyError):
                build_release(self.root,output,self.workspace,approved=True)
        self.assertEqual(output.read_bytes(),b'other owner')

if __name__=='__main__':unittest.main()
