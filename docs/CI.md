# Continuous integration

Skyrim Forge separates compatibility tests from release reproducibility.

- `python` matrix jobs run the `python` validation scope. They test parsing, unit tests, packaging, MCP, and repository hygiene across supported Python and operating-system combinations. They intentionally do not rebuild the native helper.
- `preflight` fetches full history and tags and runs `scripts/preflight.py`, so version mirrors, control characters, the complete manifest and the release state are checked on every push. The release job re-runs it with `--release` to require a clean, taggable tree.
- `VALIDATION.json` and `BUILD-RECEIPT.json` contain only deterministic evidence (results, counts, hashes). Raw unittest/Go/MCP output remains in the CI log. A full run fails if any required category is `NOT-RUN`; the SBOM schema gate requires `jsonschema`.
- `native` jobs run Go formatting, vet, unit tests, and the race detector with Go 1.27.3.
- `repository-validation` is the sole byte-for-byte publication gate. It installs the exact Go 1.27.3 toolchain used for the bundled binaries and runs the full validator.
- `windows-installer` uses an explicit setup-python interpreter and isolated temporary configuration, then tests legacy Papyrus migration and installer idempotence.

A different Go patch release can produce a valid executable with different bytes. Therefore native binary reproducibility must never depend on the changing toolchain preinstalled on a hosted runner.

All release helper builds also use `-buildvcs=false`. Go otherwise embeds the current Git revision and commit time when building inside a Git checkout. Public archives are commonly built from extracted source trees without `.git`, so allowing automatic VCS stamping would make identical source and toolchains produce different binaries in GitHub Actions.
