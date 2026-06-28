# Changelog

## Unreleased

- Project discovery: `shipwright` now walks up from the current directory to the
  nearest `shipwright.toml`, so it can run from a subdirectory. Added `-C/--project`
  to point at a project without cd-ing into it.
- `init` is now a proper subcommand (`shipwright init NAME [--force]`) with a
  leaner template: just `shipwright.toml`, a self-contained `sounds/starter_blip.py`,
  and `output/`. Soundfonts and local instrument modules are opt-in.
- Removed the `render.py` dev shim, the `--format` flag (use `--ogg/--flac/--mp3`),
  and the render-default environment variables; settings now live in
  `shipwright.toml`. `SHIPWRIGHT_ROOT` and `SHIPWRIGHT_SOUNDS` remain as escape hatches.
- `Buffer.sr` defaults to the project sample rate at render time instead of being
  frozen at import.

## 0.1.0 - 2026-06-28

- Initial public package for code-first audio rendering.
- Added the `shipwright` console command.
- Added Buffer-based SFX rendering and RenderSpec-based DawDreamer music rendering.
