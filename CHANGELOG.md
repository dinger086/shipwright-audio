# Changelog

## Unreleased

## 0.2.0 - 2026-06-28

### Breaking

- `init` is now a subcommand: `shipwright init NAME [--force]`. The project name
  is no longer a bare positional on the render command.
- Removed the `--format` flag (use `--ogg`/`--flac`/`--mp3`), the `render.py` dev
  shim, and the render-default environment variables (`SHIPWRIGHT_SR`,
  `SHIPWRIGHT_BLOCK`, `SHIPWRIGHT_MASTER_CEILING`, `SHIPWRIGHT_TARGET_LUFS`,
  `SHIPWRIGHT_EXPORT_SUBTYPE`, `SHIPWRIGHT_DITHER`). Render defaults now live in
  `shipwright.toml`; `SHIPWRIGHT_ROOT` and `SHIPWRIGHT_SOUNDS` remain as escape
  hatches.

### Added

- Project discovery: `shipwright` walks up from the current directory to the
  nearest `shipwright.toml`, so it can run from a subdirectory. Added
  `-C/--project` to point at a project without cd-ing into it.
- Leaner `init` template: `shipwright.toml`, a `.gitignore` (ignores rendered
  output), a self-contained `sounds/starter_blip.py`, and `output/`. Soundfonts
  and local instrument modules are opt-in.
- `@instrument` decorator for custom numpy instruments: write a per-note
  `(freq, dur, vel) -> samples` function with the `dsp` module and drop it on a
  `Track`, no Faust required. Voices are summed for polyphony.
- `@effect` decorator for numpy/FFT effects: an `(audio, sr) -> audio` function
  usable in a track's `fx` or `master_fx`, applied offline so it can do
  frequency-space processing the streaming Faust graph can't (not supported on
  return buses). Added frequency-domain `dsp` helpers `spectral_gate`,
  `spectral_filter`, and `convolve_reverb`.
- Microtonal support: `Note.pitch` is now a float (fractional MIDI), so numpy
  `@instrument`s render any frequency. Added `compose` tuning helpers `cents`,
  `edo`, `just`, `tuned_scale`, `quantize_tuning`, and `quantize_tuning_notes`
  for n-EDO and just-intonation scales. (Faust/SoundFont/VST instruments still
  use integer MIDI note-on.)

### Changed

- `Buffer.sr` defaults to the project sample rate at render time instead of being
  frozen at import.

## 0.1.0 - 2026-06-28

- Initial public package for code-first audio rendering.
- Added the `shipwright` console command.
- Added Buffer-based SFX rendering and RenderSpec-based DawDreamer music rendering.
