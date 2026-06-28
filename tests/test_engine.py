import numpy as np

from shipwright.engine import render_buffer
from shipwright.registry import Buffer


def test_render_buffer_limits_peak_and_preserves_shape():
    audio = np.array([[2.0, -2.0], [0.5, -0.5]], dtype=np.float32)

    rendered = render_buffer(Buffer(audio))

    assert rendered.shape == audio.shape
    assert rendered.dtype == np.float32
    assert np.max(np.abs(rendered)) <= 0.97
