from shipwright import compose


def test_note_to_midi_and_chord_parsing():
    assert compose.note_to_midi("C", 4) == 60
    assert compose.note_to_midi("Bb", 3) == 58
    assert compose.parse_chord("Dm", octave=3) == [50, 53, 57]
    assert compose.parse_chord("Cmaj7", octave=4) == [60, 64, 67, 71]
    assert compose.parse_chord("Cdim", octave=4) == [60, 63, 66]
    assert compose.parse_chord("Cadd9", octave=4) == [60, 64, 67, 74]
    assert compose.parse_chord("C/G", octave=4) == [55, 60, 64]


def test_progression_and_melody_timing():
    notes = compose.progression(["C"], bpm=120, beats_per_chord=2)
    assert [note.pitch for note in notes] == [48, 52, 55]
    assert {note.start for note in notes} == {0.0}
    assert {note.dur for note in notes} == {1.0}

    melody = compose.melody([60, None, 62], bpm=60, note_beats=[1, 1, 2])
    assert [note.pitch for note in melody] == [60, 62]
    assert [note.start for note in melody] == [0.0, 2.0]
    assert [note.dur for note in melody] == [0.95, 1.9]


def test_scales_quantize_and_groove():
    assert compose.scale("C", "minor", octave=4) == [60, 62, 63, 65, 67, 68, 70]
    assert compose.quantize_pitch(61, "C", "major") == 60

    beat_notes = compose.melody([60, 62], bpm=120, timing="beats")
    assert [note.start for note in beat_notes] == [0.0, 1.0]
    as_seconds = compose.beats_to_seconds(beat_notes, bpm=120)
    assert [note.start for note in as_seconds] == [0.0, 0.5]

    eighths = compose.melody([60, 62], bpm=120, note_beats=[0.5, 0.5], timing="beats")
    grooved = compose.apply_groove(eighths, swing=0.5, timing="beats")
    assert grooved[0].start == 0.0
    assert grooved[1].start > eighths[1].start


def test_time_signature_helpers_and_bar_aligned_groove():
    assert compose.Meter.from_value((3, 4)).beats_per_bar == 3
    assert compose.Meter.from_value((6, 8)).beats_per_bar == 3
    assert compose.measures(3, (3, 4)) == [0, 3, 6]
    assert compose.bar_start(2, (3, 4)) == 6

    notes = compose.melody([60, 62], note_beats=[0.5, 0.5], start_beat=3, timing="beats")
    grooved = compose.apply_groove(notes, swing=0.5, time_signature=(3, 4), timing="beats")

    assert grooved[0].start == 3
    assert grooved[1].start > notes[1].start
