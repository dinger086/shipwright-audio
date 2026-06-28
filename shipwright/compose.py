"""The composition layer (above the engine). Tiny helpers to turn chord
symbols / pitch lists into Note objects. Swap this for music21 if you want
richer theory; the engine only cares about the Note list."""
from .registry import Note

_NOTE = {'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,'F#':6,'Gb':6,
         'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11}
_QUAL = {'':[0,4,7],'m':[0,3,7],'7':[0,4,7,10],'m7':[0,3,7,10],
         'maj7':[0,4,7,11],'sus2':[0,2,7],'sus4':[0,5,7]}

def note_to_midi(name, octave=4):
    return 12 * (octave + 1) + _NOTE[name]

def _split(sym):
    if len(sym) > 1 and sym[1] in '#b':
        return sym[:2], sym[2:]
    return sym[:1], sym[1:]

def parse_chord(sym, octave=3):
    root, qual = _split(sym)
    base = note_to_midi(root, octave)
    return [base + iv for iv in _QUAL.get(qual, [0, 4, 7])]

def progression(chords, bpm=70, beats_per_chord=4, repeats=1, octave=3, vel=70):
    spb = 60.0 / bpm; notes = []; cur = 0.0
    for _ in range(repeats):
        for c in chords:
            for p in parse_chord(c, octave):
                notes.append(Note(p, cur, beats_per_chord * spb, vel))
            cur += beats_per_chord * spb
    return notes

def melody(pitches, bpm=70, note_beats=None, start_beat=0.0, vel=90):
    spb = 60.0 / bpm; cur = start_beat * spb; notes = []
    nb = note_beats or [1] * len(pitches)
    for p, b in zip(pitches, nb):
        if p is not None:
            notes.append(Note(p, cur, b * spb * 0.95, vel))
        cur += b * spb
    return notes

def bassline(roots, bpm=70, octave=2, beats_per_note=4, repeats=1, vel=80):
    spb = 60.0 / bpm; notes = []; cur = 0.0
    for _ in range(repeats):
        for r in roots:
            notes.append(Note(note_to_midi(r, octave), cur, beats_per_note * spb * 0.9, vel))
            cur += beats_per_note * spb
    return notes
