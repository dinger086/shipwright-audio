"""numpy synthesis primitives for SFX. Pure code -> samples. Deterministic,
tiny, no black box. Build blips, creaks, whooshes from oscillators + noise
+ envelopes + filters."""
import numpy as np
from scipy.signal import butter, sosfilt
from .config import SR

def t(dur):
    return np.linspace(0, dur, int(SR * dur), endpoint=False)

# --- oscillators -----------------------------------------------------------
def sine(freq, dur, amp=1.0, phase=0.0):
    return amp * np.sin(2 * np.pi * freq * t(dur) + phase)

def saw(freq, dur, amp=1.0):
    x = t(dur)
    return amp * (2 * ((freq * x) % 1.0) - 1.0)

def square(freq, dur, amp=1.0, duty=0.5):
    return amp * np.where((freq * t(dur)) % 1.0 < duty, 1.0, -1.0)

def noise(dur, amp=1.0, seed=None):
    rng = np.random.default_rng(seed)
    return amp * rng.uniform(-1, 1, int(SR * dur))

# --- envelopes -------------------------------------------------------------
def ad_env(sig, attack=0.005, release=0.1):
    """Apply a linear attack/release to an existing signal."""
    n = len(sig); env = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a: env[:a] = np.linspace(0, 1, a)
    if r: env[-r:] *= np.linspace(1, 0, r)
    return sig * env

def perc_env(dur, decay=0.99):
    """Exponential percussive decay over `dur` seconds."""
    n = int(SR * dur)
    return decay ** np.arange(n) if 0 < decay < 1 else np.exp(-np.linspace(0, 6, n))

# --- filters (scipy biquads) ----------------------------------------------
def _sos(kind, cutoff, order=2):
    nyq = SR / 2
    if kind == 'band':
        wn = [float(np.clip(c / nyq, 1e-4, 0.999)) for c in cutoff]
    else:
        wn = float(np.clip(cutoff / nyq, 1e-4, 0.999))
    return butter(order, wn, btype=kind, output='sos')

def lowpass(sig, cutoff, order=2):  return sosfilt(_sos('low', cutoff, order=order), sig)
def highpass(sig, cutoff, order=2): return sosfilt(_sos('high', cutoff, order=order), sig)
def bandpass(sig, low, high, order=2):
    return sosfilt(_sos('band', [low, high], order=order), sig)

# --- utilities -------------------------------------------------------------
def layer(*sigs):
    """Sum signals of any length (zero-padded to the longest)."""
    n = max(len(s) for s in sigs)
    out = np.zeros(n)
    for s in sigs:
        out[:len(s)] += s
    return out

def to_stereo(sig, pan=0.0):
    """Mono -> stereo with equal-power pan (-1 left .. +1 right)."""
    a = (pan + 1) * np.pi / 4
    return np.stack([sig * np.cos(a), sig * np.sin(a)], axis=1)

def normalize(sig, peak=0.9):
    m = np.abs(sig).max()
    return sig if m == 0 else sig * (peak / m)
