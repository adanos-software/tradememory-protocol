"""Tests for research/hyperliquid/detector/calibration.py.

Task 14 tests (measure): type_i / power / latency reporting.
Task 15 tests (pick_winner, lda_weights, run_calibration): grid search + pickup rule + artifact.
"""
from __future__ import annotations

import math
import os
import json
import tempfile

import pytest

from research.hyperliquid.detector.config import DetectorConfig, PRIMITIVES, AXES
from research.hyperliquid.tests.detector.helpers import anchors_flat, identity_cov


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cfg(M=3, kappa=0, burn_in=10, tau=0.3):
    return DetectorConfig(
        bucket_ms=1,
        M=M,
        tau={a: tau for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=kappa,
        burn_in=burn_in,
    )


# ============================================================
# TASK 14: measure()
# ============================================================

class TestMeasure:
    def test_measure_reports_typei_and_power(self):
        from research.hyperliquid.detector.calibration import measure

        res = measure(
            _cfg(),
            anchors_flat(),
            identity_cov(),
            delta=2.0,
            n_streams=40,
            length=300,
            seed=11,
        )
        assert 0.0 <= res["type_i"] <= 1.0
        assert 0.0 <= res["power"] <= 1.0
        # strong delta + small M → power should clearly exceed type_i
        assert res["power"] > res["type_i"]

    def test_measure_pure_normal_no_drift(self):
        """Type-I on zero-drift streams with tight alpha → should be low."""
        from research.hyperliquid.detector.calibration import measure

        res = measure(
            _cfg(M=3),
            anchors_flat(),
            identity_cov(),
            delta=0.0,       # no drift magnitude — theta_onset=0 anyway
            n_streams=30,
            length=200,
            seed=42,
        )
        # type_i is the ONLY thing evaluated for pure Normal (theta_onset=0)
        assert 0.0 <= res["type_i"] <= 1.0
        # Sanity bound: a properly calibrated detector should not fire too
        # often on pure-Normal data.
        assert res["type_i"] < 0.3

    def test_measure_latency_is_nonneg_or_none(self):
        """median_detection_latency_buckets is None (no detections) or >= 0."""
        from research.hyperliquid.detector.calibration import measure

        res = measure(
            _cfg(),
            anchors_flat(),
            identity_cov(),
            delta=2.5,
            n_streams=20,
            length=200,
            seed=7,
        )
        lat = res["median_detection_latency_buckets"]
        assert lat is None or lat >= 0

    def test_measure_deterministic(self):
        """Same seed + same params → identical results."""
        from research.hyperliquid.detector.calibration import measure

        kwargs = dict(
            cfg=_cfg(), anchors=anchors_flat(), cov=identity_cov(),
            delta=1.5, n_streams=20, length=150, seed=99,
        )
        r1 = measure(**kwargs)
        r2 = measure(**kwargs)
        assert r1["type_i"] == r2["type_i"]
        assert r1["power"] == r2["power"]
        assert r1["median_detection_latency_buckets"] == r2["median_detection_latency_buckets"]


# ============================================================
# TASK 15: pick_winner
# ============================================================

class TestPickWinner:
    def test_prefers_power_then_short_floor(self):
        from research.hyperliquid.detector.calibration import pick_winner

        rows = [
            {
                "bucket_ms": 4 * 3600 * 1000, "M": 6, "power": 0.80,
                "type_i": 0.01, "dof": 5, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            },
            {
                "bucket_ms": 1 * 3600 * 1000, "M": 3, "power": 0.80,
                "type_i": 0.01, "dof": 5, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            },
        ]
        w, relaxed = pick_winner(rows)
        assert relaxed is False
        # same power → shorter M*bucket floor wins
        # row[1]: M*bucket = 3*1h = 3h; row[0]: M*bucket = 6*4h = 24h
        assert w["bucket_ms"] == 1 * 3600 * 1000

    def test_relaxes_typei_when_none_pass_strict(self):
        from research.hyperliquid.detector.calibration import pick_winner

        rows = [
            {
                "bucket_ms": 3600 * 1000, "M": 3, "power": 0.75,
                "type_i": 0.04, "dof": 5, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            }
        ]
        w, relaxed = pick_winner(rows)
        assert relaxed is True
        assert w is not None

    def test_returns_none_when_nothing_passes_relaxed(self):
        from research.hyperliquid.detector.calibration import pick_winner

        rows = [
            {
                "bucket_ms": 3600 * 1000, "M": 3, "power": 0.50,
                "type_i": 0.10, "dof": 5, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            }
        ]
        w, relaxed = pick_winner(rows)
        assert w is None
        assert relaxed is True

    def test_strict_winner_chosen_by_power_desc(self):
        from research.hyperliquid.detector.calibration import pick_winner

        rows = [
            {
                "bucket_ms": 3600 * 1000, "M": 3, "power": 0.72,
                "type_i": 0.01, "dof": 5, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            },
            {
                "bucket_ms": 3600 * 1000, "M": 3, "power": 0.85,
                "type_i": 0.01, "dof": 5, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            },
        ]
        w, relaxed = pick_winner(rows)
        assert relaxed is False
        assert w["power"] == 0.85

    def test_tiebreak_by_dof(self):
        """Equal power + equal M*bucket → lower dof wins."""
        from research.hyperliquid.detector.calibration import pick_winner

        rows = [
            {
                "bucket_ms": 3600 * 1000, "M": 3, "power": 0.80,
                "type_i": 0.01, "dof": 7, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            },
            {
                "bucket_ms": 3600 * 1000, "M": 3, "power": 0.80,
                "type_i": 0.01, "dof": 3, "tau": 0.3,
                "weights": "equal", "kappa": 14,
            },
        ]
        w, relaxed = pick_winner(rows)
        assert relaxed is False
        assert w["dof"] == 3

    def test_empty_rows(self):
        from research.hyperliquid.detector.calibration import pick_winner

        w, relaxed = pick_winner([])
        assert w is None
        assert relaxed is True


# ============================================================
# TASK 15: lda_weights
# ============================================================

class TestLdaWeights:
    def test_fallback_on_degenerate_input(self):
        """All-zero MAD → near-zero solution (tiny-solution branch) → fallback to equal weights.

        When mad=0, ridge regularisation keeps S_W non-singular so _solve_linear
        succeeds, but the solution vector is near-zero → the total_abs < _SIGMA_FLOOR
        branch triggers (NOT the 'w is None' branch).
        """
        from research.hyperliquid.detector.calibration import lda_weights

        # mad=0 collapses all variance → near-zero within-class scatter solution
        anchors = anchors_flat(median=0.0, mad=0.0)
        cov = identity_cov()
        w = lda_weights("exposure", anchors, cov, delta=1.0, seed=1)

        primitives = PRIMITIVES["exposure"]
        assert set(w.keys()) == set(primitives)
        # sum |w| == 1
        total = sum(abs(v) for v in w.values())
        assert abs(total - 1.0) < 1e-9

    def test_normal_case_sums_to_one(self):
        """Standard anchors → LDA or fallback → sum|w|==1."""
        from research.hyperliquid.detector.calibration import lda_weights

        w = lda_weights("exposure", anchors_flat(median=0.0, mad=1.0),
                        identity_cov(), delta=1.5, seed=5)
        total = sum(abs(v) for v in w.values())
        assert abs(total - 1.0) < 1e-9

    def test_returns_all_primitives_for_axis(self):
        """lda_weights must return keys == PRIMITIVES[axis]."""
        from research.hyperliquid.detector.calibration import lda_weights

        for axis in AXES:
            w = lda_weights(axis, anchors_flat(), identity_cov(), delta=1.0, seed=1)
            assert set(w.keys()) == set(PRIMITIVES[axis])


# ============================================================
# TASK 15: run_calibration (smoke — keys + determinism, tiny grid)
# ============================================================

class TestRunCalibration:
    def _tiny_grid_overrides(self):
        """Return kwargs that make run_calibration use a minimal grid for test speed.

        M=6 × 1h = 6h satisfies the constraint 6h <= M*bucket_ms <= 7d.
        """
        return dict(
            bucket_ms_options=(3600 * 1000,),   # only 1h
            M_options=(6,),                      # 6 × 1h = 6h (meets lower bound)
            tau_options=(0.3,),
            weights_options=("equal",),
            kappa_options=(7,),
            n_streams=8,
            delta_power=1.5,
            power_by_delta_deltas=(0.5, 1.0),   # skip 1.5 for speed
        )

    def test_artifact_has_required_keys(self):
        from research.hyperliquid.detector.calibration import run_calibration

        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "calib.json")
            artifact = run_calibration(
                anchors=anchors_flat(),
                cov=identity_cov(),
                seed=17,
                out_path=out_path,
                **self._tiny_grid_overrides(),
            )

        required = {
            "grid_rows", "winning_tuple", "realized_type_i", "realized_power",
            "power_by_delta", "typeI_target_relaxed",
        }
        assert required <= set(artifact.keys()), (
            f"Missing keys: {required - set(artifact.keys())}"
        )

    def test_artifact_written_to_disk(self):
        from research.hyperliquid.detector.calibration import run_calibration

        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "calib.json")
            run_calibration(
                anchors=anchors_flat(),
                cov=identity_cov(),
                seed=17,
                out_path=out_path,
                **self._tiny_grid_overrides(),
            )
            assert os.path.isfile(out_path)
            with open(out_path) as f:
                data = json.load(f)
            assert "grid_rows" in data

    def test_grid_rows_nonempty(self):
        from research.hyperliquid.detector.calibration import run_calibration

        with tempfile.TemporaryDirectory() as d:
            artifact = run_calibration(
                anchors=anchors_flat(),
                cov=identity_cov(),
                seed=17,
                out_path=os.path.join(d, "calib.json"),
                **self._tiny_grid_overrides(),
            )
        assert len(artifact["grid_rows"]) >= 1

    def test_power_by_delta_is_dict(self):
        from research.hyperliquid.detector.calibration import run_calibration

        with tempfile.TemporaryDirectory() as d:
            artifact = run_calibration(
                anchors=anchors_flat(),
                cov=identity_cov(),
                seed=17,
                out_path=os.path.join(d, "calib.json"),
                **self._tiny_grid_overrides(),
            )
        pbd = artifact["power_by_delta"]
        assert isinstance(pbd, dict)
        # at least one delta present
        assert len(pbd) >= 1
        # all values are floats in [0,1]
        for k, v in pbd.items():
            assert 0.0 <= v <= 1.0, f"power_by_delta[{k}] = {v} out of range"


# ============================================================
# TASK 15: grid_search (unit — structure check, tiny)
# ============================================================

class TestGridSearch:
    def test_grid_search_returns_rows_with_required_keys(self):
        from research.hyperliquid.detector.calibration import grid_search

        # M=6 × 1h = 6h satisfies the 6h <= M*bucket <= 7d constraint
        rows = grid_search(
            anchors=anchors_flat(),
            cov=identity_cov(),
            seed=3,
            n_streams=8,
            bucket_ms_options=(3600 * 1000,),
            M_options=(6,),
            tau_options=(0.3,),
            weights_options=("equal",),
            kappa_options=(7,),
            delta=1.5,
        )
        assert len(rows) >= 1
        required_row_keys = {
            "bucket_ms", "M", "tau", "weights", "kappa",
            "type_i", "power", "median_detection_latency_buckets", "dof",
        }
        for row in rows:
            assert required_row_keys <= set(row.keys()), (
                f"Row missing keys: {required_row_keys - set(row.keys())}"
            )

    def test_constraint_M_bucket_between_6h_and_7d(self):
        """Grid must only include combinations with 6h <= M*bucket_ms <= 7d."""
        from research.hyperliquid.detector.calibration import grid_search

        rows = grid_search(
            anchors=anchors_flat(),
            cov=identity_cov(),
            seed=3,
            n_streams=4,
            # Include combos that would violate the constraint
            bucket_ms_options=(3600 * 1000, 4 * 3600 * 1000, 24 * 3600 * 1000),
            M_options=(2, 3, 4, 6, 9, 12),
            tau_options=(0.3,),
            weights_options=("equal",),
            kappa_options=(7,),
            delta=1.5,
        )
        ms_6h = 6 * 3600 * 1000
        ms_7d = 7 * 24 * 3600 * 1000
        for row in rows:
            floor_ms = row["bucket_ms"] * row["M"]
            assert ms_6h <= floor_ms <= ms_7d, (
                f"M*bucket = {floor_ms/3600000:.1f}h violates [6h, 7d] for row {row}"
            )

    def test_grid_rows_contain_lda_seed(self):
        """Each grid row must carry the lda_seed used for that cell."""
        from research.hyperliquid.detector.calibration import grid_search

        rows = grid_search(
            anchors=anchors_flat(),
            cov=identity_cov(),
            seed=3,
            n_streams=4,
            bucket_ms_options=(3600 * 1000,),
            M_options=(6,),
            tau_options=(0.3,),
            weights_options=("equal", "lda"),
            kappa_options=(7,),
            delta=1.5,
        )
        assert len(rows) >= 1
        for row in rows:
            assert "lda_seed" in row, "row missing lda_seed field"
            assert isinstance(row["lda_seed"], int)

    def test_stable_lda_seed_deterministic(self):
        """_stable_lda_seed must return the same value across two calls (PYTHONHASHSEED-independent)."""
        from research.hyperliquid.detector.calibration import _stable_lda_seed

        seed, bucket_ms, M, tau, weights_choice, kappa = 42, 3600_000, 6, 0.3, "lda", 14
        s1 = _stable_lda_seed(seed, bucket_ms, M, tau, weights_choice, kappa)
        s2 = _stable_lda_seed(seed, bucket_ms, M, tau, weights_choice, kappa)
        assert s1 == s2, "lda_seed not deterministic across two calls"
        # Different cell → different seed
        s3 = _stable_lda_seed(seed, bucket_ms, M, tau, "equal", kappa)
        assert s1 != s3, "different cells should produce different lda seeds"
        # Result is a non-negative 24-bit integer
        assert 0 <= s1 < (1 << 24)
