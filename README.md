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
shipwright build
```

Generated layout:

```text
my_game_audio/
  shipwright.toml
  .gitignore
  sounds/
    starter_blip.py
  output/
    .gitkeep
```

Use `shipwright init .` to initialize the current directory. Existing generated
files are not overwritten unless you pass `--force`.

## CLI

`shipwright.toml` marks the project root and describes how the project builds.
`shipwright` walks up from the current directory to find it, loads the Python
files in `sounds/`, and writes renders to `output/` (both relative to that root,
so you can run it from a subdirectory). The three commands are:

```bash
shipwright init NAME    # scaffold a new project (use '.' for the current dir)
shipwright build        # render the project per [build] in shipwright.toml
shipwright list         # list the sounds available in the project
```

`shipwright build` is the main command. With no arguments it renders the targets
named in `[build]` (default: every sound) using each sound's configured formats.
Name specific sounds to build just those, and point at a project elsewhere with
`-C/--project`:

```bash
shipwright build                       # build everything per the toml
shipwright build starter_blip          # build one sound
shipwright build a b c                 # build a subset
shipwright build --watch               # re-render on every save
shipwright build -C path/to/project    # build a project without cd-ing in
```

The `[build]` table is the source of truth; CLI flags are one-off overrides on
top of it:

```bash
shipwright build starter_blip --out dist/blip.wav --duration 0.4 --gain -3
shipwright build sea_bed --stems --lufs -18
shipwright build sea_bed --sr 48000 --ogg --flac --mp3
shipwright build --seed 1234 --jobs 0
shipwright build starter_blip --play
```

`--jobs 0` uses the available CPU count. MP3 support depends on the local
libsndfile build used by `soundfile`; a format that can't be written is skipped
with a warning while the rest of the build continues (WAV always must succeed).

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
- Microtonal tuning (any n-EDO or just-intonation ratio set).
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

### Microtonal

`Note.pitch` is a float (fractional MIDI = microtonal), and the numpy
`@instrument` path renders any frequency, so microtonality works end to end
without MIDI's integer limit. (Faust / SoundFont / VST instruments still go
through integer MIDI note-on, so use a numpy instrument for microtonal timbres.)

A *tuning* is a list of cents-above-the-root; `edo()` and `just()` build common
ones, `tuned_scale()` turns one into pitches, and `quantize_tuning()` snaps to it.

```python
notes = compose.melody([60, 60.5, 61, 61.5], bpm=96, timing="beats")  # quarter-tones

quarter = compose.edo(24)                       # 24 equal divisions of the octave
pitches = compose.tuned_scale(quarter, root=60, octaves=2)
snapped = compose.quantize_tuning_notes(notes, quarter, root=60)

ji = compose.just([1, 9/8, 5/4, 4/3, 3/2, 5/3, 15/8])   # just-intonation major
notes = compose.quantize_tuning_notes(notes, ji, root=60)
```

## Instruments

Built-in Faust instruments need no external files:

```python
instruments.pluck()
instruments.saw_lead()
instruments.soft_pad()
instruments.sub_bass()
```

### Custom Instruments

The simplest way to write your own instrument is the `@instrument` decorator: a
per-note `(freq, dur, vel) -> samples` function built from the same `dsp`
vocabulary you use for SFX. It is called once per note and the voices are summed,
so polyphony, chords, and overlapping notes just work. The result drops onto a
`Track` like any built-in.

```python
from shipwright import Track, RenderSpec, compose, dsp, instrument, sound


@instrument("organ")
def organ(freq, dur, vel):
    sig = dsp.saw(freq, dur, amp=vel / 127)
    sig = dsp.ad_env(sig, attack=0.01, release=0.25)
    return dsp.lowpass(sig, 3000)


@sound("riff")
def riff():
    notes = compose.melody([62, 65, 69, 65], bpm=96, timing="beats")
    return RenderSpec([Track(organ, notes)], tempo=96, time_unit="beats")
```

Define instruments inline next to a sound, or in a shared module (e.g.
`my_instruments.py`) you import — the project root is on the import path.

For instruments backed by external files or DSP languages:

- Faust: build one with `Instrument.faust("name", dsp_string, voices)` (see the
  built-ins for the `freq`/`gain`/`gate` convention).
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

## Effects

Track `fx`, return-bus `fx`, and `master_fx` take Faust strings (streaming,
time-domain) — `instruments.reverb()` is one. For frequency-space / FFT work the
streaming graph can't do, write a numpy effect with `@effect`: an
`(audio, sr) -> audio` function that runs offline on the rendered stereo audio.
Drop it into a track's `fx` or `master_fx` next to Faust strings.

```python
import numpy as np
from shipwright import Track, effect


@effect
def lowpass_blur(audio, sr):
    spec = np.fft.rfft(audio, axis=0)
    freqs = np.fft.rfftfreq(len(audio), 1 / sr)
    spec[freqs > 2000] *= 0.2
    return np.fft.irfft(spec, n=len(audio), axis=0)


pad = Track(organ, notes, fx=[lowpass_blur])
```

The `dsp` module ships ready-made frequency-space effects you can call from a
numpy `@effect` or directly in a `Buffer` SFX: `dsp.spectral_gate`,
`dsp.spectral_filter`, and `dsp.convolve_reverb`.

Because a numpy effect needs the whole signal, it runs *after* a track's Faust
chain (not interleaved per-sample), and it isn't supported on return buses — use
Faust there, or apply the effect on a track or in `master_fx`.

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

The `[build]` table describes what `shipwright build` produces. The keys under
`[build]` are the defaults for every sound; a `[build.<name>]` table overrides
them for one sound, and CLI flags override both:

```toml
[build]
targets = ["all"]          # which sounds to build ("all" = every sound)
formats = ["wav"]          # output formats: wav, ogg, flac, mp3
# lufs = -18               # normalize to integrated LUFS before export
# gain = 0.0               # post-render gain in dB
# stems = false            # write per-track WAV stems (RenderSpec sounds)
# seed = 1234              # seed numpy and shipwright noise
# jobs = 0                 # parallel jobs (0 = CPU count, 1 = serial)

[build.sea_bed]            # per-sound overrides
formats = ["wav", "flac"]
duration = 30
stems = true
lufs = -14
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
env SHIPWRIGHT_SOUNDS=examples uv run shipwright build ui_blip
env SHIPWRIGHT_SOUNDS=examples uv run shipwright build sea_bed
```

## License

`shipwright-audio` is MIT licensed. Its DawDreamer dependency is GPLv3; review
that license before redistributing bundled applications or generated tooling.
