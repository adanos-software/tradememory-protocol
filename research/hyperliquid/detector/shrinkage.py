from __future__ import annotations

SIGMA_FLOOR = 1e-9


def blend(self_stats, universe_stats, kappa):
    n = max(0, self_stats.n)
    w = n / (n + kappa) if (n + kappa) > 0 else 0.0
    mu = w * self_stats.mean + (1.0 - w) * universe_stats.mean
    # convex mix of variances (pragmatic — same credibility weight w as the mean, not JS-derived)
    var = w * (self_stats.std ** 2) + (1.0 - w) * (universe_stats.std ** 2)
    sigma = max(SIGMA_FLOOR, var ** 0.5)
    return mu, sigma
