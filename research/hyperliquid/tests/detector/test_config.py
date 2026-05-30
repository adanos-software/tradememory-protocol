import pytest
from research.hyperliquid.detector.config import (
    PrimitiveStats, BaselineStats, DetectorConfig, AXES, PRIMITIVES)


def test_axes_and_primitives_layout():
    assert AXES == ("exposure", "discipline", "tilt")
    # 3 primitives per axis, 9 total; ORDER is canonical (Fisher-LDA weights are order-dependent)
    assert PRIMITIVES["exposure"] == ("leverage", "notional_growth", "size_in_sigma")
    assert PRIMITIVES["discipline"] == ("stop_attach_rate", "reduce_only_rate", "mean_hold_hours")
    assert PRIMITIVES["tilt"] == ("topup_count", "loser_add_count", "fill_rate_spike")


def test_config_defaults_match_prereg():
    cfg = DetectorConfig(bucket_ms=4*3600*1000, M=3,
                         tau={"exposure":0.3,"discipline":0.3,"tilt":0.3},
                         weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES},
                         kappa=14, burn_in=20)
    assert cfg.alpha == 0.01          # pre-reg #12
    assert cfg.guard_x == 0.70        # pre-reg #14
    assert cfg.holm_gate == cfg.alpha/3   # len(AXES) == 3


def test_config_rejects_bad_M_and_axis_keys():
    good_tau = {"exposure":0.3,"discipline":0.3,"tilt":0.3}
    good_w = {a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}
    with pytest.raises(ValueError):
        DetectorConfig(bucket_ms=1, M=0, tau=good_tau, weights=good_w, kappa=14)
    with pytest.raises(ValueError):
        DetectorConfig(bucket_ms=1, M=3, tau={"exposure":0.3}, weights=good_w, kappa=14)
