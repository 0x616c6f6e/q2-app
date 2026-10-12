# App development

Read README.md and docs/app-contract.md; in a full Q2 workspace also read ../ai/app.md.
Lua API 2, UUID v4, strict SemVer. Lua/JSON/assets must remain independent of C/SDK implementations.
Declare minimal capabilities and handle optional permission/provider failures. Do not invent APIs.
Use four-space indentation and comment state transitions/fallback logic.
Run scripts/test_apps.py, validate/pack, and execute changed Lua with an explicitly supplied runner.
Product packaging/launch belongs to root q2.py; standalone app tooling remains in scripts/.
Development checksums are not signatures. No device installer exists yet.
