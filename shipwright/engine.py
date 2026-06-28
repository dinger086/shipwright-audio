"""The DawDreamer spine: build a processor graph from a RenderSpec
(instruments -> per-track gain -> master sum -> bus FX), render offline,
return stereo samples. Also limits raw Buffers (SFX) before the CLI writes them."""
import numpy as np
import dawdreamer as daw
from .config import SR, BLOCK, MASTER_CEILING
from .registry import Buffer, RenderSpec

def _limit(audio):
    m = float(np.abs(audio).max())
    if m > MASTER_CEILING:
        audio = audio * (MASTER_CEILING / m)
    return audio.astype(np.float32)

def render_buffer(buf: Buffer):
    s = np.asarray(buf.samples, dtype=np.float32)
    return _limit(s)

def render_spec(spec: RenderSpec):
    engine = daw.RenderEngine(SR, BLOCK)
    nodes, track_outs = [], []

    if spec.duration is not None:
        dur = spec.duration
    else:
        end = max((n.start + n.dur for tr in spec.tracks for n in tr.notes), default=1.0)
        dur = end + 2.0   # tail for releases/reverb

    for i, tr in enumerate(spec.tracks):
        inst = engine.make_faust_processor(f"inst{i}")
        inst.set_dsp_string(tr.instrument.dsp)
        inst.num_voices = tr.instrument.num_voices
        for n in tr.notes:
            inst.add_midi_note(n.pitch, n.vel, n.start, n.dur)
        nodes.append((inst, [])); last = f"inst{i}"

        for j, fx in enumerate(tr.fx):
            p = engine.make_faust_processor(f"fx{i}_{j}"); p.set_dsp_string(fx)
            nodes.append((p, [last])); last = f"fx{i}_{j}"

        lin = 10 ** (tr.gain_db / 20.0)
        g = engine.make_faust_processor(f"g{i}")
        g.set_dsp_string(f"process = _,_ : *({lin}),*({lin});")
        nodes.append((g, [last])); track_outs.append(f"g{i}")

    master = engine.make_add_processor("master", [1.0] * len(track_outs))
    nodes.append((master, track_outs)); last = "master"

    for k, mfx in enumerate(spec.master_fx):
        p = engine.make_faust_processor(f"m{k}"); p.set_dsp_string(mfx)
        nodes.append((p, [last])); last = f"m{k}"

    engine.load_graph(nodes)
    engine.render(dur)
    return _limit(engine.get_audio().T)   # (n, 2)
