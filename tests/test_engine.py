import sys
import types

import numpy as np
import soundfile as sf

from shipwright import config, instrument, instruments
import shipwright.engine as engine
from shipwright.engine import (
    measure_lufs,
    prepare_export,
    render_buffer,
    render_spec,
    _render_python,
)
from shipwright.registry import (
    AudioClip,
    AudioTrack,
    Buffer,
    Instrument,
    Note,
    RenderSpec,
    ReturnBus,
    Send,
    Sidechain,
    Track,
)


class FakeProcessor:
    def __init__(self, name):
        self.name = name
        self.midi = []

    def set_dsp_string(self, dsp):
        self.dsp = dsp

    def add_midi_note(self, pitch, vel, start, dur):
        self.midi.append((pitch, vel, start, dur))


class FakeEngine:
    instances = []

    def __init__(self, sr, block):
        self.sr = sr
        self.block = block
        self.plugin_paths = []
        self.playback = []
        self.panners = []
        self.adds = []
        self.graph = []
        self.frames = 0
        FakeEngine.instances.append(self)

    def make_faust_processor(self, name):
        return FakeProcessor(name)

    def make_plugin_processor(self, name, plugin_path):
        self.plugin_paths.append((name, plugin_path))
        return FakeProcessor(name)

    def make_playback_processor(self, name, data):
        self.playback.append((name, data.shape))
        return FakeProcessor(name)

    def make_panner_processor(self, name, rule, pan):
        self.panners.append((name, rule, pan))
        return FakeProcessor(name)

    def make_add_processor(self, name, gain_levels=None):
        self.adds.append((name, gain_levels or []))
        return FakeProcessor(name)

    def load_graph(self, graph):
        self.graph = graph

    def render(self, dur):
        self.frames = int(round(dur * self.sr))

    def get_audio(self):
        return np.zeros((2, self.frames), dtype=np.float32)


def test_render_buffer_limits_peak_and_preserves_shape():
    audio = np.array([[2.0, -2.0], [0.5, -0.5]], dtype=np.float32)

    rendered = render_buffer(Buffer(audio))

    assert rendered.shape == audio.shape
    assert rendered.dtype == np.float32
    assert np.max(np.abs(rendered)) <= 0.97


def test_render_buffer_preserves_mono_shape():
    audio = np.array([2.0, -2.0, 0.5], dtype=np.float32)

    rendered = render_buffer(Buffer(audio))

    assert rendered.shape == audio.shape
    assert np.max(np.abs(rendered)) <= 0.97


def test_prepare_export_applies_gain_and_loudness_limit():
    audio = np.ones((128, 2), dtype=np.float32) * 0.05

    louder = prepare_export(audio, gain_db=6.0, subtype="FLOAT", dither=False)
    normalized = prepare_export(audio, target_lufs=-18.0, subtype="FLOAT", dither=False)

    assert np.max(np.abs(louder)) > np.max(np.abs(audio))
    assert np.isfinite(measure_lufs(normalized))
    assert np.max(np.abs(normalized)) <= config.MASTER_CEILING


def test_prepare_export_dithers_16_bit_output():
    audio = np.zeros((256, 2), dtype=np.float32)

    dithered = prepare_export(audio, subtype="PCM_16", dither=True)
    plain = prepare_export(audio, subtype="PCM_16", dither=False)

    assert np.any(dithered != plain)


def test_render_spec_uses_duration_in_beats():
    spec = RenderSpec(tracks=[], tempo=120, time_unit="beats", duration=1)

    rendered = render_spec(spec)

    assert rendered.shape == (config.SR, 2)


def test_track_and_render_spec_keep_old_positional_order():
    inst = Instrument("x", "process=0<:_,_;", 2)
    track = Track(inst, [], -6.0, ["fx"])
    spec = RenderSpec([track], 90, 3.0, ["master"])

    assert track.gain_db == -6.0
    assert track.fx == ["fx"]
    assert spec.duration == 3.0
    assert spec.master_fx == ["master"]


def test_plugin_instrument_routes_to_dawdreamer_plugin_processor(monkeypatch):
    FakeEngine.instances = []
    monkeypatch.setattr(engine.daw, "RenderEngine", FakeEngine)
    inst = instruments.plugin("synth", "/tmp/example.vst3")
    track = Track(inst, [Note(60, 0, 0.25)], pan=0.25)
    spec = RenderSpec([track], duration=0.5)

    rendered = render_spec(spec)
    fake = FakeEngine.instances[-1]

    assert rendered.shape == (int(config.SR * 0.5), 2)
    assert fake.plugin_paths == [("inst0", "/tmp/example.vst3")]
    assert fake.panners == [("pan0", "linear", 0.25)]


def test_soundfont_instrument_renders_to_playback_processor(monkeypatch):
    class FakeSynth:
        def __init__(self, samplerate):
            self.samplerate = samplerate
            self.loaded = []
            self.programs = []
            self.events = []
            self.deleted = False

        def sfload(self, path):
            self.loaded.append(path)
            return 42

        def program_select(self, channel, sfid, bank, preset):
            self.programs.append((channel, sfid, bank, preset))

        def noteon(self, channel, pitch, vel):
            self.events.append(("on", channel, pitch, vel))

        def noteoff(self, channel, pitch):
            self.events.append(("off", channel, pitch))

        def get_samples(self, frames):
            return np.zeros(frames * 2, dtype=np.float32)

        def delete(self):
            self.deleted = True

    FakeEngine.instances = []
    fake_module = types.SimpleNamespace(Synth=FakeSynth)
    monkeypatch.setitem(sys.modules, "fluidsynth", fake_module)
    monkeypatch.setattr(engine.daw, "RenderEngine", FakeEngine)
    inst = instruments.soundfont("piano", "/tmp/piano.sf2", bank=1, preset=2)
    track = Track(inst, [Note(64, 0, 0.25, 80)])
    spec = RenderSpec([track], duration=0.5)

    render_spec(spec)
    fake = FakeEngine.instances[-1]

    assert fake.playback == [("inst0", (2, int(config.SR * 0.5)))]


def test_python_instrument_renders_to_playback_processor(monkeypatch):
    FakeEngine.instances = []
    monkeypatch.setattr(engine.daw, "RenderEngine", FakeEngine)

    @instrument("blip")
    def blip(freq, dur, vel):
        return np.zeros(int(dur * config.SR), dtype=np.float32)

    track = Track(blip, [Note(60, 0, 0.25, 80)], pan=0.1)
    spec = RenderSpec([track], duration=0.5)

    render_spec(spec)
    fake = FakeEngine.instances[-1]

    assert fake.playback == [("inst0", (2, int(config.SR * 0.5)))]
    assert fake.panners == [("pan0", "linear", 0.1)]


def test_render_python_sums_voices_at_note_starts():
    @instrument("tone")
    def tone(freq, dur, vel):
        # constant DC equal to velocity so placement is easy to check
        return np.full(int(dur * 100), float(vel), dtype=np.float32)

    notes = [(0.0, 0.1, 69, 1), (0.5, 0.1, 69, 2)]  # 10 frames each at 100 Hz
    out = _render_python(tone, notes, dur=1.0, sample_rate=100)

    assert out.shape == (100, 2)
    assert np.allclose(out[0:10], 1.0)     # first voice
    assert np.allclose(out[50:60], 2.0)    # second voice, offset by 0.5s
    assert np.allclose(out[10:50], 0.0)    # silence between


def test_sends_returns_and_pan_are_in_mix_graph(monkeypatch):
    FakeEngine.instances = []
    monkeypatch.setattr(engine.daw, "RenderEngine", FakeEngine)
    track = Track(
        instruments.pluck(),
        [Note(60, 0, 0.25)],
        pan=-0.5,
        sends=[Send("verb", -9)],
    )
    spec = RenderSpec(
        [track],
        duration=0.5,
        returns=[ReturnBus("verb", fx=[instruments.reverb(0.2)], gain_db=-3)],
    )

    render_spec(spec)
    fake = FakeEngine.instances[-1]
    add_names = [name for name, _levels in fake.adds]

    assert fake.panners == [("pan0", "linear", -0.5)]
    assert "return_verb" in add_names
    assert "master" in add_names


def test_audio_track_loads_clip_into_playback_processor(tmp_path, monkeypatch):
    FakeEngine.instances = []
    sample = np.ones((1000, 2), dtype=np.float32) * 0.25
    asset = tmp_path / "assets" / "hit.wav"
    asset.parent.mkdir()
    sf.write(asset, sample, config.SR)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(engine.daw, "RenderEngine", FakeEngine)
    track = AudioTrack(
        [AudioClip("assets/hit.wav", start=0.25, dur=0.5, gain_db=-3)],
        fx=[instruments.reverb(0.1)],
        pan=0.75,
        name="hit",
    )
    spec = RenderSpec([track], duration=1.0)

    rendered = render_spec(spec)
    fake = FakeEngine.instances[-1]

    assert rendered.shape == (config.SR, 2)
    assert fake.playback == [("audio0", (2, config.SR))]
    assert fake.panners == [("pan0", "linear", 0.75)]


def test_audio_track_auto_duration_and_beat_timing(tmp_path, monkeypatch):
    FakeEngine.instances = []
    sample = np.ones((config.SR, 1), dtype=np.float32) * 0.2
    asset = tmp_path / "loop.wav"
    sf.write(asset, sample, config.SR)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(engine.daw, "RenderEngine", FakeEngine)
    track = AudioTrack([AudioClip("loop.wav", start=2, dur=1)])
    spec = RenderSpec([track], tempo=120, time_unit="beats")

    render_spec(spec)
    fake = FakeEngine.instances[-1]

    assert fake.frames == int(config.SR * 3.5)
    assert fake.playback == [("audio0", (2, int(config.SR * 3.5)))]


def test_render_stems_applies_sidechain_ducking(monkeypatch):
    key_track = Track(instruments.pluck(), [], name="kick")
    ducked_track = Track(
        instruments.pluck(),
        [],
        name="pad",
        sidechain=Sidechain("kick", amount_db=12, threshold_db=-60),
    )
    spec = RenderSpec([key_track, ducked_track], duration=0.01)
    key = np.ones((441, 2), dtype=np.float32) * 0.8
    pad = np.ones((441, 2), dtype=np.float32) * 0.5

    def fake_render_single(_spec, track, _dur):
        return key if track.name == "kick" else pad

    monkeypatch.setattr(engine, "_render_single_track", fake_render_single)

    stems = engine.render_stems(spec)

    assert np.max(stems["pad"]) < np.max(pad)
