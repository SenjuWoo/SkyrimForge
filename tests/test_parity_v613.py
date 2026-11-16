"""6.13 parity features on synthetic fixtures: native BSA, PEX + diagnostics, NIF, data kinds, voice pipeline with
stand-in tools, deploy/undeploy, Creation Kit switches, check tiers, facts and routes, Nexus API shape, tool lock sync,
records worker guards and the Spriggit round-trip oracle. No game file is read."""
from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest import mock

from skyrim_forge import bsa, ck, datakinds, deploy, facts, nexus_api, nif, pex, records_worker, spriggit, tools_lock
from skyrim_forge.audio import generate_voice
from skyrim_forge.check import check
from skyrim_forge.cli import subcommands
from skyrim_forge.config import ForgeConfig, ToolConfig, default_tools
from skyrim_forge.errors import SafetyError, ValidationError
from skyrim_forge.frameworks import lint_file


def make_config(root: Path, **extra) -> ForgeConfig:
    workspace = root / "workspace"; workspace.mkdir(exist_ok=True)
    return ForgeConfig(config_path=root / "config" / "config.toml", workspace_root=workspace, audit_log=root / "audit.jsonl",
                       tools=default_tools(), **extra)


def plugin_bytes(records: list[tuple[bytes, int, bytes]]) -> bytes:
    """A minimal TES4 header plus one GRUP of records (signature, form id, EDID)."""
    hedr = b"HEDR" + struct.pack("<H", 12) + struct.pack("<fII", 1.71, len(records), 0x801)
    header = b"TES4" + struct.pack("<IIIIHH", len(hedr), 0, 0, 0, 44, 0) + hedr
    body = b""
    for signature, form_id, edid in records:
        payload = b"EDID" + struct.pack("<H", len(edid) + 1) + edid + b"\x00"
        body += signature + struct.pack("<IIIIHH", len(payload), 0, form_id, 0, 44, 0) + payload
    group = b"GRUP" + struct.pack("<I", 24 + len(body)) + records[0][0] + struct.pack("<IHHI", 0, 0, 0, 0) + body if records else b""
    return header + group


def nif_bytes(textures: list[str]) -> bytes:
    def sized(text: str) -> bytes:
        raw = text.encode(); return struct.pack("<I", len(raw)) + raw
    def short(text: str) -> bytes:
        raw = text.encode() + b"\x00"; return bytes((len(raw),)) + raw
    block = struct.pack("<i", len(textures)) + b"".join(sized(t) for t in textures)
    header = b"Gamebryo File Format, Version 20.2.0.7\n" + struct.pack("<IBII", 0x14020007, 1, 12, 1) + struct.pack("<I", 100)
    header += short("author") + short("") + short("export") + struct.pack("<H", 1) + sized("BSShaderTextureSet")
    header += struct.pack("<H", 0) + struct.pack("<I", len(block)) + struct.pack("<II", 0, 0) + struct.pack("<I", 0)
    return header + block + struct.pack("<II", 1, 0)


def pex_bytes(endian: str = ">", game: int = 1) -> bytes:
    def w(text: str) -> bytes:
        raw = text.encode(); return struct.pack(endian + "H", len(raw)) + raw
    out = struct.pack(endian + "I", pex.MAGIC) + bytes((3, 2)) + struct.pack(endian + "HQ", game, 0) + w("Test.psc") + w("user") + w("pc")
    out += struct.pack(endian + "H", 3) + w("MyQuestScript") + w("Quest") + w("hidden")
    out += b"\x00"  # no debug info
    out += struct.pack(endian + "H", 1) + struct.pack(endian + "H", 2) + b"\x00"  # one user flag
    object_data = struct.pack(endian + "H", 1) + b"\x00" * 6
    out += struct.pack(endian + "H", 1) + struct.pack(endian + "H", 0) + struct.pack(endian + "I", 4 + len(object_data)) + object_data
    return out


class NativeBsaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "src"
        files = {"meshes/test/a.nif": b"nif" * 400, "meshes/test/b.nif": os.urandom(300), "textures/test/a.dds": b"dds" * 999,
                 "scripts/MyScript.pex": pex_bytes()}
        for relative, payload in files.items():
            (self.source / relative).parent.mkdir(parents=True, exist_ok=True); (self.source / relative).write_bytes(payload)
        self.files = files

    def test_pack_read_extract_round_trip_for_lz4_zlib_and_stored(self):
        for version, compress in ((105, True), (105, False), (104, True)):
            out = self.root / f"t{version}{int(compress)}.bsa"
            report = bsa.pack(self.source, out, self.root, approved=True, compress=compress, version=version)
            self.assertEqual(report["files"], 4)
            archive = bsa.read(out, with_data=True)
            self.assertEqual({e.path: bsa.entry_bytes(archive, e) for e in archive.entries},
                             {k.replace("/", "\\").lower(): v for k, v in self.files.items()})
            self.assertTrue(bsa.verify_repack(out)["identical"])
            for row in archive.folders:
                self.assertEqual(row["hash"], bsa.tes_hash(row["name"], folder=True))

    def test_extract_writes_inside_the_workspace_only_with_approval(self):
        out = self.root / "x.bsa"; bsa.pack(self.source, out, self.root, approved=True)
        with self.assertRaises(Exception):
            bsa.extract(out, self.root / "o", self.root, approved=False)
        report = bsa.extract(out, self.root / "o", self.root, approved=True, only="textures")
        self.assertEqual(report["files"], 1)
        self.assertEqual((self.root / "o/textures/test/a.dds").read_bytes(), self.files["textures/test/a.dds"])

    def test_lz4_and_xxh32_known_answers(self):
        self.assertEqual(bsa.xxh32(b""), 0x02CC5D05)
        self.assertEqual(bsa.xxh32(b"abc"), 0x32D153FF)
        data = os.urandom(5000) + b"A" * 70000
        self.assertEqual(bsa.lz4_frame_decompress(bsa.lz4_frame_compress(data), len(data)), data)
        with self.assertRaises(ValidationError):
            bsa.lz4_frame_decompress(b"not a frame")


class PexAndDiagnosticsTests(unittest.TestCase):
    def test_reads_big_endian_skyrim_and_little_endian_fallout4(self):
        skyrim = pex.parse(pex_bytes(">", 1))
        self.assertEqual((skyrim["endian"], skyrim["game"], skyrim["version"]), ("big", "Skyrim", "3.2"))
        self.assertEqual(skyrim["objects"], [{"name": "MyQuestScript", "parent": "Quest"}])
        self.assertEqual(skyrim["user_flags"], ["hidden"])
        self.assertEqual(pex.parse(pex_bytes("<", 2))["endian"], "little")
        with self.assertRaises(ValidationError):
            pex.parse(b"\x00" * 16)

    def test_a_planted_error_gives_exactly_one_structured_diagnostic(self):
        official = "Starting 1 compile threads\nC:\\mods\\Test.psc(7,12): variable Foo is undefined\nNo output generated for Test.psc\n"
        found = pex.parse_diagnostics(official, "official")
        self.assertEqual(found, [{"file": "C:\\mods\\Test.psc", "line": 7, "column": 13, "severity": "error",
                                  "message": "variable Foo is undefined", "compiler": "official"}])
        caprica = "C:\\mods\\Test.psc (7, 12): Error: Unresolved identifier 'Foo'!\n"
        found = pex.parse_diagnostics(caprica, "caprica")
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["line"], found[0]["column"], found[0]["severity"]), (7, 12, "error"))
        self.assertEqual(pex.parse_diagnostics("C:\\x.psc (1, 2): Warning W4001: unused\n", "caprica")[0]["severity"], "warning")


class NifTests(unittest.TestCase):
    def test_header_blocks_and_texture_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mesh = root / "m.nif"; mesh.write_bytes(nif_bytes(["textures\\a\\b.dds", "a\\missing.dds"]))
            report = nif.info(mesh)
            self.assertEqual((report["game"], report["block_count"], report["size_ok"]), ("Skyrim SE", 1, True))
            (root / "data/textures/a").mkdir(parents=True); (root / "data/textures/a/b.dds").write_bytes(b"x")
            refs = nif.refs(mesh, data_roots=[root / "data"], archives=[])
            self.assertEqual(refs["missing"], 1)
            self.assertEqual({row["resolved"]: row["found"] for row in refs["textures"]}, {"textures\\a\\b.dds": True, "textures\\a\\missing.dds": False})
            (root / "bad.nif").write_bytes(b"not a nif")
            with self.assertRaises(ValidationError):
                nif.info(root / "bad.nif")


class DataKindTests(unittest.TestCase):
    def test_bodyslide_ini_and_quirks_as_warnings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); presets = root / "SliderPresets"; presets.mkdir(); groups = root / "SliderGroups"; groups.mkdir()
            (presets / "ok.xml").write_text('<SliderPresets><Preset name="P" set="CBBE"><SetSlider name="Breasts" size="big" value="50"/></Preset></SliderPresets>')
            (presets / "bad.xml").write_text('<SliderPresets><Preset name="P"><SetSlider name="X" size="huge" value="a"/></Preset></SliderPresets>')
            (groups / "g.xml").write_text('<SliderGroups><Group name="CBBE"><Member name="x"/></Group></SliderGroups>')
            (root / "flat.ini").write_text("bEnable=1\nfScale=abc\n")
            self.assertEqual(datakinds.validate(presets / "ok.xml")["result"], "PASS")
            self.assertEqual(datakinds.validate(presets / "bad.xml")["errors"], 2)
            self.assertEqual(datakinds.validate(groups / "g.xml")["result"], "PASS")
            flat = datakinds.validate(root / "flat.ini")
            self.assertEqual((flat["result"], {i["code"] for i in flat["issues"]}), ("PASS", {"INI-NO-SECTION", "INI-TYPE"}))
            (root / "x_DISTR.ini").write_text("Spell = 0x1\n")
            with self.assertRaises(ValidationError):
                datakinds.validate(root / "x_DISTR.ini")
            swap = root / "y_SWAP.ini"; swap.write_text("[Forms]\n0x00012EB7~Skyrim.esm|0x12EB8~Skyrim.esm\n")
            issues = lint_file(swap)
            self.assertEqual([i["severity"] for i in issues], ["warning"])


def write_fake_tool(path: Path, body: str) -> Path:
    path.write_text("import sys, shutil, pathlib\n" + body, encoding="utf-8")
    return path


class VoicePipelineTests(unittest.TestCase):
    def test_wav_to_fuz_with_stand_in_creation_kit_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); config = make_config(root, allow_external_processes=True)
            body = b"XWMA" + b"fmt " + struct.pack("<I", 18) + struct.pack("<HHIIHH", 0x0161, 1, 44100, 8000, 2, 16) + b"\x00\x00" + b"dpds" + struct.pack("<I", 4) + b"\x00" * 4
            riff = b"RIFF" + struct.pack("<I", 4 + len(body)) + body
            xwma = write_fake_tool(root / "xwmaencode.py", f"src, dst = sys.argv[-2:]\npathlib.Path(dst).write_bytes(bytes.fromhex('{riff.hex()}'))\n")
            lip = write_fake_tool(root / "LipGenerator.py", "wav = pathlib.Path(sys.argv[1]); assert sys.argv[2] and sys.argv[3].startswith('-Language:')\nwav.with_suffix('.lip').write_bytes(b'LIP-DATA')\n")
            for key, path in (("audio_xwma_encode", xwma), ("audio_lip_generate", lip)):
                config.tools[key] = ToolConfig(executable=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), timeout_seconds=60)
            wav = root / "line.wav"
            with wave.open(str(wav), "wb") as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(44100); stream.writeframes(b"\x00\x00" * 4410)
            out = config.workspace_root / "Sound/Voice/Test.esp/MaleNord/Topic_00000801_1.fuz"
            with self.assertRaises(Exception):
                generate_voice(config, wav, "Hello there.", out, approved=False)
            report = generate_voice(config, wav, "Hello there.", out, approved=True)
            data = out.read_bytes()
            self.assertEqual(data[:4], b"FUZE")
            self.assertEqual(struct.unpack_from("<I", data, 8)[0], len(b"LIP-DATA"))
            self.assertEqual(report["lip_size"], 8)


class DeployTests(unittest.TestCase):
    def test_dry_run_receipt_force_backup_and_exact_undeploy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data = root / "Data"; data.mkdir()
            config = make_config(root, skyrim_data=data)
            mod = root / "MyMod"; (mod / "meshes").mkdir(parents=True); (mod / "fomod").mkdir()
            (mod / "MyMod.esp").write_bytes(b"plugin"); (mod / "meshes/x.nif").write_bytes(b"mesh"); (mod / "fomod/info.xml").write_bytes(b"x")
            (data / "MyMod.esp").write_bytes(b"someone else's")
            plan = deploy.deploy(config, mod)
            self.assertTrue(plan["dry_run"]); self.assertEqual(plan["refused"], ["MyMod.esp"]); self.assertFalse((data / "meshes/x.nif").exists())
            with self.assertRaises(SafetyError):
                deploy.deploy(config, mod, approved=True)
            done = deploy.deploy(config, mod, approved=True, force=True)
            self.assertEqual(done["written"], 2)
            self.assertEqual((data / "MyMod.esp").read_bytes(), b"plugin")
            self.assertFalse((data / "fomod").exists())
            (data / "meshes/x.nif").write_bytes(b"edited after deploy")
            undo = deploy.undeploy(config, "MyMod", approved=True)
            self.assertEqual(undo["skipped_changed"], ["meshes/x.nif"])
            self.assertEqual((data / "MyMod.esp").read_bytes(), b"someone else's")
            self.assertEqual((data / "meshes/x.nif").read_bytes(), b"edited after deploy")


class CreationKitTests(unittest.TestCase):
    def test_switches_come_from_the_executable_and_runs_are_dry_until_approved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data = root / "Data"; data.mkdir(); (data / "Mod.esp").write_bytes(b"x")
            (root / "CreationKit.exe").write_bytes(b"MZ\x00-GenerateLips\x00junk\x00-ExportFaceGenData\x00-NotAReal\x00")
            config = make_config(root, skyrim_data=data)
            self.assertEqual(ck.switches(root / "CreationKit.exe"), ["ExportFaceGenData", "GenerateLips"])
            report = ck.run(config, "GenerateLips", "Mod.esp")
            self.assertEqual((report["dry_run"], report["argv"]), (True, ["CreationKit.exe", "-GenerateLips:Mod.esp"]))
            with self.assertRaises(ValidationError):
                ck.run(config, "GenerateSEQ", "Mod.esp")
            with self.assertRaises(ValidationError):
                ck.run(config, "GenerateLips", "Missing.esp")


class CheckTierTests(unittest.TestCase):
    def test_static_compiled_packaged_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            mod = Path(temp) / "Mod"; (mod / "Scripts/Source").mkdir(parents=True); (mod / "meshes").mkdir()
            (mod / "Mod.esp").write_bytes(plugin_bytes([(b"MISC", 0x800, b"Thing")]))
            (mod / "Scripts/Source/A.psc").write_text("ScriptName A")
            (mod / "meshes/m.nif").write_bytes(nif_bytes(["textures\\x.dds"]))
            report = check(mod)
            self.assertEqual(report["evidence"], {"static": "PASS", "compiled": "FAIL", "packaged": "NOT RUN", "runtime": "NOT RUN"})
            (mod / "Scripts/A.pex").write_bytes(pex_bytes())
            self.assertEqual(check(mod)["evidence"]["compiled"], "PASS")


class FactsAndPlanTests(unittest.TestCase):
    def test_every_fact_is_tiered_and_every_route_command_exists(self):
        document = facts.load_facts()
        self.assertEqual(facts.validate(document), [])
        commands = set(subcommands())
        missing = [c for route in document["routes"] for c in route["commands"] if c not in commands]
        self.assertEqual(missing, [])
        self.assertTrue(all(page["nexus"] > 0 for page in document["pages"]))

    def test_unverified_or_secondary_facts_cannot_enforce(self):
        self.assertEqual(facts.require("creation_kit.switches")["tier"], "installed")
        with self.assertRaises(ValidationError):
            facts.require("creation_kit.argument_form")
        bad = {"facts": [{"id": "x", "claim": "c", "tier": "rumour", "source": "s", "checked": "d", "recheck": "ls"}]}
        self.assertTrue(facts.validate(bad))

    def test_plan_ranks_routes(self):
        plan = facts.plan("I need a voice line with lip sync", set(subcommands()))
        self.assertEqual(plan["routes"][0]["goal"], "make a voice line")
        self.assertTrue(all(c["available"] for c in plan["routes"][0]["commands"]))


class NexusApiTests(unittest.TestCase):
    def test_query_shapes_with_a_stub_transport(self):
        def opener(request, timeout):
            body = json.loads(request.data)
            if "legacyModsByDomain" in body["query"]:
                payload = {"data": {"legacyModsByDomain": {"nodes": [{"name": "SkyUI", "modId": 12604, "version": "5.2"}]}}}
            else:
                payload = {"data": {"mods": {"nodes": [{"name": "SkyUI", "modId": 12604}]}}}
            return io.BytesIO(json.dumps(payload).encode())
        self.assertEqual(nexus_api.mod(12604, opener=opener)["url"], "https://www.nexusmods.com/skyrimspecialedition/mods/12604")
        self.assertEqual(nexus_api.find("SkyUI", opener=opener)["count"], 1)
        with self.assertRaises(ValidationError):
            nexus_api.mod(0)


class ToolLockTests(unittest.TestCase):
    def test_bind_existing_then_second_sync_downloads_nothing_and_download_checks_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.dict(os.environ, {"USERPROFILE": str(root), "HOME": str(root), "UABS_TOOL_ROOTS": str(root / "reuse")}):
                config = make_config(root)
                pin = root / "reuse/Tool 1.0/tool.exe"; pin.parent.mkdir(parents=True); pin.write_bytes(b"tool-binary")
                digest = hashlib.sha256(b"tool-binary").hexdigest()
                lock = {"tools": [{"id": "caprica", "config_key": "caprica", "repo": "o/r", "tag": "1.0", "asset": "t.zip", "asset_sha256": "0" * 64,
                                   "folder": "Tool 1.0", "pin_file": "tool.exe", "pin_sha256": digest, "safe_tools": "T | https://x | 1 | safe | test"}]}
                with mock.patch.object(tools_lock, "save_config"), mock.patch.object(tools_lock, "_download", side_effect=AssertionError("no download")):
                    first = tools_lock.sync(config, approved=True, lock=lock)
                    self.assertEqual((first["tools"][0]["action"], first["downloaded_bytes"]), ("bind-existing", 0))
                    self.assertEqual(config.tools["caprica"].executable, pin)
                    second = tools_lock.sync(config, approved=True, lock=lock)
                    self.assertEqual(second["downloaded_bytes"], 0)
                pin.unlink()
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr("wrap/tool.exe", b"tool-binary")
                lock["tools"][0]["asset_sha256"] = hashlib.sha256(archive.getvalue()).hexdigest()
                def fake_download(url, target):
                    target.write_bytes(archive.getvalue()); return len(archive.getvalue())
                config.tools["caprica"] = ToolConfig()
                with mock.patch.object(tools_lock, "save_config"), mock.patch.object(tools_lock, "_download", side_effect=fake_download):
                    third = tools_lock.sync(config, approved=True, lock=lock)
                    self.assertEqual(third["tools"][0]["action"], "download")
                    self.assertTrue((tools_lock.tools_root(config) / "Tool 1.0/tool.exe").is_file())
                    fourth = tools_lock.sync(config, approved=True, lock=lock)
                    self.assertEqual((fourth["tools"][0]["action"], fourth["downloaded_bytes"]), ("present", 0))
                lock["tools"][0]["asset_sha256"] = "f" * 64
                (tools_lock.tools_root(config) / "tools.receipt.json").unlink()
                import shutil; shutil.rmtree(tools_lock.tools_root(config) / "Tool 1.0")
                with mock.patch.object(tools_lock, "save_config"), mock.patch.object(tools_lock, "_download", side_effect=fake_download):
                    with self.assertRaises(SafetyError):
                        tools_lock.sync(config, approved=True, lock=lock)

    def test_shipped_lock_is_complete(self):
        self.assertEqual({t["id"] for t in tools_lock.load_lock()["tools"]}, {"spriggit", "caprica", "champollion", "pynifly"})


class WorkerAndSpriggitTests(unittest.TestCase):
    def test_worker_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            config = make_config(Path(temp))
            self.assertEqual(records_worker.status(config)["built"], False)
            with self.assertRaises(Exception):
                records_worker.call(config, {"verb": "version"})
            exe = records_worker.worker_exe(config); exe.parent.mkdir(parents=True); exe.write_bytes(b"MZ")
            (exe.parent / "worker.receipt.json").write_text(json.dumps({"exe_sha256": "0" * 64}))
            with self.assertRaises(SafetyError):
                records_worker.call(config, {"verb": "version"})
            with self.assertRaises(SafetyError):
                records_worker.build(config, approved=True)
            with self.assertRaises(ValidationError):
                records_worker.write_target(config, str(config.workspace_root / "x.txt"), True, "new record")

    def test_spriggit_round_trip_oracle(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "a.esp"; path.write_bytes(plugin_bytes([(b"MISC", 0x800, b"Coin"), (b"MISC", 0x801, b"Gem")]))
            self.assertEqual(spriggit.record_index(path), {"00000800": ("MISC", "Coin"), "00000801": ("MISC", "Gem")})

    def test_worker_source_pins_mutagen(self):
        project = (records_worker.source_dir() / "SkyrimForge.Records.csproj").read_text(encoding="utf-8")
        self.assertIn('Include="Mutagen.Bethesda.Skyrim" Version="0.54.4"', project)
        self.assertTrue((records_worker.source_dir() / "packages.lock.json").is_file())


if __name__ == "__main__":
    unittest.main()
