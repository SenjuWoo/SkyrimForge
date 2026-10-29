"""Cross-plugin winners, load-order resolution and SEQ generation against hand-built plugins (no game files)."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from skyrim_forge.conflicts import find_records, mo2_sources, parse_form_key, resolve_load_order
from skyrim_forge.errors import SafetyError, ValidationError
from skyrim_forge.seq import build_seq, start_game_quests


def sub(sig: str, data: bytes) -> bytes:
    return sig.encode() + struct.pack("<H", len(data)) + data


def rec(sig: str, form_id: int, subs: list[bytes], flags: int = 0, compress: bool = False) -> bytes:
    body = b"".join(subs)
    if compress:
        body, flags = struct.pack("<I", len(body)) + zlib.compress(body), flags | 0x00040000
    return struct.pack("<4sIIIIHH", sig.encode(), len(body), flags, form_id, 0, 44, 0) + body


def group(label: str, *records: bytes) -> bytes:
    body = b"".join(records)
    return struct.pack("<4sI4sIII", b"GRUP", 24 + len(body), label.encode(), 0, 0, 0) + body


def plugin(path: Path, masters: list[str], *groups: bytes, flags: int = 0) -> Path:
    subs = [sub("HEDR", struct.pack("<fII", 1.7, 0, 0x800))] + [part for m in masters for part in (sub("MAST", m.encode() + b"\0"), sub("DATA", bytes(8)))]
    path.write_bytes(rec("TES4", 0, subs, flags) + b"".join(groups))
    return path


def edid(name: str) -> bytes:
    return sub("EDID", name.encode() + b"\0")


class LoadOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        plugin(self.dir / "A.esm", [], group("KYWD", rec("KYWD", 0x800, [edid("KwA"), sub("CNAM", b"\x01\x02\x03\x04")], compress=True)), flags=0x1)
        plugin(self.dir / "B.esp", ["A.esm"],
               group("KYWD", rec("KYWD", 0x00000800, [edid("KwA"), sub("CNAM", b"\x09\x09\x09\x09")]),
                     rec("KYWD", 0x01000800, [edid("KwB")])))
        plugin(self.dir / "C.esp", ["A.esm", "B.esp"], group("KYWD", rec("KYWD", 0x00000800, [edid("KwA"), sub("CNAM", b"\x09\x09\x09\x09")], flags=0x20)))
        plugin(self.dir / "L.esl", ["A.esm"], group("KYWD", rec("KYWD", 0x01000801, [edid("KwLight")])), flags=0x200)
        (self.dir / "plugins.txt").write_text("*C.esp\n*B.esp\n*L.esl\n*A.esm\n", encoding="utf-8")

    def order(self):
        return resolve_load_order(self.dir / "plugins.txt", [self.dir])

    def test_resolution_orders_masters_first_and_indexes_light_separately(self):
        order = self.order()
        self.assertEqual([p.name for p in order["plugins"]], ["A.esm", "C.esp", "B.esp", "L.esl"])
        self.assertEqual([p.load_index for p in order["plugins"]], ["00", "01", "02", "FE000"])
        self.assertIn("skyrim.esm", [m.casefold() for m in order["missing"]])

    def test_winner_chain_and_changed_subrecords(self):
        result = find_records(self.order(), editor_id="kwa", signature="KYWD")
        row = result["records"][0]
        self.assertEqual((row["winner"], row["overrides"], row["conflict"]), ("B.esp", 2, True))  # C loads before B in this plugins.txt
        self.assertEqual([c["plugin"] for c in row["chain"]], ["A.esm", "C.esp", "B.esp"])
        self.assertEqual(row["chain"][1]["changed_subrecords"], ["CNAM"])
        self.assertTrue(row["chain"][1]["deleted"])
        self.assertEqual((row["chain"][2]["changed_subrecords"], row["chain"][2]["itm_candidate"]), ([], True))

    def test_form_key_lookup_and_new_record_has_no_conflict(self):
        by_key = find_records(self.order(), form_key="0x800~A.esm")["records"][0]
        self.assertEqual((by_key["editor_id"], len(by_key["chain"])), ("KwA", 3))
        own = find_records(self.order(), editor_id="KwB")["records"][0]
        self.assertEqual((own["conflict"], own["origin_plugin"], own["chain"][0]["role"]), (False, "B.esp", "origin"))

    def test_light_plugin_local_ids_are_twelve_bit(self):
        light = find_records(self.order(), editor_id="KwLight")["records"][0]
        self.assertEqual(light["form_key"], "0x801~l.esl")

    def test_dump_reports_text_and_resolved_form_keys(self):
        winner = find_records(self.order(), editor_id="KwB", dump=True)["records"][0]["winner_subrecords"]
        self.assertEqual(winner[0], {"sig": "EDID", "size": 4, "hex": winner[0]["hex"], "text": "KwB"})

    def test_needs_a_selector_and_a_valid_form_key(self):
        with self.assertRaises(ValidationError):
            find_records(self.order())
        with self.assertRaises(ValidationError):
            parse_form_key("not a key")
        self.assertEqual(parse_form_key("Skyrim.esm|12EB7"), ("skyrim.esm", 0x12EB7))

    def test_mo2_instance_priority_and_bytearray_values(self):
        instance = self.dir / "inst"
        (instance / "mods/High").mkdir(parents=True)
        (instance / "mods/Low").mkdir()
        (instance / "profiles/Default").mkdir(parents=True)
        (instance / "overwrite").mkdir()
        (instance / "ModOrganizer.ini").write_text(f"﻿[General]\nselected_profile=@ByteArray(Default)\ngamePath=@ByteArray({self.dir.as_posix()}/game/)\n", encoding="utf-8")
        (instance / "profiles/Default/modlist.txt").write_text("# generated\n+High\n-Off\n+Low\n", encoding="utf-8")
        (instance / "profiles/Default/plugins.txt").write_text("*A.esm\n", encoding="utf-8")
        plugin(instance / "mods/High/A.esm", [], flags=0x1)
        plugin(instance / "mods/Low/A.esm", [], flags=0x1)
        source = mo2_sources(instance)
        self.assertEqual([r.name for r in source["roots"][:3]], ["overwrite", "High", "Low"])
        order = resolve_load_order(source["plugins_file"], source["roots"])
        self.assertIn("High", str(order["plugins"][0].path))


class SeqTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        dnam = lambda flags: sub("DNAM", struct.pack("<HBBII", flags, 50, 0, 0, 0))
        self.plugin = plugin(self.dir / "Q.esp", ["Skyrim.esm"], group("QUST",
            rec("QUST", 0x01000800, [edid("OwnStart"), dnam(0x11)]),
            rec("QUST", 0x01000801, [edid("OwnQuiet"), dnam(0x00)]),
            rec("QUST", 0x00012345, [edid("Override"), dnam(0x11)], compress=True)))

    def test_only_defined_start_enabled_quests_are_listed(self):
        self.assertEqual(start_game_quests(self.plugin.read_bytes()), [0x01000800])

    def test_build_requires_approval_writes_form_ids_and_refuses_overwrite(self):
        with self.assertRaises(SafetyError):
            build_seq(self.plugin, self.dir / "out", approved=False)
        result = build_seq(self.plugin, self.dir / "out", approved=True)
        self.assertEqual((self.dir / "out/Seq/Q.seq").read_bytes(), struct.pack("<I", 0x01000800))
        self.assertEqual(result["quests"], 1)
        with self.assertRaises(SafetyError):
            build_seq(self.plugin, self.dir / "out", approved=True)

    def test_plugin_without_start_quests_writes_nothing(self):
        empty = plugin(self.dir / "E.esp", [], group("QUST", rec("QUST", 0x800, [edid("Q"), sub("DNAM", struct.pack("<HBBII", 0, 0, 0, 0, 0))])))
        self.assertEqual(build_seq(empty, self.dir / "out", approved=True)["result"], "NOTHING_TO_WRITE")
        self.assertFalse((self.dir / "out/Seq").exists())


if __name__ == "__main__":
    unittest.main()
