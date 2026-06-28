"""A wooden ship-deck creak. Resonant filtered noise + a low groan, wobbled
by a slow LFO. SFX path."""
import numpy as np
from shipwright import sound, Buffer, dsp

@sound("ship_creak")
def ship_creak():
    dur = 2.2
    creak = dsp.bandpass(dsp.noise(dur, seed=7), 150, 600, order=4)
    lfo = 0.35 + 0.65 * np.abs(np.sin(2 * np.pi * 1.3 * dsp.t(dur)))  # slow groan
    creak *= lfo
    groan = dsp.lowpass(dsp.saw(68, dur, 0.5), 280)
    sig = dsp.layer(creak * 0.9, groan * 0.25)
    sig = dsp.ad_env(sig, attack=0.2, release=0.6)
    sig = dsp.normalize(sig, 0.85)
    return Buffer(dsp.to_stereo(sig, pan=-0.2))
