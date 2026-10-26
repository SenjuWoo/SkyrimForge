"""Real child-process acceptance gates reject silent or stale external-tool output."""
from pathlib import Path
import json
import tempfile
import unittest
from skyrim_forge.config import ForgeConfig, ToolConfig, default_tools
from skyrim_forge.errors import ToolError
from skyrim_forge.tool_adapters import deadmesh_scan, champollion_decompile, synthesis_run
from skyrim_forge.util import sha256_file

class AdapterOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.workspace=self.root/'work'; self.workspace.mkdir()
        self.cfg=ForgeConfig(config_path=self.root/'config.toml',workspace_root=self.workspace,audit_log=self.root/'audit.jsonl',allow_external_processes=True,extra_read_roots=[self.root],tools=default_tools())
        self.source=self.root/'source'; self.source.mkdir()
        self.pex=self.source/'Example.pex'; self.pex.write_bytes(b'fixture')
        self.settings=self.source/'settings.json'; self.settings.write_text('{}')

    def worker(self,key,code):
        path=self.root/(key+'.py'); path.write_text('import pathlib,sys\n'+code,encoding='utf-8')
        self.cfg.tools[key]=ToolConfig(executable=path,sha256=sha256_file(path),timeout_seconds=20)

    def test_deadmesh_zero_outputs_and_stale_exact_prefix_fail(self):
        self.worker('deadmesh_cli','')
        with self.assertRaises(ToolError): deadmesh_scan(self.cfg,self.source,self.workspace/'report',approved=True)
        stale=self.workspace/'report.csv'; stale.write_text('old')
        with self.assertRaises(FileExistsError): deadmesh_scan(self.cfg,self.source,self.workspace/'report',approved=True)

    def test_deadmesh_requires_all_reports_but_allows_empty_defect_jsonl(self):
        self.worker('deadmesh_cli',"p=sys.argv[sys.argv.index('--out')+1]\nfor ext,text in [('.csv','mesh,verdict\\nExample.nif,OK'),('.jsonl',''),('.txt','No defects')]: pathlib.Path(p+ext).write_text(text)\n")
        self.assertEqual(deadmesh_scan(self.cfg,self.source,self.workspace/'report.csv',approved=True)['result'],'PASS')

    def test_champollion_zero_output_fails_and_fresh_script_passes(self):
        self.worker('champollion','')
        with self.assertRaises(ToolError): champollion_decompile(self.cfg,self.pex,self.workspace/'empty',approved=True)
        self.worker('champollion',"pathlib.Path(sys.argv[sys.argv.index('-p')+1],'Example.psc').write_text('ScriptName Example')")
        self.assertEqual(champollion_decompile(self.cfg,self.pex,self.workspace/'fresh',approved=True)['result'],'PASS')

    def test_synthesis_exit_zero_requires_a_parseable_plugin(self):
        self.worker('synthesis_cli','')
        with self.assertRaises(ToolError): synthesis_run(self.cfg,self.settings,self.workspace/'empty',approved=True)
        self.worker('synthesis_cli',"pathlib.Path(sys.argv[sys.argv.index('--OutputDirectory')+1],'Patch.esp').write_bytes(b'not a plugin')")
        with self.assertRaises(ValueError): synthesis_run(self.cfg,self.settings,self.workspace/'invalid',approved=True)

if __name__=='__main__': unittest.main()
