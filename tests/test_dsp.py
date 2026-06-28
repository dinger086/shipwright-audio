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
