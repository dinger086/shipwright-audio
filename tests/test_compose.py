from shipwright import compose


def test_note_to_midi_and_chord_parsing():
    assert compose.note_to_midi("C", 4) == 60
    assert compose.note_to_midi("Bb", 3) == 58
    assert compose.parse_chord("Dm", octave=3) == [50, 53, 57]
    assert compose.parse_chord("Cmaj7", octave=4) == [60, 64, 67, 71]


def test_progression_and_melody_timing():
    notes = compose.progression(["C"], bpm=120, beats_per_chord=2)
    assert [note.pitch for note in notes] == [48, 52, 55]
    assert {note.start for note in notes} == {0.0}
    assert {note.dur for note in notes} == {1.0}

    melody = compose.melody([60, None, 62], bpm=60, note_beats=[1, 1, 2])
    assert [note.pitch for note in melody] == [60, 62]
    assert [note.start for note in melody] == [0.0, 2.0]
    assert [note.dur for note in melody] == [0.95, 1.9]
