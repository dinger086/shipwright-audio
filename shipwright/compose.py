"""The composition layer (above the engine).

Helpers here turn chord symbols, scales, grooves, and MIDI files into Note
objects. The engine only cares about the resulting Note list.
"""
from dataclasses import dataclass
import random

from .registry import Note

_NOTE = {'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,'F#':6,'Gb':6,
         'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11}
_QUAL = {
    '': [0, 4, 7],
    'm': [0, 3, 7],
    'min': [0, 3, 7],
    'dim': [0, 3, 6],
    'aug': [0, 4, 8],
    '+': [0, 4, 8],
    '5': [0, 7],
    '6': [0, 4, 7, 9],
    'm6': [0, 3, 7, 9],
    '7': [0, 4, 7, 10],
    'm7': [0, 3, 7, 10],
    'min7': [0, 3, 7, 10],
    'maj7': [0, 4, 7, 11],
    'M7': [0, 4, 7, 11],
    'dim7': [0, 3, 6, 9],
    'm7b5': [0, 3, 6, 10],
    'ø': [0, 3, 6, 10],
    '9': [0, 4, 7, 10, 14],
    'm9': [0, 3, 7, 10, 14],
    'maj9': [0, 4, 7, 11, 14],
    '11': [0, 4, 7, 10, 14, 17],
    'm11': [0, 3, 7, 10, 14, 17],
    '13': [0, 4, 7, 10, 14, 17, 21],
    'm13': [0, 3, 7, 10, 14, 17, 21],
    'add9': [0, 4, 7, 14],
    'madd9': [0, 3, 7, 14],
    'sus2': [0, 2, 7],
    'sus4': [0, 5, 7],
    '7sus4': [0, 5, 7, 10],
}
_SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "chromatic": list(range(12)),
}


@dataclass(frozen=True)
class Key:
    root: str
    scale: str = "major"

    def pitches(self, octave=4, octaves=1):
        return scale(self.root, self.scale, octave=octave, octaves=octaves)


@dataclass(frozen=True)
class Meter:
    beats: int = 4
    beat_unit: int = 4

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        beats, beat_unit = value
        return cls(int(beats), int(beat_unit))

    @property
    def beats_per_bar(self):
        return self.beats * (4.0 / self.beat_unit)

def note_to_midi(name, octave=4):
    return 12 * (octave + 1) + _NOTE[name]

def _split(sym):
    if len(sym) > 1 and sym[1] in '#b':
        return sym[:2], sym[2:]
    return sym[:1], sym[1:]

def _split_slash(sym):
    if "/" not in sym:
        return sym, None
    chord, bass = sym.split("/", 1)
    return chord, bass

def parse_chord(sym, octave=3, inversion=0, close=True):
    """Parse a chord symbol into MIDI pitches.

    Supports common triads/sevenths/extensions plus slash bass notes such as
    C/G. `inversion` rotates chord tones upward by octaves after parsing.
    """
    chord_sym, bass = _split_slash(sym)
    root, qual = _split(chord_sym)
    base = note_to_midi(root, octave)
    if qual not in _QUAL:
        raise ValueError(f"unknown chord quality '{qual}' in {sym!r}")
    notes = [base + iv for iv in _QUAL[qual]]
    for _ in range(inversion):
        notes = notes[1:] + [notes[0] + 12]
    if close:
        notes = sorted(notes)
    if bass:
        bass_pitch = note_to_midi(bass, octave)
        while bass_pitch >= notes[0]:
            bass_pitch -= 12
        notes = [bass_pitch] + [p for p in notes if p % 12 != bass_pitch % 12]
    return notes

def scale(root, quality="major", octave=4, octaves=1):
    if quality not in _SCALES:
        raise ValueError(f"unknown scale '{quality}'")
    base = note_to_midi(root, octave)
    pitches = []
    for o in range(octaves):
        pitches.extend(base + iv + 12 * o for iv in _SCALES[quality])
    return pitches

def quantize_pitch(pitch, root="C", quality="major"):
    tones = {p % 12 for p in scale(root, quality, octave=0)}
    if pitch % 12 in tones:
        return pitch
    candidates = range(pitch - 6, pitch + 7)
    return min(candidates, key=lambda p: (p % 12 not in tones, abs(p - pitch), p))

def quantize_notes(notes, root="C", quality="major"):
    return [Note(quantize_pitch(n.pitch, root, quality), n.start, n.dur, n.vel) for n in notes]

def beats_to_seconds(notes, bpm):
    spb = 60.0 / bpm
    return [Note(n.pitch, n.start * spb, n.dur * spb, n.vel) for n in notes]

def seconds_to_beats(notes, bpm):
    bps = bpm / 60.0
    return [Note(n.pitch, n.start * bps, n.dur * bps, n.vel) for n in notes]

def bars_to_beats(bars, time_signature=(4, 4)):
    return bars * Meter.from_value(time_signature).beats_per_bar

def bar_start(bar, time_signature=(4, 4)):
    """Return the beat offset for a zero-based bar number."""
    return bars_to_beats(bar, time_signature)

def measures(count, time_signature=(4, 4)):
    """Return beat offsets for `count` bars in the given meter."""
    meter = Meter.from_value(time_signature)
    return [i * meter.beats_per_bar for i in range(count)]

def _unit_scale(bpm, timing):
    if timing not in {"seconds", "beats"}:
        raise ValueError("timing must be 'seconds' or 'beats'")
    return 60.0 / bpm if timing == "seconds" else 1.0

def progression(chords, bpm=70, beats_per_chord=4, repeats=1, octave=3, vel=70, timing="seconds"):
    spb = _unit_scale(bpm, timing); notes = []; cur = 0.0
    for _ in range(repeats):
        for c in chords:
            for p in parse_chord(c, octave):
                notes.append(Note(p, cur, beats_per_chord * spb, vel))
            cur += beats_per_chord * spb
    return notes

def melody(pitches, bpm=70, note_beats=None, start_beat=0.0, vel=90, timing="seconds"):
    spb = _unit_scale(bpm, timing); cur = start_beat * spb; notes = []
    nb = note_beats or [1] * len(pitches)
    for p, b in zip(pitches, nb):
        if p is not None:
            notes.append(Note(p, cur, b * spb * 0.95, vel))
        cur += b * spb
    return notes

def bassline(roots, bpm=70, octave=2, beats_per_note=4, repeats=1, vel=80, timing="seconds"):
    spb = _unit_scale(bpm, timing); notes = []; cur = 0.0
    for _ in range(repeats):
        for r in roots:
            notes.append(Note(note_to_midi(r, octave), cur, beats_per_note * spb * 0.9, vel))
            cur += beats_per_note * spb
    return notes

def apply_groove(
    notes,
    bpm=120,
    swing=0.0,
    subdivision=0.5,
    humanize_time=0.0,
    humanize_vel=0,
    time_signature=(4, 4),
    seed=None,
    timing="seconds",
):
    """Apply swing and random timing/velocity jitter.

    `subdivision` is in beats; 0.5 means eighth-note swing. For seconds-based
    notes, `bpm` is used to find the beat grid. `time_signature` accepts
    tuples like (3, 4) and keeps the groove grid aligned to bar boundaries.
    """
    rng = random.Random(seed)
    spb = _unit_scale(bpm, "seconds")
    unit = spb if timing == "seconds" else 1.0
    sub = subdivision * unit
    bar_len = Meter.from_value(time_signature).beats_per_bar * unit
    swing_delay = max(0.0, swing) * sub / 3.0
    out = []
    for n in notes:
        start = n.start
        if sub > 0 and bar_len > 0:
            bar_start_time = int(start / bar_len) * bar_len
            idx = round((start - bar_start_time) / sub)
            if idx % 2 == 1:
                start += swing_delay
        if humanize_time:
            start += rng.uniform(-humanize_time, humanize_time) * unit
        vel = n.vel
        if humanize_vel:
            vel = max(1, min(127, vel + rng.randint(-humanize_vel, humanize_vel)))
        out.append(Note(n.pitch, max(0.0, start), n.dur, vel))
    return out

def write_midi(path, notes, bpm=120, instrument=0):
    try:
        import pretty_midi
    except ModuleNotFoundError as exc:  # pragma: no cover - optional extra
        raise RuntimeError("MIDI export needs the optional 'midi' extra: install pretty_midi") from exc

    midi = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    inst = pretty_midi.Instrument(program=instrument)
    for n in notes:
        inst.notes.append(
            pretty_midi.Note(
                velocity=int(n.vel),
                pitch=int(n.pitch),
                start=float(n.start),
                end=float(n.start + n.dur),
            )
        )
    midi.instruments.append(inst)
    midi.write(str(path))

def read_midi(path, track=0):
    try:
        import pretty_midi
    except ModuleNotFoundError as exc:  # pragma: no cover - optional extra
        raise RuntimeError("MIDI import needs the optional 'midi' extra: install pretty_midi") from exc

    midi = pretty_midi.PrettyMIDI(str(path))
    if track >= len(midi.instruments):
        return []
    return [
        Note(n.pitch, n.start, n.end - n.start, n.velocity)
        for n in midi.instruments[track].notes
    ]
