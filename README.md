# shipwright-audio

A code-first audio studio: describe a sound or a few bars of music in a
small Python function, run one command, get a `.wav` (and `.ogg` for Godot).
The loop is **write → render → listen → adjust** — co-producing in code.

## The shape

Four layers, cleanly separated:

| Layer | File | Job |
|---|---|---|
| **Composition** (above) | `shipwright/compose.py` | chord symbols / pitch lists → `Note`s |
| **Sound sources** (below) | `shipwright/instruments.py` | Faust synths the engine plays |
| **SFX synthesis** | `shipwright/dsp.py` | numpy oscillators / noise / envelopes / filters |
| **The spine** | `shipwright/engine.py` | DawDreamer: graph → mix → bus FX → offline render |

You author in a `sounds/` directory in your project (create it yourself —
the tool reads `./sounds` from wherever you run it). Each file is one sound.
A build-function returns either a **`Buffer`** (raw numpy samples → SFX) or a
**`RenderSpec`** (tracks of MIDI played by instruments → music). The harness
routes by type. Copy-paste starting points live in [`examples/`](examples/).

## Install

As a tool (gets you the `shipwright` command anywhere):

```bash
uv tool install shipwright-audio      # or: pipx install shipwright-audio
```

Or from a checkout for development:

```bash
uv sync                               # create .venv + install deps
```

## Use

`shipwright` loads sounds from `./sounds` and writes to `./output` relative
to the directory you run it in (override with `SHIPWRIGHT_SOUNDS` /
`SHIPWRIGHT_OUTPUT`).

```bash
shipwright                       # list sounds
shipwright sea_bed               # render one  -> output/sea_bed.wav
shipwright all --ogg             # render all, also write .ogg
shipwright --watch sea_bed       # re-render on every save (tight loop)
```

From a checkout without installing, `uv run shipwright ...` or
`python render.py ...` both work.

## Add a sound

Create `sounds/my_thing.py`:

```python
from shipwright import sound, Buffer, dsp

@sound("zap")
def zap():
    s = dsp.ad_env(dsp.saw(220, 0.25), attack=0.001, release=0.2)
    s = dsp.lowpass(s, 1200)
    return Buffer(dsp.to_stereo(dsp.normalize(s, 0.9)))
```

…then `shipwright zap`. Music works the same way but returns a
`RenderSpec` of `Track`s — see [`examples/music_sea_bed.py`](examples/music_sea_bed.py).

## Why DawDreamer is the spine but not the whole thing

DawDreamer mixes, automates (sample-accurate, via numpy arrays), hosts
plugins, and renders deterministically offline. It does **not** compose and
ships **no instruments** — so composition lives above it (`compose.py`) and
sound sources below it (`instruments.py`, here as Faust). That's the whole
architecture.

## Nicer instruments (upgrade path)

The built-in Faust synths need zero files. When you want more "produced"
sound, swap a `Track`'s instrument for either:

- **SoundFont**: drop an `.sf2` in `soundfonts/`, render its MIDI with
  `pyfluidsynth`, feed the audio into the DawDreamer graph as a track.
- **VST/AU**: `engine.make_plugin_processor("name", "/path/to/plugin.vst3")`,
  then `add_midi_note(...)` exactly like the Faust instruments.

## Godot

`--ogg` writes Vorbis files Godot imports directly. For an idle game, render
short stems and loop/layer them at runtime instead of one long track, so the
ambient bed never gets stale.
