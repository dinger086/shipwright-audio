# shipwright-audio

A code-first audio studio: describe a sound or a few bars of music in a
small Python function, run one command, get a `.wav`.

Requires Python 3.10 through 3.12.

## The shape

Four layers, cleanly separated:

| Layer | File | Job |
| --- | --- | --- |
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
shipwright sea_bed --play        # render and audition with a local player
shipwright all --flac --jobs 4   # render all in parallel, also write FLAC
```

From a checkout without installing, `uv run shipwright ...` or
`python render.py ...` both work.

## Develop

```bash
uv run --extra dev pytest
env SHIPWRIGHT_SOUNDS=examples uv run shipwright ui_blip
env SHIPWRIGHT_SOUNDS=examples uv run shipwright sea_bed
```

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

Useful render flags:

```bash
shipwright ui_blip --out build/blip.wav --duration 0.4 --gain -3
shipwright sea_bed --stems --lufs -18
shipwright sea_bed --sr 48000 --ogg --flac --mp3
shipwright all --seed 1234 --jobs 0
shipwright --watch all
```

`--jobs 0` uses the available CPU count for `all`. MP3 support depends on the
libsndfile build available to `soundfile`.

## Why DawDreamer is the spine but not the whole thing

DawDreamer mixes, automates (sample-accurate, via numpy arrays), hosts
plugins, and renders deterministically offline. It does **not** compose and
ships **no instruments** — so composition lives above it (`compose.py`) and
sound sources below it (`instruments.py`, here as Faust). That's the whole
architecture.

## Composition helpers

`shipwright.compose` supports common chord symbols (`dim`, `aug`, `6`,
`9/11/13`, `add9`, suspended chords, and slash chords like `C/G`), scales and
keys, pitch quantization, swing/humanization, time signatures, and beat/second
conversion.

By default the helpers keep the original behavior and return notes timed in
seconds:

```python
compose.progression(["Dm9", "Bbadd9", "F/C", "C7sus4"], bpm=70)
```

For tempo-driven specs, emit beat-timed notes and tell the renderer to use the
spec tempo:

```python
meter = (3, 4)
start = compose.bar_start(2, meter)
notes = compose.melody([60, 62, 63, 67], bpm=120, start_beat=start, timing="beats")
notes = compose.apply_groove(notes, swing=0.25, time_signature=meter, timing="beats")
return RenderSpec(
    tracks=[Track(instruments.pluck(), notes)],
    tempo=120,
    time_unit="beats",
    time_signature=meter,
)
```

MIDI import/export is available through the optional `midi` extra:

```python
notes = compose.read_midi("riff.mid")
compose.write_midi("out.mid", notes, bpm=120)
```

## Instruments

The built-in Faust synths need zero files. When you want more "produced"
sound, swap a `Track`'s instrument for either:

- **SoundFont**: install the optional `soundfont` extra, drop an `.sf2` in
  `soundfonts/`, and use `instruments.soundfont("Piano")` or
  `instruments.soundfont("piano", "/path/to/file.sf2", preset=0)`.
- **VST/AU**: use `instruments.plugin("name", "/path/to/plugin.vst3")`.
  DawDreamer hosts the plugin and the engine sends it the track's MIDI notes.

## Mixing and export

Tracks have `gain_db` and `pan`. Sends and returns give you shared buses:

```python
from shipwright import ReturnBus, Send, Track

pad = Track(
    instruments.soft_pad(),
    notes,
    gain_db=-8,
    pan=-0.2,
    sends=[Send("verb", -14)],
)
return RenderSpec(
    tracks=[pad],
    returns=[ReturnBus("verb", fx=[instruments.reverb(0.4)], gain_db=-3)],
)
```

For ducking, name the source track and add a `Sidechain` to the track being
ducked. Use `shipwright sea_bed --stems` to write per-track WAV stems next to
the main render. Exports are peak-limited, can normalize to a LUFS target with
`--lufs`, and dither 16-bit output by default.

## Project config

Environment variables still work, and a project can also provide
`shipwright.toml`:

```toml
[shipwright]
sr = 48000
block = 512
master_ceiling = 0.97
target_lufs = -18
export_subtype = "PCM_16"
dither = true
sounds_dir = "sounds"
soundfont_dir = "soundfonts"
output_dir = "output"
```

## License

`shipwright-audio` is MIT licensed. Its DawDreamer dependency is GPLv3; review
that license before redistributing bundled applications or generated tooling.
