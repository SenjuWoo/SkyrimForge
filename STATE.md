# Forge 6.2.1 cache migration correction

- Goal: retain standalone/modular ownership, shared tools, private work/settings and a correct upgrade from existing releases.
- Live 6.1.1 to 6.2.0 found stale version.cpython-314.pyc: source says 6.2.0 but import says 6.1.1. Same deterministic source timestamp/size made the old cache valid to Python.
- Fix: retain generated owner __pycache__ directories in the previous release backup instead of moving them into the new owner. Private venv/workspace trees remain intact without traversal.
- Regression: actual compiled timestamp bytecode failed before the fix. New source/native version 6.2.1; full source validation PASS (unit/installer tests, pinned native reproducibility/race/vet, package and MCP gates); publication and live repair pending.
- Last public release: 6.2.0 at aefa1a2d222801a4953e6fe39b65983750dc7997. Last fully proven live release: 6.1.1. Existing deployment backups and private settings remain intact.
- Next: full pinned-toolchain validation, exact-SHA CI/security, release 6.2.1 public-byte proof, bundle repin and approved live update.
- Run: START-HERE.bat; validate: .venv/Scripts/python.exe scripts/validate_repository.py --scope full --write-reports. Logs: LOCALAPPDATA/Skyrim-Forge/logs and installed UPDATE owner logs. Cross-provider proof is tracked by bundle STATE.md.
