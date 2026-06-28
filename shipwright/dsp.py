"""numpy synthesis primitives for SFX."""
import numpy as np
import threading
from scipy.signal import butter, fftconvolve, sosfilt
from .config import SR

_RNG = np.random.default_rng()
_LOCAL = threading.local()


def set_seed(seed):
    """Seed shipwright's module-level random generator used by noise()."""
    global _RNG
    _RNG = np.random.default_rng(seed)
    _LOCAL.rng = np.random.default_rng(seed)

def set_thread_seed(seed):
    """Seed noise() for the current render thread."""
    _LOCAL.rng = np.random.default_rng(seed)

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
    rng = np.random.default_rng(seed) if seed is not None else getattr(_LOCAL, "rng", _RNG)
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

# --- frequency-space (FFT) effects ----------------------------------------
# These operate on the whole signal at once. They accept mono (n,) or stereo
# (n, 2) and return float32 of the same length.
def spectral_gate(sig, threshold=0.05):
    """Zero every frequency bin quieter than `threshold` * the loudest bin.
    A blunt denoise / 'spectral cleanup' that keeps only dominant partials."""
    sig = np.asarray(sig, dtype=np.float64)
    spec = np.fft.rfft(sig, axis=0)
    mag = np.abs(spec)
    spec[mag < mag.max() * threshold] = 0
    return np.fft.irfft(spec, n=sig.shape[0], axis=0).astype(np.float32)

def spectral_filter(sig, low=None, high=None):
    """Brick-wall keep of frequencies within [low, high] Hz in the FFT domain.
    Sharper than the biquad filters; useful for surgical band isolation."""
    sig = np.asarray(sig, dtype=np.float64)
    n = sig.shape[0]
    spec = np.fft.rfft(sig, axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    keep = np.ones(len(freqs), dtype=bool)
    if low is not None:
        keep &= freqs >= low
    if high is not None:
        keep &= freqs <= high
    spec[~keep] = 0
    return np.fft.irfft(spec, n=n, axis=0).astype(np.float32)

def convolve_reverb(sig, decay=2.5, mix=0.35, seed=0):
    """Convolution reverb with a synthetic exponential-decay noise impulse.
    Frequency-domain convolution (scipy.fftconvolve); output keeps `sig`'s
    length (the wet tail past the end is trimmed)."""
    sig = np.asarray(sig, dtype=np.float64)
    n = sig.shape[0]
    rng = np.random.default_rng(seed)
    ir = rng.uniform(-1, 1, n) * np.exp(-np.linspace(0, decay * 6, n))
    ir /= np.abs(ir).sum() or 1.0
    if sig.ndim == 2:
        wet = np.stack([fftconvolve(sig[:, c], ir)[:n] for c in range(sig.shape[1])], axis=1)
    else:
        wet = fftconvolve(sig, ir)[:n]
    return ((1.0 - mix) * sig + mix * wet).astype(np.float32)

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
