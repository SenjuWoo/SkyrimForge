"""Generate deterministic, dependency-free DDS textures and PNG previews.

Skyrim needs real DDS files, and an agent that has no art pipeline otherwise
stops at "make a texture". This module closes that gap with the standard
library only: procedural patterns, tangent-space normal maps from a height
field, mip chains, BC1/BC3 block compression, A8R8G8B8 fallback, and a PNG
preview for humans and vision models.

Everything is seeded and deterministic, writes only inside the Forge
workspace, and never pretends to be art direction: these are placeholders and
utility maps, not a replacement for Blender, GIMP or a human artist.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .safety import require_approval, require_within
from .util import atomic_write_bytes, sha256_bytes

DDS_MAGIC = b"DDS "
KINDS = ("solid", "checker", "gradient", "noise", "bricks", "normal")
FORMATS = ("bc1", "bc3", "rgba")
MAX_SIZE = 2048
DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH = 0x1, 0x2, 0x4
DDSD_PITCH, DDSD_PIXELFORMAT, DDSD_LINEARSIZE = 0x8, 0x1000, 0x80000
DDPF_ALPHAPIXELS, DDPF_FOURCC, DDPF_RGB = 0x1, 0x4, 0x40
DDSCAPS_COMPLEX, DDSCAPS_TEXTURE, DDSCAPS_MIPMAP = 0x8, 0x1000, 0x400000


# --------------------------------------------------------------------------- header

def _dds_header(width: int, height: int, mips: int, fmt: str) -> bytes:
    """Build a 128-byte legacy DDS header for one format."""
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT
    caps = DDSCAPS_TEXTURE | ((DDSCAPS_COMPLEX | DDSCAPS_MIPMAP) if mips > 1 else 0)
    if fmt == "rgba":
        flags |= DDSD_PITCH
        pitch = width * 4
        pf_flags, fourcc, bits = DDPF_RGB | DDPF_ALPHAPIXELS, 0, 32
        masks = (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    else:
        flags |= DDSD_LINEARSIZE
        block = 8 if fmt == "bc1" else 16
        pitch = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block
        pf_flags, fourcc, bits = DDPF_FOURCC, int.from_bytes(b"DXT1" if fmt == "bc1" else b"DXT5", "little"), 0
        masks = (0, 0, 0, 0)
    head = struct.pack("<7I", 124, flags, height, width, pitch, 0, mips)
    head += b"\0" * 44  # reserved1[11]
    head += struct.pack("<8I", 32, pf_flags, fourcc, bits, *masks)
    head += struct.pack("<5I", caps, 0, 0, 0, 0)
    return DDS_MAGIC + head


def _payload_sizes(width: int, height: int, mips: int, fmt: str) -> list[int]:
    sizes, w, h = [], width, height
    for _ in range(mips):
        if fmt == "rgba":
            sizes.append(w * h * 4)
        else:
            sizes.append(max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == "bc1" else 16))
        w, h = max(1, w // 2), max(1, h // 2)
    return sizes


# --------------------------------------------------------------------------- PNG preview

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _png(width: int, height: int, rgba: bytes) -> bytes:
    """Minimal 8-bit RGBA PNG; no filters, which keeps it deterministic everywhere."""
    rows = bytearray()
    stride = width * 4
    for y in range(height):
        rows.append(0)
        rows += rgba[y * stride:(y + 1) * stride]
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 6))
            + _png_chunk(b"IEND", b""))


# --------------------------------------------------------------------------- patterns

def _parse_color(value: str, default: str) -> tuple[int, int, int, int]:
    text = (value or default).strip().lstrip("#")
    if len(text) == 6:
        text += "FF"
    if len(text) != 8:
        raise ValidationError(f"Colour must be #RRGGBB or #RRGGBBAA, got {value!r}")
    try:
        channels = tuple(int(text[i:i + 2], 16) for i in range(0, 8, 2))
    except ValueError as exc:
        raise ValidationError(f"Colour has non-hex digits: {value!r}") from exc
    return channels  # type: ignore[return-value]


def _lerp(a: int, b: int, t: float) -> int:
    return max(0, min(255, round(a + (b - a) * t)))


def _mix(a: tuple[int, int, int, int], b: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
    return (_lerp(a[0], b[0], t), _lerp(a[1], b[1], t), _lerp(a[2], b[2], t), _lerp(a[3], b[3], t))


def _hash2(x: int, y: int, seed: int) -> float:
    n = (x * 374761393 + y * 668265263 + seed * 1274126177) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _value_noise(x: float, y: float, seed: int) -> float:
    xi, yi = math.floor(x), math.floor(y)
    fx, fy = x - xi, y - yi
    u, v = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash2(xi, yi, seed), _hash2(xi + 1, yi, seed)
    c, d = _hash2(xi, yi + 1, seed), _hash2(xi + 1, yi + 1, seed)
    return a * (1 - u) * (1 - v) + b * u * (1 - v) + c * (1 - u) * v + d * u * v


def _fbm(x: float, y: float, seed: int, octaves: int) -> float:
    total = norm = 0.0
    amp, freq = 0.5, 1.0
    for octave in range(octaves):
        total += amp * _value_noise(x * freq, y * freq, seed + octave * 101)
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm if norm else 0.0


def _pixels(kind: str, size: int, primary: tuple[int, int, int, int], secondary: tuple[int, int, int, int],
            seed: int, octaves: int, frequency: float, cells: int, strength: float, flip_green: bool) -> bytes:
    """Return one RGBA level for the requested pattern."""
    out = bytearray(size * size * 4)
    if kind == "normal":
        heights = [[_fbm(x / size * frequency, y / size * frequency, seed, octaves) for x in range(size)]
                   for y in range(size)]
        for y in range(size):
            for x in range(size):
                dx = (heights[y][(x + 1) % size] - heights[y][(x - 1) % size]) * 0.5
                dy = (heights[(y + 1) % size][x] - heights[(y - 1) % size][x]) * 0.5
                nx, ny, nz = -dx * strength, (dy if not flip_green else -dy) * strength, 1.0
                inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
                offset = (y * size + x) * 4
                out[offset] = int((nx * inv * 0.5 + 0.5) * 255)
                out[offset + 1] = int((ny * inv * 0.5 + 0.5) * 255)
                out[offset + 2] = int((nz * inv * 0.5 + 0.5) * 255)
                out[offset + 3] = 255
        return bytes(out)
    for y in range(size):
        for x in range(size):
            if kind == "solid":
                colour = primary
            elif kind == "checker":
                cell = max(1, size // max(1, cells))
                colour = primary if ((x // cell) + (y // cell)) % 2 == 0 else secondary
            elif kind == "gradient":
                colour = _mix(primary, secondary, y / max(1, size - 1))
            elif kind == "noise":
                colour = _mix(primary, secondary, _fbm(x / size * frequency, y / size * frequency, seed, octaves))
            elif kind == "bricks":
                rows = max(1, cells)
                row = y * rows // size
                brick_h = max(1, size // rows)
                brick_w = brick_h * 2
                shift = (brick_w // 2) if row % 2 else 0
                bx = (x + shift) % brick_w
                mortar = bx < 2 or (y % brick_h) < 2
                tint = 0.92 + 0.16 * _hash2(row, (x + shift) // brick_w, seed)
                colour = (secondary if mortar else
                          (_lerp(0, primary[0], tint), _lerp(0, primary[1], tint), _lerp(0, primary[2], tint), 255))
            else:  # pragma: no cover - guarded by KINDS
                raise ValidationError(f"Unsupported texture kind: {kind}")
            offset = (y * size + x) * 4
            out[offset:offset + 4] = bytes(colour)
    return bytes(out)


def _downsample(width: int, height: int, rgba: bytes) -> tuple[int, int, bytes]:
    """Box-filter one mip level, clamping at the edge for odd sizes."""
    nw, nh = max(1, width // 2), max(1, height // 2)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        y0, y1 = min(height - 1, y * 2), min(height - 1, y * 2 + 1)
        for x in range(nw):
            x0, x1 = min(width - 1, x * 2), min(width - 1, x * 2 + 1)
            acc = [0, 0, 0, 0]
            for sy in (y0, y1):
                base = (sy * width + x0) * 4
                for step in (0, (x1 - x0) * 4):
                    acc[0] += rgba[base + step]
                    acc[1] += rgba[base + step + 1]
                    acc[2] += rgba[base + step + 2]
                    acc[3] += rgba[base + step + 3]
            offset = (y * nw + x) * 4
            out[offset:offset + 4] = bytes(channel // 4 for channel in acc)
    return nw, nh, bytes(out)


# --------------------------------------------------------------------------- BC1/BC3

def _rgb565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def _from565(value: int) -> tuple[int, int, int]:
    return (((value >> 11) & 31) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31)


def _bc1_colour_block(rgba: bytes, width: int, height: int, x0: int, y0: int) -> bytes:
    pixels = []
    for y in range(4):
        for x in range(4):
            sx, sy = min(width - 1, x0 + x), min(height - 1, y0 + y)
            offset = (sy * width + sx) * 4
            pixels.append((rgba[offset], rgba[offset + 1], rgba[offset + 2]))
    hi = tuple(max(p[i] for p in pixels) for i in range(3))
    lo = tuple(min(p[i] for p in pixels) for i in range(3))
    c0, c1 = _rgb565(*hi), _rgb565(*lo)
    if c0 < c1 or (c0 == c1 and c0 != 0xFFFF):
        c0, c1 = c1, c0
    if c0 == c1:
        c1 = max(0, c0 - 1)
    palette = [_from565(c0), _from565(c1),
               tuple((2 * a + b) // 3 for a, b in zip(_from565(c0), _from565(c1))),
               tuple((a + 2 * b) // 3 for a, b in zip(_from565(c0), _from565(c1)))]
    indices = 0
    for index, pixel in enumerate(pixels):
        best = min(range(4), key=lambda i: sum((pixel[c] - palette[i][c]) ** 2 for c in range(3)))
        indices |= best << (index * 2)
    return struct.pack("<HHI", c0, c1, indices)


def _bc3_alpha_block(rgba: bytes, width: int, height: int, x0: int, y0: int) -> bytes:
    alphas = []
    for y in range(4):
        for x in range(4):
            sx, sy = min(width - 1, x0 + x), min(height - 1, y0 + y)
            alphas.append(rgba[(sy * width + sx) * 4 + 3])
    a0, a1 = max(alphas), min(alphas)
    if a0 == a1:
        palette = [a0] * 8
    else:
        palette = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    bits = 0
    for index, alpha in enumerate(alphas):
        best = min(range(8), key=lambda i: abs(alpha - palette[i]))
        bits |= best << (index * 3)
    return bytes([a0, a1]) + bits.to_bytes(6, "little")


def _compress_level(rgba: bytes, width: int, height: int, fmt: str) -> bytes:
    out = bytearray()
    for y0 in range(0, height, 4):
        for x0 in range(0, width, 4):
            if fmt == "bc3":
                out += _bc3_alpha_block(rgba, width, height, x0, y0)
            out += _bc1_colour_block(rgba, width, height, x0, y0)
    return bytes(out)


def _decode_bc1_colour(block: bytes) -> list[tuple[int, int, int]]:
    """Decode one BC1 colour block; exported for tests and sanity checks."""
    c0, c1, indices = struct.unpack("<HHI", block[:8])
    p0, p1 = _from565(c0), _from565(c1)
    if c0 > c1:
        palette = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)),
                   tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
    else:
        palette = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1)), (0, 0, 0)]
    return [palette[(indices >> (i * 2)) & 3] for i in range(16)]


# --------------------------------------------------------------------------- public API

def generate(kind: str, output: Path | str, *, workspace_root: Path, size: int = 512, fmt: str = "bc1",
             seed: int = 0, primary: str = "#808080", secondary: str = "#303030", octaves: int = 5,
             frequency: float = 4.0, cells: int = 8, strength: float = 2.0, flip_green: bool = False,
             preview: Path | str | None = None, approved: bool = False) -> dict[str, Any]:
    """Write one procedural DDS (and optional PNG preview) inside the workspace."""
    if kind not in KINDS:
        raise ValidationError(f"Unsupported texture kind {kind!r}; choose from {', '.join(KINDS)}")
    if fmt not in FORMATS:
        raise ValidationError(f"Unsupported format {fmt!r}; choose from {', '.join(FORMATS)}")
    if size < 8 or size > MAX_SIZE or size & (size - 1):
        raise ValidationError(f"Size must be a power of two between 8 and {MAX_SIZE}")
    if not 1 <= octaves <= 8:
        raise ValidationError("octaves must be between 1 and 8")
    require_approval(approved, f"generate {kind} texture at {output}")
    target = require_within(Path(output), workspace_root)
    preview_path = require_within(Path(preview), workspace_root) if preview else None
    mips = int(math.log2(size)) + 1
    pixels = _pixels(kind, size, _parse_color(primary, "#808080"), _parse_color(secondary, "#303030"),
                     seed, octaves, frequency, cells, strength, flip_green)
    levels: list[bytes] = []
    width, height, level = size, size, pixels
    for _ in range(mips):
        levels.append(level if fmt == "rgba" else _compress_level(level, width, height, fmt))
        if width == 1 and height == 1:
            break
        width, height, level = _downsample(width, height, level)
    payload = b"".join(levels)
    data = _dds_header(size, size, mips, fmt) + payload
    atomic_write_bytes(target, data)
    report: dict[str, Any] = {
        "result": "PASS", "kind": kind, "format": fmt, "size": [size, size], "mips": mips,
        "path": str(target), "bytes": len(data), "sha256": sha256_bytes(data),
        "seed": seed, "deterministic": True,
        "preview": None,
    }
    if preview_path is not None:
        png = _png(size, size, pixels)
        atomic_write_bytes(preview_path, png)
        report["preview"] = {"path": str(preview_path), "sha256": sha256_bytes(png)}
    return report


def inspect(path: Path | str) -> dict[str, Any]:
    """Read a DDS header and report format, mip chain and payload consistency."""
    target = Path(path).resolve(strict=True)
    data = target.read_bytes()
    if len(data) < 128 or data[:4] != DDS_MAGIC:
        raise ValidationError("Not a DDS file: missing the 128-byte DDS header")
    size, flags, height, width, pitch, depth, mips = struct.unpack_from("<7I", data, 4)
    if size != 124:
        raise ValidationError(f"Unexpected DDS header size {size}; Forge models 124")
    pf_flags, fourcc, bits, rmask, gmask, bmask, amask = struct.unpack_from("<8I", data, 76)[1:]
    if fourcc == int.from_bytes(b"DXT1", "little"):
        fmt = "bc1"
    elif fourcc == int.from_bytes(b"DXT5", "little"):
        fmt = "bc3"
    elif pf_flags & DDPF_RGB and bits == 32:
        fmt = "rgba"
    else:
        fmt = f"other(fourcc={fourcc},bits={bits},pf=0x{pf_flags:X})"
    mips = max(1, mips)
    expected = sum(_payload_sizes(width, height, mips, fmt)) if fmt in FORMATS else None
    actual = len(data) - 128
    return {
        "path": str(target), "size_bytes": len(data), "width": width, "height": height, "depth": depth,
        "mips": mips, "format": fmt, "fourcc": fourcc, "rgb_bits": bits,
        "masks": {"r": rmask, "g": gmask, "b": bmask, "a": amask},
        "linear_size": pitch if flags & DDSD_LINEARSIZE else None, "pitch": pitch if flags & DDSD_PITCH else None,
        "payload_bytes": actual, "expected_payload_bytes": expected,
        "payload_matches": expected is None or expected == actual,
        "sha256": sha256_bytes(data),
    }


def self_test() -> dict[str, Any]:
    """Deterministic regression fixture; does not touch a game or a live mod."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        first = generate("checker", root / "a.dds", workspace_root=root, size=32, fmt="bc1", approved=True)
        second = generate("checker", root / "b.dds", workspace_root=root, size=32, fmt="bc1", approved=True)
        same = first["sha256"] == second["sha256"]
        info = inspect(root / "a.dds")
        generate("solid", root / "s.dds", workspace_root=root, size=32, fmt="bc1", approved=True)
        normal = generate("normal", root / "n.dds", workspace_root=root, size=16, fmt="rgba",
                          preview=root / "n.png", approved=True)
        png = (root / "n.png").read_bytes()
        block = _decode_bc1_colour((root / "s.dds").read_bytes()[128:136])
        solid_ok = len(set(block)) == 1 and all(abs(c - 131) <= 3 for c in block[0])
        checks = {
            "deterministic": same,
            "header": info["format"] == "bc1" and info["mips"] == 6 and info["payload_matches"],
            "normal_and_preview": normal["preview"] is not None and png[:8] == b"\x89PNG\r\n\x1a\n",
            "solid_block": solid_ok,
        }
        return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
