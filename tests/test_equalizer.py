import numpy as np
from app.audio.equalizer import Equalizer

SR = 44100

def sine(f, amp=0.05, n=SR):
    t = np.arange(n) / SR
    s = (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)
    return np.column_stack([s, s])

def rms(x): return float(np.sqrt(np.mean(x[SR // 2:] ** 2)))

def test_flat_is_transparent():
    eq = Equalizer(SR); x = sine(1000)
    assert abs(rms(eq.process(x)) / rms(x) - 1) < 0.01

def test_band_boost_and_cut():
    eq = Equalizer(SR); eq.set_band(5, 12)
    assert 3.5 < rms(eq.process(sine(1000))) / rms(sine(1000)) < 4.4
    eq.reset(); eq.set_band(5, -12)
    assert rms(eq.process(sine(1000))) / rms(sine(1000)) < 0.3

def test_other_bands_unaffected():
    eq = Equalizer(SR); eq.set_band(5, 12)
    assert abs(rms(eq.process(sine(62))) / rms(sine(62)) - 1) < 0.1

def test_block_processing_matches_single_pass():
    x = sine(500, n=8192); a = Equalizer(SR); b = Equalizer(SR)
    for e in (a, b): e.set_band(4, 6)
    whole = a.process(x)
    parts = np.vstack([b.process(x[i:i + 1024]) for i in range(0, 8192, 1024)])
    assert np.allclose(whole, parts, atol=1e-5)

def test_mute_balance_volume_and_limiter():
    eq = Equalizer(SR); x = sine(1000, 0.1, 4096)
    eq.set_balance(1.0); y = eq.process(x)
    assert np.allclose(y[:, 0], 0) and y[:, 1].any()
    eq.reset(); eq.set_muted(True); assert not eq.process(x).any()
    eq.reset(); eq.set_volume(1.5)
    assert np.abs(eq.process(sine(1000, 1.0, 4096))).max() <= 1.0

def test_clamping_and_reset():
    eq = Equalizer(SR); eq.set_band(0, 99); assert eq.gains[0] == 12
    eq.reset(); assert eq.gains == [0.0] * 10
