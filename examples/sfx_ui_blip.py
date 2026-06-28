"""A short UI confirm blip. SFX path: synthesise samples -> Buffer."""
import numpy as np
from shipwright import sound, Buffer, dsp

@sound("ui_blip")
def ui_blip():
    ping1 = dsp.ad_env(dsp.sine(880, 0.09), attack=0.002, release=0.07)
    ping2 = dsp.ad_env(dsp.sine(1320, 0.11), attack=0.002, release=0.09)
    gap = np.zeros(int(0.045 * dsp.SR))
    sig = dsp.layer(ping1, np.concatenate([gap, ping2]))
    sig = dsp.normalize(sig, 0.85)
    return Buffer(dsp.to_stereo(sig, pan=0.0))
