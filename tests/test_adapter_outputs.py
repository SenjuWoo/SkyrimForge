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

    # Option tables copied from the real binaries: 1.0.1 prints this help (exit 1);
    # 1.3.2 adds --recursive and --debug-funcs (Orvid/Champollion main.cpp at v1.3.2).
    CHAMPOLLION_101 = ("HELP='''Champollion PEX decompiler V1.0.1:\n  -h [ --help ] Display the help message\n"
                       "  -a [ --asm ] arg Output assembly file\n  -p [ --psc ] arg Name of the output dir for psc decompilation\n"
                       "  -c [ --comment ] Output\n  -t [ --threaded ] Run decompilation in parallel mode'''\n")
    CHAMPOLLION_132 = CHAMPOLLION_101.replace("V1.0.1", "V1.3.2").replace("'''\n", "\n  -r [ --recursive ] Recursively scan\n  -d [ --debug-funcs ] Decompile debug functions'''\n")
    FAKE_BODY = ("argv=sys.argv[1:]\n"
                 "if '--help' in argv: print(HELP); sys.exit(1)\n"
                 "known={'-h','-a','-p','-c','-t'} | ({'-r','-d'} if 'V1.3.2' in HELP else set())\n"
                 "bad=[a for a in argv if a.startswith('-') and a not in known]\n"
                 "if bad: print(\"unrecognised option '\"+bad[0]+\"'\", file=sys.stderr); sys.exit(1)\n"
                 "pathlib.Path(argv[argv.index('-p')+1],'Example.psc').write_text('ScriptName Example')\n"
                 "pathlib.Path(argv[argv.index('-p')+1],'argv.txt').write_text(' '.join(argv))\n")

    def test_champollion_101_gets_only_options_it_accepts(self):
        self.worker('champollion', self.CHAMPOLLION_101 + self.FAKE_BODY)
        result = champollion_decompile(self.cfg, self.pex, self.workspace/'old', approved=True)
        self.assertEqual(result['result'], 'PASS')
        self.assertNotIn('-d', (self.workspace/'old'/'argv.txt').read_text().split())
        with self.assertRaisesRegex(ToolError, 'recursive'):
            champollion_decompile(self.cfg, self.pex, self.workspace/'old-r', approved=True, recursive=True)
        self.assertFalse((self.workspace/'old-r').exists())

    def test_champollion_132_keeps_debug_funcs_and_recursive(self):
        self.worker('champollion', self.CHAMPOLLION_132 + self.FAKE_BODY)
        champollion_decompile(self.cfg, self.pex, self.workspace/'new', approved=True, recursive=True)
        argv = (self.workspace/'new'/'argv.txt').read_text().split()
        self.assertIn('-d', argv); self.assertIn('-r', argv)

    def test_synthesis_exit_zero_requires_a_parseable_plugin(self):
        self.worker('synthesis_cli','')
        with self.assertRaises(ToolError): synthesis_run(self.cfg,self.settings,self.workspace/'empty',approved=True)
        self.worker('synthesis_cli',"pathlib.Path(sys.argv[sys.argv.index('--OutputDirectory')+1],'Patch.esp').write_bytes(b'not a plugin')")
        with self.assertRaises(ValueError): synthesis_run(self.cfg,self.settings,self.workspace/'invalid',approved=True)

if __name__=='__main__': unittest.main()
