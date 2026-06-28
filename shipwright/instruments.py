"""The sound-source layer. DawDreamer has no instruments of its own, so we
supply them. These are Faust programs compiled inside the engine -> zero
external files, fully reproducible. Swap any of these for a SoundFont or a
VST later (see README) when you want more 'produced' instruments."""
from .registry import Instrument

# Faust convention for a polyphonic instrument: expose freq/gain/gate; the
# engine drives them from MIDI. `effect = _,_;` silences the poly warning.
_HEAD = 'import("stdfaust.lib");\n'

def saw_lead(cutoff=1500, voices=8):
    dsp = _HEAD + f"""
    freq=hslider("freq",440,20,8000,0.01);
    gain=hslider("gain",0.4,0,1,0.01);
    gate=button("gate");
    env=en.adsr(0.01,0.15,0.6,0.25,gate);
    process=os.sawtooth(freq)*env*gain : fi.resonlp({cutoff},2,1) <: _,_;
    effect=_,_;
    """
    return Instrument("saw_lead", dsp, voices)

def soft_pad(cutoff=1200, voices=8):
    dsp = _HEAD + f"""
    freq=hslider("freq",220,20,8000,0.01);
    gain=hslider("gain",0.3,0,1,0.01);
    gate=button("gate");
    env=en.adsr(0.6,0.4,0.8,1.2,gate);
    osc=(os.sawtooth(freq)+os.sawtooth(freq*1.006)+os.sawtooth(freq*0.994))/3;
    process=osc*env*gain : fi.lowpass(2,{cutoff}) <: _,_;
    effect=_,_;
    """
    return Instrument("soft_pad", dsp, voices)

def sub_bass(voices=4):
    dsp = _HEAD + """
    freq=hslider("freq",110,20,4000,0.01);
    gain=hslider("gain",0.5,0,1,0.01);
    gate=button("gate");
    env=en.adsr(0.01,0.1,0.9,0.2,gate);
    process=(os.triangle(freq)*0.7+os.osc(freq)*0.3)*env*gain <: _,_;
    effect=_,_;
    """
    return Instrument("sub_bass", dsp, voices)

def pluck(voices=8):
    dsp = _HEAD + """
    freq=hslider("freq",440,20,8000,0.01);
    gain=hslider("gain",0.5,0,1,0.01);
    gate=button("gate");
    process=pm.ks(freq, gate)*gain <: _,_;
    effect=_,_;
    """
    return Instrument("pluck", dsp, voices)

# ---- bus / master effects (2 in -> 2 out) --------------------------------
def reverb(wet=0.3):
    return _HEAD + f"""
    wet={wet};
    process = _,_ <:
      (_*(1.0-wet), _*(1.0-wet)),
      (re.stereo_freeverb(0.72,0.5,0.5,23) : _*wet, _*wet)
      :> _,_;
    """
