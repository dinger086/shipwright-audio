"""The vocabulary you author in: a @sound registry plus the data types
that describe a sound. A sound build-function returns EITHER:
  - a Buffer       (raw samples you synthesised in numpy -> SFX)
  - a RenderSpec   (tracks of MIDI played by instruments -> music)
The harness looks at the type and routes it to the right renderer.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
from .config import SR

_REGISTRY = {}

def sound(name):
    """Decorator: register a build-function under a name."""
    def deco(fn):
        _REGISTRY[name] = fn
        return fn
    return deco

def get(name):   return _REGISTRY[name]
def names():     return sorted(_REGISTRY)

# ---- SFX path -------------------------------------------------------------
@dataclass
class Buffer:
    samples: np.ndarray      # (n,) mono or (n, 2) stereo, float -1..1
    sr: int = SR

# ---- Music path -----------------------------------------------------------
@dataclass
class Note:
    pitch: int               # MIDI note number (60 = middle C)
    start: float             # seconds
    dur: float               # seconds
    vel: int = 100           # 1..127

@dataclass
class Instrument:
    name: str
    dsp: str                 # a Faust program (the sound source)
    num_voices: int = 8      # >0 makes it a polyphonic MIDI instrument

@dataclass
class Track:
    instrument: Instrument
    notes: List[Note]
    gain_db: float = 0.0
    fx: List[str] = field(default_factory=list)   # per-track Faust effects

@dataclass
class RenderSpec:
    tracks: List[Track]
    tempo: float = 120.0
    duration: Optional[float] = None              # auto from notes if None
    master_fx: List[str] = field(default_factory=list)  # bus effects (reverb...)
