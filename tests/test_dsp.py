import numpy as np

from shipwright import config, dsp


def test_oscillators_have_expected_length_and_range():
    sig = dsp.sine(440, 0.1)

    assert len(sig) == int(config.SR * 0.1)
    assert np.max(np.abs(sig)) <= 1.0


def test_layer_pads_to_longest_signal():
    out = dsp.layer(np.ones(3), np.ones(5))

    np.testing.assert_array_equal(out, np.array([2.0, 2.0, 2.0, 1.0, 1.0]))


def test_normalize_and_stereo_shape():
    sig = dsp.normalize(np.array([0.0, 2.0, -1.0]), peak=0.5)
    stereo = dsp.to_stereo(sig)

    assert np.max(np.abs(sig)) == 0.5
    assert stereo.shape == (3, 2)


def test_module_seed_makes_noise_repeatable():
    dsp.set_seed(123)
    a = dsp.noise(0.01)
    dsp.set_seed(123)
    b = dsp.noise(0.01)

    np.testing.assert_array_equal(a, b)


def test_spectral_filter_removes_out_of_band_tone():
    sig = dsp.sine(1000, 0.1)

    kept = dsp.spectral_filter(sig, low=2000)   # the 1 kHz tone is below 2 kHz

    assert kept.shape == sig.shape
    assert np.max(np.abs(kept)) < 0.05


def test_spectral_gate_preserves_a_dominant_tone():
    sig = dsp.sine(440, 0.1)

    out = dsp.spectral_gate(sig, threshold=0.05)

    assert out.shape == sig.shape
    assert np.corrcoef(out, sig)[0, 1] > 0.99


def test_convolve_reverb_keeps_length_and_is_seeded():
    sig = dsp.sine(440, 0.05)

    a = dsp.convolve_reverb(sig, seed=1)
    b = dsp.convolve_reverb(sig, seed=1)

    assert a.shape == sig.shape
    np.testing.assert_array_equal(a, b)


def test_spectral_helpers_handle_stereo():
    sig = dsp.to_stereo(dsp.sine(440, 0.05))

    assert dsp.spectral_gate(sig).shape == sig.shape
    assert dsp.spectral_filter(sig, high=1000).shape == sig.shape
    assert dsp.convolve_reverb(sig).shape == sig.shape
