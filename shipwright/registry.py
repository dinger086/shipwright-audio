"""The vocabulary you author in: a @sound registry plus the data types
that describe a sound. A sound build-function returns EITHER:
  - a Buffer       (raw samples you synthesised in numpy -> SFX)
  - a RenderSpec   (tracks of MIDI played by instruments -> music)
The harness looks at the type and routes it to the right renderer.
"""
from dataclasses import dataclass, field
from pathlib import Path
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
def clear():     _REGISTRY.clear()

# ---- SFX path -------------------------------------------------------------
@dataclass
class Buffer:
    samples: np.ndarray      # (n,) mono or (n, 2) stereo, float -1..1
    sr: int = SR

# ---- Music path -----------------------------------------------------------
@dataclass
class Note:
    pitch: int               # MIDI note number (60 = middle C)
    start: float             # seconds, or beats when RenderSpec.time_unit="beats"
    dur: float               # seconds, or beats when RenderSpec.time_unit="beats"
    vel: int = 100           # 1..127

@dataclass
class Instrument:
    name: str
    dsp: str = ""            # a Faust program (the sound source)
    num_voices: int = 8      # >0 makes it a polyphonic MIDI instrument
    kind: str = "faust"      # faust, plugin, or soundfont
    path: Optional[Path | str] = None
    bank: int = 0
    preset: int = 0

    @classmethod
    def faust(cls, name: str, dsp: str, num_voices: int = 8):
        return cls(name=name, dsp=dsp, num_voices=num_voices, kind="faust")

    @classmethod
    def plugin(cls, name: str, path: Path | str, num_voices: int = 8):
        return cls(name=name, num_voices=num_voices, kind="plugin", path=path)

    @classmethod
    def soundfont(
        cls,
        name: str,
        path: Path | str,
        bank: int = 0,
        preset: int = 0,
        num_voices: int = 64,
    ):
        return cls(
            name=name,
            num_voices=num_voices,
            kind="soundfont",
            path=path,
            bank=bank,
            preset=preset,
        )

@dataclass
class Send:
    bus: str
    gain_db: float = -12.0

@dataclass
class ReturnBus:
    name: str
    fx: List[str] = field(default_factory=list)
    gain_db: float = 0.0

@dataclass
class Sidechain:
    source: str
    amount_db: float = 6.0
    threshold_db: float = -36.0
    attack: float = 0.01
    release: float = 0.15

@dataclass
class Track:
    instrument: Instrument
    notes: List[Note]
    gain_db: float = 0.0
    fx: List[str] = field(default_factory=list)   # per-track Faust effects
    pan: float = 0.0
    sends: List[Send] = field(default_factory=list)
    sidechain: Optional[Sidechain] = None
    name: Optional[str] = None

@dataclass
class AudioClip:
    path: Path | str
    start: float = 0.0       # seconds, or beats when RenderSpec.time_unit="beats"
    dur: Optional[float] = None
    offset: float = 0.0      # seconds into the source file
    gain_db: float = 0.0

@dataclass
class AudioTrack:
    clips: List[AudioClip]
    gain_db: float = 0.0
    fx: List[str] = field(default_factory=list)
    pan: float = 0.0
    sends: List[Send] = field(default_factory=list)
    sidechain: Optional[Sidechain] = None
    name: Optional[str] = None

@dataclass
class RenderSpec:
    tracks: List[Track | AudioTrack]
    tempo: float = 120.0
    duration: Optional[float] = None              # seconds; auto from notes if None
    master_fx: List[str] = field(default_factory=list)  # bus effects (reverb...)
    time_unit: str = "seconds"                    # seconds or beats
    time_signature: tuple[int, int] = (4, 4)
    returns: List[ReturnBus] = field(default_factory=list)
