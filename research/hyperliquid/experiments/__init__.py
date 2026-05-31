"""Plan-3 Phase-5 experiment harness.

Early-window baseline builder + non-trivial early baselines (B1/B2/B3) +
Claim A / Claim B / ablation experiment harness with event-clustered stats.

Pure Python (no numpy). Reuses the frozen detector in
``research.hyperliquid.detector`` and the equity-aware series adapter in
``series_runner``. Never imports ``tradememory.owm.*``.
"""
