"""An 8-bar ambient sea bed: pad + soft lead + sub bass, through reverb.
Music path: returns a RenderSpec that the DawDreamer engine renders."""
from shipwright import sound, Track, RenderSpec, instruments, compose

@sound("sea_bed")
def sea_bed():
    bpm = 70
    pad = Track(
        instruments.soft_pad(cutoff=1100),
        compose.progression(["Dm", "Bb", "F", "C"], bpm, beats_per_chord=4, repeats=2),
        gain_db=-6,
    )
    lead = Track(
        instruments.saw_lead(cutoff=1400),
        compose.melody([74, 77, 76, 74, 72, 74, None, 69, 72, 74],
                       bpm, note_beats=[2,1,1,2,1,1,2,2,2,4], start_beat=4),
        gain_db=-11,
    )
    bass = Track(
        instruments.sub_bass(),
        compose.bassline(["D", "Bb", "F", "C"], bpm, octave=2, beats_per_note=4, repeats=2),
        gain_db=-7,
    )
    return RenderSpec(tracks=[pad, lead, bass], tempo=bpm,
                      master_fx=[instruments.reverb(wet=0.35)])
