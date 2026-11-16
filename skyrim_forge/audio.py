"""Inspect, split and assemble Skyrim voice containers (FUZ/XWM/WAV) with the standard library.

Forge owns the container layer so an agent never hand-writes struct code against
a live mod. Encoding (WAV -> XWM) and lip-sync run the Creation Kit's own
xwmaencode.exe and LipGenerator.exe when they are pinned in the configuration.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import Any

from .errors import SafetyError, ValidationError
from .safety import require_approval, require_within
from .util import atomic_write_bytes, iter_files, sha256_bytes, utc_now

FUZ_MAGIC = b"FUZE"
FUZ_VERSION = 1
FUZ_HEADER = struct.Struct("<4sII")
AUDIO_SUFFIXES = {".fuz", ".xwm", ".wav", ".lip"}
VOICE_SUFFIXES = {".fuz", ".xwm"}
# WAVEFORMATEX tags that appear in Skyrim audio containers.
WAVE_FORMATS = {0x0001: "PCM", 0x0002: "ADPCM", 0x0011: "IMA ADPCM", 0x0161: "WMAudio2 (xWMA)", 0x0162: "WMAudio3", 0x0165: "WMAudio Lossless"}


def _riff_info(data: bytes) -> dict[str, Any]:
    """Parse a RIFF container far enough to name the format and packet table."""
    if len(data) < 12 or data[:4] != b"RIFF":
        raise ValidationError("Audio payload is not a RIFF container")
    form = data[8:12]
    chunks: list[str] = []
    fmt: dict[str, Any] = {}
    position = 12
    while position + 8 <= len(data):
        chunk_id = data[position:position + 4].decode("latin-1")
        size = struct.unpack_from("<I", data, position + 4)[0]
        payload = data[position + 8:position + 8 + size]
        chunks.append(chunk_id)
        if chunk_id == "fmt " and len(payload) >= 16:
            tag, channels, rate, avg_bytes, block_align, bits = struct.unpack_from("<HHIIHH", payload, 0)
            fmt = {"format_tag": f"0x{tag:04X}", "format": WAVE_FORMATS.get(tag, "unknown"), "channels": channels,
                   "sample_rate": rate, "avg_bytes_per_second": avg_bytes, "block_align": block_align,
                   "bits_per_sample": bits, "extra_bytes": max(0, len(payload) - 16)}
        position += 8 + size + (size & 1)  # RIFF chunks are word aligned
    if not fmt:
        raise ValidationError("RIFF container has no fmt chunk")
    return {"container": form.decode("latin-1"), "chunks": chunks, "has_packet_table": "dpds" in chunks, **fmt}


def _fuz_info(data: bytes) -> dict[str, Any]:
    if len(data) < FUZ_HEADER.size:
        raise ValidationError("FUZ file is shorter than its 12-byte header")
    magic, version, lip_size = FUZ_HEADER.unpack_from(data, 0)
    if magic != FUZ_MAGIC:
        raise ValidationError(f"Not a FUZ container: magic is {magic!r}")
    if version != FUZ_VERSION:
        raise ValidationError(f"Unsupported FUZ version {version}; Forge models version {FUZ_VERSION}")
    audio_offset = FUZ_HEADER.size + lip_size
    if audio_offset > len(data):
        raise ValidationError(f"FUZ lip_size {lip_size} exceeds the file size")
    payload = data[audio_offset:]
    try:
        audio = _riff_info(payload) if payload else {}
    except ValidationError as exc:
        audio = {"container": "invalid", "error": str(exc)}
    return {"format": "fuz", "version": version, "lip_size": lip_size, "has_lip_sync": lip_size > 0,
            "xwm_size": len(payload), "audio": audio, "payload_sha256": sha256_bytes(payload),
            "lip_sha256": sha256_bytes(data[FUZ_HEADER.size:audio_offset]) if lip_size else ""}


def inspect(path: Path) -> dict[str, Any]:
    """Report container and PCM facts for one .fuz, .xwm, .wav or .lip file."""
    target = path.resolve(strict=True)
    suffix = target.suffix.casefold()
    if suffix not in AUDIO_SUFFIXES:
        raise ValidationError(f"Unsupported audio file type: {target.suffix}")
    data = target.read_bytes()
    report: dict[str, Any] = {"path": str(target), "size": len(data), "sha256": sha256_bytes(data)}
    if suffix == ".fuz":
        report.update(_fuz_info(data))
    elif suffix == ".xwm":
        report.update({"format": "xwm", **_riff_info(data)})
    elif suffix == ".wav":
        with wave.open(str(target), "rb") as stream:
            frames = stream.getnframes()
            report.update({"format": "wav", "channels": stream.getnchannels(), "sample_rate": stream.getframerate(),
                           "bits_per_sample": stream.getsampwidth() * 8, "frames": frames,
                           "duration_seconds": round(frames / stream.getframerate(), 3) if stream.getframerate() else 0,
                           "compression": stream.getcomptype()})
    else:
        report.update({"format": "lip", "note": "FaceFX lip-sync track; Forge inspects presence and size, not phoneme content."})
    if report.get("format") in {"wav", "xwm"}:
        report["voice_ready"] = (report.get("format") == "wav" and report.get("channels") in {1, 2}
                                 and report.get("sample_rate") == 44100 and report.get("bits_per_sample") == 16)
        if report.get("format") == "wav" and not report["voice_ready"]:
            report["voice_ready_reason"] = "Skyrim voice expects 16-bit PCM at 44100 Hz, mono or stereo"
    return {"result": "PASS", "audio": report,
            "evidence": "Container and header facts only. Playback, loudness, lip timing and in-game dialogue behavior are not tested."}


def extract_fuz(path: Path, output_dir: Path, workspace_root: Path, *, approved: bool) -> dict[str, Any]:
    """Split one .fuz into its .lip (when present) and .xwm payload inside the workspace."""
    require_approval(approved, "FUZ extraction")
    source = path.resolve(strict=True)
    if source.suffix.casefold() != ".fuz":
        raise ValidationError("extract-fuz expects a .fuz file")
    target = require_within(output_dir, workspace_root)
    data = source.read_bytes()
    info = _fuz_info(data)
    lip = data[FUZ_HEADER.size:FUZ_HEADER.size + info["lip_size"]]
    xwm = data[FUZ_HEADER.size + info["lip_size"]:]
    written = []
    target.mkdir(parents=True, exist_ok=True)
    for suffix, payload in ((".lip", lip), (".xwm", xwm)):
        if not payload:
            continue
        destination = target / f"{source.stem}{suffix}"
        if destination.exists():
            raise SafetyError(f"Refusing to overwrite extracted payload: {destination}")
        atomic_write_bytes(destination, payload)
        if destination.read_bytes() != payload:
            raise SafetyError(f"Extracted payload readback mismatch: {destination}")
        written.append({"path": str(destination), "size": len(payload), "sha256": sha256_bytes(payload)})
    return {"result": "PASS", "source": str(source), "output_dir": str(target), "written": written, "container": info}


def create_fuz(xwm_path: Path, output: Path, workspace_root: Path, *, lip_path: Path | None = None, approved: bool) -> dict[str, Any]:
    """Pack an .xwm (and optional .lip) into a FUZ container inside the workspace."""
    require_approval(approved, "FUZ creation")
    audio = xwm_path.resolve(strict=True).read_bytes()
    if len(audio) < 12 or audio[:4] != b"RIFF":
        raise ValidationError("FUZ audio payload must be a RIFF/XWM stream")
    lip = lip_path.resolve(strict=True).read_bytes() if lip_path else b""
    target = require_within(output, workspace_root)
    if target.suffix.casefold() != ".fuz":
        raise ValidationError("FUZ output must use the .fuz suffix")
    if target.exists():
        raise SafetyError(f"Refusing to overwrite FUZ file: {target}")
    payload = FUZ_HEADER.pack(FUZ_MAGIC, FUZ_VERSION, len(lip)) + lip + audio
    atomic_write_bytes(target, payload)
    if target.read_bytes() != payload:
        raise SafetyError(f"FUZ readback mismatch: {target}")
    return {"result": "PASS", "output": str(target), "size": len(payload), "sha256": sha256_bytes(payload),
            "lip_size": len(lip), "xwm_size": len(audio), "container": _fuz_info(payload)}


def validate_voice_tree(root: Path) -> dict[str, Any]:
    """Check that a staged mod keeps voice files at Sound/Voice/<plugin>/<voice type>/<file>."""
    base = root.resolve(strict=True)
    if not base.is_dir():
        raise ValidationError("Voice validation needs a directory")
    voice_root = next((item for item in base.rglob("*") if item.is_dir() and item.name.casefold() == "voice"
                       and item.parent.name.casefold() == "sound"), None)
    errors: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    if voice_root is None:
        return {"result": "PASS", "root": str(base), "voice_files": 0, "files": [], "errors": [], "warnings": ["No Sound/Voice tree found; nothing to validate."],
                "evidence": "Path layout only. Voice file presence in a plugin's INFO records is not checked."}
    for path in iter_files(voice_root):
        rel = path.relative_to(voice_root).as_posix()
        parts = rel.split("/")
        row: dict[str, Any] = {"path": path.relative_to(base).as_posix(), "depth": len(parts)}
        if path.suffix.casefold() not in VOICE_SUFFIXES:
            errors.append(f"voice payload is not .fuz/.xwm: {row['path']}")
            row["status"] = "FAIL"
        elif len(parts) < 3:
            errors.append(f"voice payload is not under <plugin>/<voice type>/: {row['path']}")
            row["status"] = "FAIL"
        else:
            plugin = parts[0]
            if Path(plugin).suffix.casefold() not in {".esp", ".esm", ".esl"}:
                errors.append(f"voice folder is not named after a plugin: {row['path']}")
                row["status"] = "FAIL"
            elif len(parts) > 3:
                warnings.append(f"voice payload is nested deeper than <plugin>/<voice type>/: {row['path']}")
                row["status"] = "WARN"
            else:
                row["status"] = "PASS"
        rows.append(row)
    return {"result": "PASS" if not errors else "FAIL", "root": str(base), "voice_files": len(rows), "files": rows,
            "errors": sorted(set(errors)), "warnings": warnings, "generated_utc": utc_now(),
            "evidence": "Path layout only. Voice file presence in a plugin's INFO records and in-game dialogue timing are not checked."}


# --- encoding and lip-sync through the Creation Kit's own tools ----------------------------------------
# Tools/Audio/xwmaencode.exe: "XWMAENCODE [-b <N>] <InputFile> <OutputFile>" (its usage text).
# Tools/LipGen/LipGenerator/LipGenerator.exe: "LipGenerator wav text [-Language:..]" (its usage text); it writes
# <wav stem>.lip beside the WAV, so it runs on a private copy and the result is moved.
XWMA_BITRATES = (20000, 32000, 48000, 64000, 96000, 160000, 192000)
LIP_LANGUAGES = ("USEnglish", "French", "German")


def _voice_ready_wav(wav: Path) -> None:
    report = inspect(wav)
    if not report.get("audio", {}).get("voice_ready"):
        raise ValidationError(f"{wav.name} is not a voice-ready WAV (16-bit PCM mono): {report.get('audio')}")


def encode_xwm(config: Any, wav: Path, output: Path, *, approved: bool, bitrate: int | None = None) -> dict[str, Any]:
    from .tools import resolve_tool, run_process
    require_approval(approved, "XWM encoding")
    if bitrate is not None and bitrate not in XWMA_BITRATES:
        raise ValidationError(f"bitrate must be one of {XWMA_BITRATES}")
    target = require_within(output, config.workspace_root)
    if target.suffix.casefold() != ".xwm":
        raise ValidationError("XWM output must use the .xwm suffix")
    tool, exe = resolve_tool(config, "audio_xwma_encode", require_pin=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    args = (["-b", str(bitrate)] if bitrate else []) + [str(wav.resolve(strict=True)), str(target)]
    process = run_process(exe, args, cwd=target.parent, timeout_seconds=tool.timeout_seconds)
    if process["returncode"] != 0 or not target.is_file():
        raise ValidationError(f"xwmaencode failed: {(process['stdout'] + process['stderr'])[-400:]}")
    return {"result": "PASS", "wav": str(wav), "xwm": str(target), "size": target.stat().st_size, "sha256": sha256_bytes(target.read_bytes()),
            "container": inspect(target).get("audio")}


def generate_lip(config: Any, wav: Path, text: str, output: Path, *, approved: bool, language: str = "USEnglish") -> dict[str, Any]:
    import shutil
    import tempfile
    from .tools import resolve_tool, run_process
    require_approval(approved, "LIP generation")
    if language not in LIP_LANGUAGES:
        raise ValidationError(f"language must be one of {LIP_LANGUAGES}")
    if not text.strip():
        raise ValidationError("LIP generation needs the spoken text")
    target = require_within(output, config.workspace_root)
    if target.suffix.casefold() != ".lip":
        raise ValidationError("LIP output must use the .lip suffix")
    _voice_ready_wav(wav)
    tool, exe = resolve_tool(config, "audio_lip_generate", require_pin=True)
    with tempfile.TemporaryDirectory(prefix="forge-lip-") as temp:
        copy = Path(temp) / (target.stem + ".wav")
        shutil.copy2(wav, copy)
        process = run_process(exe, [str(copy), text, f"-Language:{language}"], cwd=exe.parent, timeout_seconds=tool.timeout_seconds)
        produced = copy.with_suffix(".lip")
        if not produced.is_file() or produced.stat().st_size == 0:
            raise ValidationError(f"LipGenerator wrote no .lip: {(process['stdout'] + process['stderr'])[-400:]}")
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, produced.read_bytes())
    return {"result": "PASS", "wav": str(wav), "lip": str(target), "size": target.stat().st_size, "language": language}


def generate_voice(config: Any, wav: Path, text: str, output: Path, *, approved: bool, language: str = "USEnglish", bitrate: int | None = None) -> dict[str, Any]:
    """WAV -> XWM (xwmaencode) + LIP (LipGenerator) -> FUZ in one command; intermediates stay in a private temp folder."""
    import tempfile
    require_approval(approved, "voice generation")
    target = require_within(output, config.workspace_root)
    if target.suffix.casefold() != ".fuz":
        raise ValidationError("voice output must use the .fuz suffix")
    if target.exists():
        raise SafetyError(f"Refusing to overwrite FUZ file: {target}")
    _voice_ready_wav(wav)
    with tempfile.TemporaryDirectory(prefix="forge-voice-", dir=config.workspace_root) as temp:
        stage = Path(temp)
        xwm = encode_xwm(config, wav, stage / "line.xwm", approved=True, bitrate=bitrate)
        lip = generate_lip(config, wav, text, stage / "line.lip", approved=True, language=language)
        packed = create_fuz(stage / "line.xwm", target, config.workspace_root, lip_path=stage / "line.lip", approved=True)
    unpacked = _fuz_info(target.read_bytes())
    return {"result": "PASS", "fuz": str(target), "size": packed["size"], "sha256": packed["sha256"], "xwm_size": xwm["size"],
            "lip_size": lip["size"], "language": language, "container": unpacked,
            "evidence": "Encoded and lip-synced by the Creation Kit's own tools and re-read as a FUZ; in-game playback and timing are not tested."}


def self_test() -> dict[str, Any]:
    """Prove FUZ pack/unpack round-trips and that path validation catches a bad layout."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="forge-audio-self-test-") as td:
        root = Path(td)
        # A minimal 16-bit 44100 Hz mono PCM WAV plus a fake XWM RIFF body.
        wav = root / "line.wav"
        with wave.open(str(wav), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(44100)
            stream.writeframes(b"\x00\x00" * 441)
        xwm = root / "line.xwm"
        body = b"XWMA" + b"fmt " + struct.pack("<I", 18) + struct.pack("<HHIIHH", 0x0161, 1, 44100, 8000, 2, 16) + b"\x00\x00" + b"dpds" + struct.pack("<I", 4) + b"\x00" * 4
        atomic_write_bytes(xwm, b"RIFF" + struct.pack("<I", 4 + len(body)) + body)
        lip = root / "line.lip"
        atomic_write_bytes(lip, b"LIP\x00")
        packed = create_fuz(xwm, root / "line.fuz", root, lip_path=lip, approved=True)
        extracted = extract_fuz(root / "line.fuz", root / "out", root, approved=True)
        voice = root / "mod" / "Sound" / "Voice" / "Test.esp" / "FemaleEvenToned"
        voice.mkdir(parents=True)
        atomic_write_bytes(voice / "Topic_0001.fuz", (root / "line.fuz").read_bytes())
        good = validate_voice_tree(root / "mod")
        bad = root / "bad" / "Sound" / "Voice" / "NoPluginFolder"
        bad.mkdir(parents=True)
        atomic_write_bytes(bad / "Topic_0001.fuz", b"FUZE")
        assertions = {
            "pack": packed["result"] == "PASS",
            "extract": extracted["result"] == "PASS",
            "round_trip": {row["sha256"] for row in extracted["written"]} == {sha256_bytes((root / "line.lip").read_bytes()), sha256_bytes((root / "line.xwm").read_bytes())},
            "wav_voice_ready": inspect(wav)["audio"]["voice_ready"] is True,
            "voice_path_pass": good["result"] == "PASS",
            "voice_path_fail": validate_voice_tree(root / "bad")["result"] == "FAIL",
        }
        return {"result": "PASS" if all(assertions.values()) else "FAIL", "assertions": assertions}
