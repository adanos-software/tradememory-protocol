"""Tests for Composite: Holm-min-gate + sustained-M alert.

Properties verified:
1. alert_raised fires at bucket M (not before).
2. A cold bucket resets the counter so M fires again from scratch.
3. alert_raised latches: once True, never again True.
"""
from research.hyperliquid.detector.config import DetectorConfig, AXES, PRIMITIVES
from research.hyperliquid.detector.composite import Composite


def _cfg(M):
    return DetectorConfig(
        bucket_ms=1, M=M, tau={a: 1.0 for a in AXES},
        weights={a: {p: 1/3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=0,
    )


def test_alert_after_M_consecutive_fires():
    comp = Composite(_cfg(M=3))
    hot = {"exposure": 0.001, "discipline": 1.0, "tilt": 1.0}   # min < 0.00333
    r1 = comp.step(hot)
    r2 = comp.step(hot)
    r3 = comp.step(hot)
    assert (r1.alert_raised, r2.alert_raised, r3.alert_raised) == (False, False, True)
    assert r3.carrying_axis == "exposure"


def test_miss_resets_counter():
    comp = Composite(_cfg(M=2))
    hot = {"exposure": 0.001, "discipline": 1.0, "tilt": 1.0}
    cold = {"exposure": 0.9, "discipline": 0.9, "tilt": 0.9}
    comp.step(hot)
    comp.step(cold)   # resets counter
    r = comp.step(hot)
    assert r.alert_raised is False


def test_alert_latches_once():
    comp = Composite(_cfg(M=1))
    hot = {"exposure": 0.001, "discipline": 1.0, "tilt": 1.0}
    assert comp.step(hot).alert_raised is True
    assert comp.step(hot).alert_raised is False   # latched — no second True


def test_fired_flag_independent_of_latch():
    """fired is still True on each hot bucket even after alert has latched."""
    comp = Composite(_cfg(M=1))
    hot = {"exposure": 0.001, "discipline": 1.0, "tilt": 1.0}
    r1 = comp.step(hot)
    assert r1.alert_raised is True
    r2 = comp.step(hot)
    assert r2.fired is True          # still firing
    assert r2.alert_raised is False  # but not a new alert


def test_carrying_axis_none_on_miss():
    """carrying_axis is None when the bucket did not fire."""
    comp = Composite(_cfg(M=1))
    cold = {"exposure": 0.9, "discipline": 0.9, "tilt": 0.9}
    r = comp.step(cold)
    assert r.fired is False
    assert r.carrying_axis is None


def test_carrying_axis_is_argmin():
    """carrying_axis is the axis with the smallest p-value."""
    comp = Composite(_cfg(M=1))
    # tilt has the smallest p
    p = {"exposure": 0.002, "discipline": 0.003, "tilt": 0.0005}
    r = comp.step(p)
    assert r.fired is True
    assert r.carrying_axis == "tilt"


def test_m1_fires_on_first_bucket():
    """With M=1, the very first hot bucket raises an alert."""
    comp = Composite(_cfg(M=1))
    hot = {"exposure": 0.001, "discipline": 1.0, "tilt": 1.0}
    r = comp.step(hot)
    assert r.alert_raised is True
    assert r.fired is True
