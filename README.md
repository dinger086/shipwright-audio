# shipwright-audio

A code-first audio studio for game and app sound. Define sounds in small Python
functions, run one command, and get rendered audio files.

Requires Python 3.10 through 3.12.

## Install

As a tool:

```bash
uv tool install shipwright-audio
# or
pipx install shipwright-audio
```

From a checkout:

```bash
uv sync
uv run shipwright --version
```

## Quick Start

Create a project with one runnable starter sound:

```bash
shipwright init my_game_audio
cd my_game_audio
shipwright starter_blip
```

Generated layout:

```text
my_game_audio/
  shipwright.toml
  sounds/
    starter_blip.py
  output/
    .gitkeep
```

Use `shipwright init .` to initialize the current directory. Existing generated
files are not overwritten unless you pass `--force`.

## CLI

`shipwright.toml` marks the project root. `shipwright` walks up from the current
directory to find it, loads the Python files in `sounds/`, and writes renders to
`output/` (both relative to that root, so you can run it from a subdirectory).
Point it at a project elsewhere with `-C/--project`:

```bash
shipwright                         # list available sounds
shipwright starter_blip            # render one sound
shipwright all                     # render every sound
shipwright all --flac --jobs 4     # parallel render with extra FLAC files
shipwright starter_blip --play     # render and audition
shipwright --watch starter_blip    # re-render on save
shipwright -C path/to/project all  # render a project without cd-ing into it
```

Useful render flags:

```bash
shipwright ui_blip --out build/blip.wav --duration 0.4 --gain -3
shipwright sea_bed --stems --lufs -18
shipwright sea_bed --sr 48000 --ogg --flac --mp3
shipwright all --seed 1234 --jobs 0
shipwright --watch all
```

`--jobs 0` uses the available CPU count. MP3 support depends on the local
libsndfile build used by `soundfile`.

## Write Sounds

Each sound is a function decorated with `@sound("name")`. It returns either:

- `Buffer`: raw NumPy samples for direct SFX synthesis.
- `RenderSpec`: MIDI tracks, audio tracks, sends/returns, and master FX.

### Synthesized SFX

```python
from shipwright import Buffer, dsp, sound


@sound("zap")
def zap():
    sig = dsp.saw(220, 0.25)
    sig = dsp.ad_env(sig, attack=0.001, release=0.2)
    sig = dsp.lowpass(sig, 1200)
    sig = dsp.normalize(sig, 0.9)
    return Buffer(dsp.to_stereo(sig))
```

### Sample-Based Audio

Put WAV/AIFF/FLAC files in your project and place them with `AudioClip`.
Audio tracks use the same mixer controls as MIDI tracks: `gain_db`, `pan`,
Faust `fx`, sends/returns, sidechain, and stems.

```python
from shipwright import AudioClip, AudioTrack, RenderSpec, ReturnBus, Send, sound
from shipwright import instruments


@sound("hit_with_space")
def hit_with_space():
    hit = AudioTrack(
        clips=[
            AudioClip("assets/hit.wav", start=0.0),
            AudioClip("assets/hit.wav", start=0.35, gain_db=-8),
        ],
        gain_db=-3,
        pan=-0.2,
        sends=[Send("verb", -12)],
        name="hit",
    )
    return RenderSpec(
        tracks=[hit],
        returns=[ReturnBus("verb", fx=[instruments.reverb(0.35)])],
    )
```

`AudioClip.start` and `AudioClip.dur` use the spec's `time_unit`; `offset` is
always seconds into the source file. Relative paths resolve from the project
root.

### MIDI / Instrument Tracks

```python
from shipwright import RenderSpec, Track, compose, instruments, sound


@sound("loop")
def loop():
    bpm = 96
    chords = compose.progression(
        ["Dm9", "Bbadd9", "F/C", "C7sus4"],
        bpm=bpm,
        beats_per_chord=4,
        timing="beats",
    )
    pad = Track(instruments.soft_pad(), chords, gain_db=-8, pan=-0.2)
    return RenderSpec(
        tracks=[pad],
        tempo=bpm,
        time_unit="beats",
        master_fx=[instruments.reverb(0.3)],
    )
```

See [`examples/music_sea_bed.py`](examples/music_sea_bed.py) and
[`examples/sfx_ui_blip.py`](examples/sfx_ui_blip.py) for complete examples.

## Composition

`shipwright.compose` includes lightweight theory helpers:

- Chords: `dim`, `aug`, `6`, `9/11/13`, `add9`, suspended chords, slash chords.
- Scales and keys, including quantize-to-scale.
- Swing and humanization.
- Time signatures and beat/second conversion.
- Optional MIDI import/export through the `midi` extra.

```python
meter = (3, 4)
start = compose.bar_start(2, meter)
notes = compose.melody([60, 62, 63, 67], bpm=120, start_beat=start, timing="beats")
notes = compose.apply_groove(notes, swing=0.25, time_signature=meter, timing="beats")
```

```python
notes = compose.read_midi("riff.mid")
compose.write_midi("out.mid", notes, bpm=120)
```

## Instruments

Built-in Faust instruments need no external files:

```python
instruments.pluck()
instruments.saw_lead()
instruments.soft_pad()
instruments.sub_bass()
```

For external instruments:

- SoundFont: install the `soundfont` extra, create a `soundfonts/` folder in
  your project, drop `.sf2` files in it, and use `instruments.soundfont("Piano")` or
  `instruments.soundfont("piano", "/path/to/file.sf2", preset=0)`.
- VST/AU: use `instruments.plugin("name", "/path/to/plugin.vst3")`.

## Mixing And Export

Tracks support `gain_db`, `pan`, per-track Faust `fx`, sends, sidechain ducking,
and stem export.

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

Exports are peak-limited, can normalize to a LUFS target with `--lufs`, and
dither 16-bit output by default.

## Project Config

A project is configured through its `shipwright.toml`:

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

Two environment variables override discovery as escape hatches:

- `SHIPWRIGHT_ROOT` — use this directory as the project root instead of walking
  up for a `shipwright.toml`.
- `SHIPWRIGHT_SOUNDS` — load sounds from here (used to run the bundled
  `examples/`).

## Architecture

| Layer | File | Job |
| --- | --- | --- |
| Composition | `shipwright/compose.py` | chord symbols / pitch lists to `Note`s |
| Sound sources | `shipwright/instruments.py` | Faust, SoundFont, and plugin instruments |
| SFX synthesis | `shipwright/dsp.py` | NumPy oscillators, noise, envelopes, filters |
| Engine | `shipwright/engine.py` | DawDreamer graph, mix, FX, offline render |

DawDreamer hosts plugins and renders deterministically offline. It does not
compose and ships no instruments, so Shipwright keeps composition and sound
source helpers above the engine.

## Development

```bash
uv run --extra dev pytest
env SHIPWRIGHT_SOUNDS=examples uv run shipwright ui_blip
env SHIPWRIGHT_SOUNDS=examples uv run shipwright sea_bed
```

## License

`shipwright-audio` is MIT licensed. Its DawDreamer dependency is GPLv3; review
that license before redistributing bundled applications or generated tooling.
