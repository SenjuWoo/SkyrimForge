# Procedural assets and the free-tool map

Forge generates real Skyrim DDS textures with the Python standard library: no
paid tool, no external binary, no network. That closes the most common gap in
an AI-driven mod — a plugin or NIF references a texture that does not exist
yet.

## What Forge generates

`forge texture-generate <kind> <output.dds>` writes a deterministic DDS with a
full mip chain:

| Kind | What it is | Useful for |
|---|---|---|
| `solid` | one colour | placeholders, UI swatches, masks |
| `checker` | two-colour grid | UV/debug checks, tiling tests |
| `gradient` | vertical blend | skies, fades, masks |
| `noise` | seeded fBm value noise | grunge, terrain blends, roughness bases |
| `bricks` | offset rows with mortar | walls, floors, quick material studies |
| `normal` | tangent-space normal from an fBm height field | surface detail, placeholder normals |

Formats: `bc1` (DXT1, no alpha), `bc3` (DXT5, alpha), `rgba` (A8R8G8B8,
lossless). Sizes are powers of two from 8 to 2048. Every file is seeded, so the
same arguments produce the same bytes on every machine, and `texture-inspect`
reports the header, mip count and payload consistency of any DDS.

```powershell
forge texture-generate bricks mod/Textures/Architecture/stone.dds --size 512 --format bc1 --primary "#8a7f6a" --secondary "#3a352c" --preview mod/stone.png --approve
forge texture-generate normal mod/Textures/Architecture/stone_n.dds --size 512 --format bc1 --strength 2.5 --flip-green --approve
forge texture-inspect mod/Textures/Architecture/stone.dds
```

Notes that matter in practice:

- Normal maps are tangent-space with +Y up. Pass `--flip-green` for pipelines
  authored for DirectX-style green channels; record which convention the mod
  uses.
- BC1 ignores alpha; use `bc3` when the texture needs transparency.
- BC7, BC5 and BC6H are not encoded. Use the pinned `texconv` (MIT) from the
  tool vault when a project needs them.
- These are placeholders and utility maps. They are not art direction, and a
  file that loads is not a texture that looks right in game.

## Free tools for the gaps Forge does not fill

No step in this table needs a paid program. Forge never bundles these binaries;
they stay in the local tool vault with a SHA-256 pin, or the human runs them.

| Gap | Free tool | Licence | How it fits |
|---|---|---|---|
| Meshes, collision, rigs, NIF authoring | Blender + NIF exporter | GPL | Forge does not write meshes; export NIF, then `forge nif` checks and `nif-optimizer` converts |
| Hand painting, photo texturing | GIMP or Krita | GPL-3.0-or-later | source art; Forge generates placeholders only |
| Vector UI, icons, maps | Inkscape | GPL-3.0-or-later | export PNG, convert to DDS with `texconv` |
| PBR channel synthesis (normal/roughness/AO from height) | Materialize | free | Forge's `normal` kind is a rough stand-in |
| BC7/BC5/BC6H, colour-space conversion | texconv (DirectXTex) | MIT | pinned tool-vault capability |
| Asset optimisation, texture/archive normalisation | Cathedral Assets Optimizer | MPL-2.0 | pinned tool-vault capability |
| NIF conversion and cleanup | SSE NIF Optimizer | GPL-3.0 | pinned tool-vault capability |
| Audio editing, cleanup, mixing | Audacity | GPL | source audio; Forge inspects and packs FUZ |
| Audio conversion and loudness | FFmpeg | LGPL-2.1-or-later | WAV prep before `xWMAEncode` |
| WAV to XWM | xWMAEncode | free Microsoft SDK tool | pinned `audio.xwma.encode` |
| Lip-sync generation | FaceFXWrapper | free community tool | pinned `audio.lip.generate` |
| BSA/BA2 packing | BSArch | MPL-2.0 | pinned `archive.bsa.*` |
| Records, conflict checks | xEdit / SSEEdit | free, open source | Forge drives fixed scripts only |

The full licence and hash record lives in `references/TOOL-CATALOG.json`; query
`forge tool-resolve <capability>` before assuming a binary exists.

## Licence position

Textures produced by `texture-generate` are original output of this repository's
code — no third-party art is copied, and no licence from a paid product is
involved. Third-party tools are never redistributed with Forge, a FOMOD, a
GitHub release or a Nexus archive. The only paid software in the whole workflow
is Skyrim itself and the Creation Kit that ships with it.

## For agents

1. `forge capabilities` — confirm `asset.texture` is `direct` on this install.
2. `forge texture-generate … --approve` — write only inside the workspace.
3. `forge texture-inspect` — prove the header and mip chain.
4. Package through `forge release-build` / `forge fomod-build`; never hand-write
   DDS bytes or shell out to a paid converter.
