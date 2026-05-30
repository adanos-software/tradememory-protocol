from research.hyperliquid.detector.config import PrimitiveStats
from research.hyperliquid.detector.shrinkage import blend


def test_no_self_history_is_all_universe():
    s = PrimitiveStats(mean=5.0, std=2.0, n=0)
    u = PrimitiveStats(mean=1.0, std=1.0, n=999)
    mu, sigma = blend(s, u, kappa=14)
    assert mu == 1.0 and sigma == 1.0


def test_large_self_history_approaches_self():
    s = PrimitiveStats(mean=5.0, std=2.0, n=10_000)
    u = PrimitiveStats(mean=1.0, std=1.0, n=999)
    mu, sigma = blend(s, u, kappa=14)
    assert abs(mu - 5.0) < 0.01


def test_sigma_floored_positive():
    s = PrimitiveStats(mean=0.0, std=0.0, n=5)
    u = PrimitiveStats(mean=0.0, std=0.0, n=5)
    _, sigma = blend(s, u, kappa=14)
    assert sigma > 0


def test_midpoint_shrinkage_at_n_equals_kappa():
    s = PrimitiveStats(mean=4.0, std=2.0, n=14)
    u = PrimitiveStats(mean=0.0, std=2.0, n=999)
    mu, _ = blend(s, u, kappa=14)   # w = 14/(14+14) = 0.5
    assert abs(mu - 2.0) < 1e-9     # 0.5*4 + 0.5*0
