# Audio container engineering

Forge owns the Skyrim voice container layer with the standard library, so an agent never hand-writes struct code against a live mod. Codec work stays external and hash-pinned.

## Formats

| Format | Shape | Forge evidence |
|---|---|---|
| `.fuz` | 12-byte `FUZE` header: magic, `uint32` version 1, `uint32` lip size, then `.lip` bytes, then `.xwm` | header, lip size, payload hash, embedded XWM facts |
| `.xwm` | RIFF `XWMA` container with `fmt ` and `dpds` chunks | format tag, channels, sample rate, bits, packet table |
| `.wav` | PCM | channels, sample rate, bits, frames, voice readiness |
| `.lip` | FaceFX track | presence and size only |

Skyrim voice expects 16-bit PCM at 44100 Hz, mono or stereo. `audio-inspect` reports `voice_ready` for a WAV that meets it and never claims playback quality.

## Commands

```text
forge audio-inspect <file>
forge audio-extract-fuz <file.fuz> <output-dir> --approve
forge audio-create-fuz <file.xwm> <file.fuz> [--lip <file.lip>] --approve
forge voice-path-validate <mod-root>
```

Extraction and packing write only inside the Forge workspace, refuse to overwrite an existing payload, and read the written bytes back before reporting PASS.

## Voice layout

Voice payloads belong at `Sound/Voice/<Plugin.esp|esm|esl>/<VoiceType>/<Topic_Response>.fuz`. `voice-path-validate` reports a missing plugin-named folder or a non-audio suffix as an error, and a deeper nesting as a warning. It checks the path layout only: it does not prove that a plugin's `INFO` records reference these files, and it cannot judge dialogue timing.

## External boundary

WAV-to-XWM transcoding and `.lip` generation need pinned tools, not Forge:

- `audio.xwma.encode` → `xWMAEncode.exe` (Microsoft SDK component, configure-only)
- `audio.lip.generate` → `FaceFXWrapper.exe` or `LipGen.exe`

Use `forge tool-scan`, `forge tool-configure` and `forge tool-resolve` with those capabilities. Forge pins the SHA-256 and never bundles them.
