"""The DawDreamer spine: build processor graphs from RenderSpec objects,
render offline, and prepare audio for export."""
from pathlib import Path

import numpy as np
import dawdreamer as daw

from . import config
from .registry import Buffer, RenderSpec, ReturnBus


def _db(db):
    return 10 ** (db / 20.0)


def _as_stereo(audio):
    s = np.asarray(audio, dtype=np.float32)
    if s.ndim == 1:
        s = np.stack([s, s], axis=1)
    return s


def _limit(audio, ceiling=None):
    ceiling = config.MASTER_CEILING if ceiling is None else ceiling
    audio = np.asarray(audio, dtype=np.float32)
    m = float(np.abs(audio).max()) if audio.size else 0.0
    if m > ceiling:
        audio = audio * (ceiling / m)
    return audio.astype(np.float32)


def _tpdf_dither(audio, subtype):
    if subtype is None or "16" not in subtype.upper():
        return audio
    step = 1.0 / 32768.0
    noise = (np.random.random(audio.shape) - np.random.random(audio.shape)) * step
    return np.asarray(audio + noise, dtype=np.float32)


def measure_lufs(audio):
    """Measure integrated loudness with a lightweight BS.1770-style meter."""
    s = _as_stereo(audio)
    if not len(s):
        return float("-inf")
    power = np.mean(np.sum(s * s, axis=1))
    if power <= 0:
        return float("-inf")
    ungated = -0.691 + 10.0 * np.log10(power)
    gate = max(-70.0, ungated - 10.0)
    frame = max(1, int(config.SR * 0.4))
    kept = []
    for i in range(0, len(s), frame):
        block = s[i:i + frame]
        p = np.mean(np.sum(block * block, axis=1))
        if p > 0 and -0.691 + 10.0 * np.log10(p) >= gate:
            kept.append(p)
    if not kept:
        return ungated
    return float(-0.691 + 10.0 * np.log10(np.mean(kept)))


def normalize_loudness(audio, target_lufs, ceiling=None):
    current = measure_lufs(audio)
    if not np.isfinite(current):
        return _limit(audio, ceiling=ceiling)
    return _limit(np.asarray(audio) * _db(target_lufs - current), ceiling=ceiling)


def prepare_export(audio, gain_db=0.0, target_lufs=None, subtype=None, dither=None):
    out = _as_stereo(audio) * _db(gain_db)
    if target_lufs is not None:
        out = normalize_loudness(out, target_lufs)
    else:
        out = _limit(out)
    subtype = config.EXPORT_SUBTYPE if subtype is None else subtype
    dither = config.DITHER if dither is None else dither
    if dither:
        out = _tpdf_dither(out, subtype)
    return _limit(out)


def write_audio(path, audio, sample_rate, format=None, subtype=None, **export_kwargs):
    import soundfile as sf

    fmt = (format or Path(path).suffix.lstrip(".")).upper()
    if subtype is None and fmt not in {"MP3", "OGG"}:
        subtype = config.EXPORT_SUBTYPE
    data = prepare_export(audio, subtype=subtype, **export_kwargs)
    kwargs = {"format": format}
    if subtype is not None:
        kwargs["subtype"] = subtype
    sf.write(path, data, sample_rate, **kwargs)
    return data


def render_buffer(buf: Buffer):
    return _limit(np.asarray(buf.samples, dtype=np.float32))


def _note_seconds(spec, note):
    if spec.time_unit == "seconds":
        return note.start, note.dur
    if spec.time_unit == "beats":
        spb = 60.0 / spec.tempo
        return note.start * spb, note.dur * spb
    raise ValueError("RenderSpec.time_unit must be 'seconds' or 'beats'")


def _notes_seconds(spec, track):
    return [(*_note_seconds(spec, n), n.pitch, n.vel) for n in track.notes]


def _duration(spec):
    if spec.duration is not None:
        return spec.duration
    end = 0.0
    for tr in spec.tracks:
        for n in tr.notes:
            start, dur = _note_seconds(spec, n)
            end = max(end, start + dur)
    return end + 2.0


def _resolve_path(path):
    if path is None:
        raise ValueError("instrument path is required")
    return str(Path(path).expanduser())


def _render_soundfont(instrument, notes, dur, sample_rate):
    try:
        import fluidsynth
    except ModuleNotFoundError as exc:  # pragma: no cover - optional extra
        raise RuntimeError("SoundFont rendering needs the optional 'soundfont' extra: install pyfluidsynth") from exc

    sf_path = _resolve_path(instrument.path)
    synth = fluidsynth.Synth(samplerate=sample_rate)
    try:
        sfid = synth.sfload(sf_path)
        synth.program_select(0, sfid, instrument.bank, instrument.preset)
        events = []
        for start, note_dur, pitch, vel in notes:
            events.append((max(0.0, start), "on", pitch, vel))
            events.append((max(0.0, start + note_dur), "off", pitch, 0))
        events.sort(key=lambda e: (e[0], e[1] == "on"))
        frames = max(1, int(np.ceil(dur * sample_rate)))
        out = np.zeros((frames, 2), dtype=np.float32)
        pos = 0
        for when, kind, pitch, vel in events:
            target = min(frames, int(round(when * sample_rate)))
            if target > pos:
                chunk = np.asarray(synth.get_samples(target - pos), dtype=np.float32)
                out[pos:target] = chunk.reshape(-1, 2)
                pos = target
            if kind == "on":
                synth.noteon(0, int(pitch), int(vel))
            else:
                synth.noteoff(0, int(pitch))
        if pos < frames:
            chunk = np.asarray(synth.get_samples(frames - pos), dtype=np.float32)
            out[pos:] = chunk.reshape(-1, 2)
        return out
    finally:
        synth.delete()


def _make_source(engine, name, track, notes, dur):
    inst = track.instrument
    if inst.kind == "faust":
        proc = engine.make_faust_processor(name)
        proc.set_dsp_string(inst.dsp)
        proc.num_voices = inst.num_voices
    elif inst.kind == "plugin":
        proc = engine.make_plugin_processor(name, _resolve_path(inst.path))
    elif inst.kind == "soundfont":
        audio = _render_soundfont(inst, notes, dur, config.SR)
        return engine.make_playback_processor(name, audio.T)
    else:
        raise ValueError(f"unknown instrument kind: {inst.kind!r}")

    for start, dur_s, pitch, vel in notes:
        if not hasattr(proc, "add_midi_note"):
            raise RuntimeError(f"instrument {inst.name!r} cannot receive MIDI notes")
        proc.add_midi_note(int(pitch), int(vel), float(start), float(dur_s))
    return proc


def _add_gain(engine, nodes, name, source, gain_db):
    if gain_db == 0:
        return source
    lin = _db(gain_db)
    g = engine.make_faust_processor(name)
    g.set_dsp_string(f"process = _,_ : *({lin}),*({lin});")
    nodes.append((g, [source]))
    return name


def _build_track(engine, nodes, spec, track, i, dur):
    notes = _notes_seconds(spec, track)
    inst_name = f"inst{i}"
    source = _make_source(engine, inst_name, track, notes, dur)
    nodes.append((source, []))
    last = inst_name

    for j, fx in enumerate(track.fx):
        p = engine.make_faust_processor(f"fx{i}_{j}")
        p.set_dsp_string(fx)
        nodes.append((p, [last]))
        last = f"fx{i}_{j}"

    if track.pan:
        panner = engine.make_panner_processor(f"pan{i}", "linear", float(track.pan))
        nodes.append((panner, [last]))
        last = f"pan{i}"

    return _add_gain(engine, nodes, f"g{i}", last, track.gain_db)


def _return_specs(spec):
    returns = {bus.name: bus for bus in spec.returns}
    for tr in spec.tracks:
        for send in tr.sends:
            returns.setdefault(send.bus, ReturnBus(send.bus))
    return returns


def _load_mix_graph(engine, spec, track_outs, dur):
    nodes = []
    master_ins = list(track_outs)
    send_nodes = {name: [] for name in _return_specs(spec)}

    for i, tr in enumerate(spec.tracks):
        for j, send in enumerate(tr.sends):
            src = track_outs[i]
            send_name = _add_gain(engine, nodes, f"send{i}_{j}", src, send.gain_db)
            send_nodes.setdefault(send.bus, []).append(send_name)

    for bus_name, bus in _return_specs(spec).items():
        inputs = send_nodes.get(bus_name, [])
        if not inputs:
            continue
        add = engine.make_add_processor(f"return_{bus_name}", [1.0] * len(inputs))
        nodes.append((add, inputs))
        last = f"return_{bus_name}"
        for j, fx in enumerate(bus.fx):
            p = engine.make_faust_processor(f"return_{bus_name}_fx{j}")
            p.set_dsp_string(fx)
            nodes.append((p, [last]))
            last = f"return_{bus_name}_fx{j}"
        last = _add_gain(engine, nodes, f"return_{bus_name}_gain", last, bus.gain_db)
        master_ins.append(last)

    if not master_ins:
        silence = np.zeros((2, max(1, int(dur * config.SR))), dtype=np.float32)
        p = engine.make_playback_processor("silence", silence)
        nodes.append((p, []))
        master_ins = ["silence"]

    master = engine.make_add_processor("master", [1.0] * len(master_ins))
    nodes.append((master, master_ins))
    last = "master"

    for k, mfx in enumerate(spec.master_fx):
        p = engine.make_faust_processor(f"m{k}")
        p.set_dsp_string(mfx)
        nodes.append((p, [last]))
        last = f"m{k}"

    return nodes, last


def _render_graph(spec):
    dur = _duration(spec)
    engine = daw.RenderEngine(config.SR, config.BLOCK)
    nodes, track_outs = [], []
    for i, tr in enumerate(spec.tracks):
        track_outs.append(_build_track(engine, nodes, spec, tr, i, dur))
    mix_nodes, _ = _load_mix_graph(engine, spec, track_outs, dur)
    nodes.extend(mix_nodes)
    engine.load_graph(nodes)
    engine.render(dur)
    return engine.get_audio().T


def _render_single_track(spec, track, dur):
    single = RenderSpec(
        tracks=[track],
        tempo=spec.tempo,
        time_unit=spec.time_unit,
        time_signature=spec.time_signature,
        duration=dur,
    )
    engine = daw.RenderEngine(config.SR, config.BLOCK)
    nodes = []
    track_out = _build_track(engine, nodes, single, track, 0, dur)
    engine.load_graph(nodes + [(engine.make_add_processor("master", [1.0]), [track_out])])
    engine.render(dur)
    return engine.get_audio().T


def _sidechain_gain(key, sidechain):
    mono = np.mean(np.abs(key), axis=1)
    threshold = _db(sidechain.threshold_db)
    over = np.clip((mono - threshold) / max(threshold, 1e-6), 0.0, 1.0)
    target = 1.0 - over * (1.0 - _db(-abs(sidechain.amount_db)))
    attack = max(1, int(sidechain.attack * config.SR))
    release = max(1, int(sidechain.release * config.SR))
    env = np.ones_like(target)
    cur = 1.0
    for i, val in enumerate(target):
        coeff = 1.0 / (attack if val < cur else release)
        cur += (val - cur) * coeff
        env[i] = cur
    return env


def _apply_sidechains(spec, stems):
    named = {
        (tr.name or f"track_{i + 1}"): audio
        for i, (tr, audio) in enumerate(zip(spec.tracks, stems))
    }
    out = []
    for tr, audio in zip(spec.tracks, stems):
        if tr.sidechain is None:
            out.append(audio)
            continue
        key = named.get(tr.sidechain.source)
        if key is None:
            raise ValueError(f"unknown sidechain source {tr.sidechain.source!r}")
        gain = _sidechain_gain(key, tr.sidechain)
        out.append(audio * gain[:, None])
    return out


def _render_mix_from_audio(spec, stems, dur):
    engine = daw.RenderEngine(config.SR, config.BLOCK)
    nodes, track_outs = [], []
    for i, audio in enumerate(stems):
        name = f"stem{i}"
        p = engine.make_playback_processor(name, _as_stereo(audio).T)
        nodes.append((p, []))
        track_outs.append(name)
    mix_nodes, _ = _load_mix_graph(engine, spec, track_outs, dur)
    nodes.extend(mix_nodes)
    engine.load_graph(nodes)
    engine.render(dur)
    return engine.get_audio().T


def render_stems(spec: RenderSpec, apply_sidechain=True):
    dur = _duration(spec)
    stems = [_render_single_track(spec, tr, dur) for tr in spec.tracks]
    if apply_sidechain:
        stems = _apply_sidechains(spec, stems)
    return {
        (tr.name or f"track_{i + 1}"): _limit(audio)
        for i, (tr, audio) in enumerate(zip(spec.tracks, stems))
    }


def render_spec(spec: RenderSpec):
    if any(tr.sidechain for tr in spec.tracks):
        dur = _duration(spec)
        stems = [_render_single_track(spec, tr, dur) for tr in spec.tracks]
        stems = _apply_sidechains(spec, stems)
        return _limit(_render_mix_from_audio(spec, stems, dur))
    return _limit(_render_graph(spec))
