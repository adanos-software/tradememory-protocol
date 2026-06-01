"""
make_figures.py — Publication-quality figures for the Hyperliquid copy-trading drift paper.

Reads:
  research/hyperliquid/cohort_behavioral.json
  research/hyperliquid/fair_comparison_results.json

Writes into research/hyperliquid/paper/figures/:
  fig1_boundary.{pdf,png}
  fig2_fpr_recall.{pdf,png}
  fig3_leadtime.{pdf,png}
  fig4_casestudy.{pdf,png}

Also writes:
  research/hyperliquid/paper/figure_data.json

Usage:
  python research/hyperliquid/paper/make_figures.py
"""

import json
import os
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))

COHORT_PATH = os.path.join(REPO_ROOT, "research", "hyperliquid", "cohort_behavioral.json")
FAIR_PATH = os.path.join(REPO_ROOT, "research", "hyperliquid", "fair_comparison_results.json")
FIGURES_DIR = os.path.join(SCRIPT_DIR, "figures")
FIGURE_DATA_PATH = os.path.join(SCRIPT_DIR, "figure_data.json")

os.makedirs(FIGURES_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family": "DejaVu Serif",
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.35,
    "grid.linestyle": "--",
    "axes.prop_cycle": plt.cycler("color", [
        "#0072B2",  # blue   (colorblind-safe IBM / Wong palette)
        "#E69F00",  # orange
        "#009E73",  # green
        "#D55E00",  # vermillion
        "#CC79A7",  # pink
        "#56B4E9",  # sky-blue
    ]),
})

DPI = 200

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
print("Loading cohort_behavioral.json …", end=" ", flush=True)
with open(COHORT_PATH, "r", encoding="utf-8") as fh:
    cohort = json.load(fh)
masters = cohort["masters"]
print(f"{len(masters)} masters loaded.")

print("Loading fair_comparison_results.json …", end=" ", flush=True)
with open(FAIR_PATH, "r", encoding="utf-8") as fh:
    fair = json.load(fh)
print("done.")

# ---------------------------------------------------------------------------
# Model-free lead computation (used by Fig 1 and Fig 3)
# ---------------------------------------------------------------------------
EARLY_FRAC = 0.20


def _percentile(xs, p):
    """Return p-th percentile (0-100) of a sorted list xs (at least 1 element)."""
    if not xs:
        return None
    xs_s = sorted(xs)
    idx = min(int(p / 100.0 * len(xs_s)), len(xs_s) - 1)
    return xs_s[idx]


def compute_model_free_lead(m):
    """
    Compute (T_behavior_ms, T_equity_ms, trigger_axis) for one blowup master.

    T_behavior: first bucket *after* the early 20% window where:
        - leverage > 1.5 * early-window p90 leverage, OR
        - (loser_add_count > 0 AND leverage > early-window p90), OR
        - stop_attach_rate < early-window p10

    T_equity: first bucket where equity < 0.90 * running peak

    trigger_axis: "exposure" if the first-firing condition is cond_lev or cond_loser_lev
                  "discipline" if the first-firing condition is cond_sar only
                  None if T_behavior is None

    Returns (T_behavior_ms or None, T_equity_ms or None, trigger_axis or None).
    """
    series = m["series"]
    n = len(series)
    early_end = max(4, int(n * EARLY_FRAC))
    early = series[:early_end]

    levs = [b["prim"]["leverage"] for b in early if b["prim"]["leverage"] is not None]
    if not levs:
        return None, None, None
    early_lev_p90 = _percentile(levs, 90)

    sars = [b["prim"]["stop_attach_rate"] for b in early if b["prim"]["stop_attach_rate"] is not None]
    early_sar_p10 = _percentile(sars, 10)

    # T_behavior
    T_behavior_ms = None
    trigger_axis = None
    for i in range(early_end, n):
        b = series[i]
        lev = b["prim"]["leverage"]
        loser_add = b["prim"]["loser_add_count"]
        sar = b["prim"]["stop_attach_rate"]

        cond_lev = lev is not None and early_lev_p90 is not None and lev > 1.5 * early_lev_p90
        cond_loser_lev = (
            loser_add is not None and loser_add > 0
            and lev is not None and early_lev_p90 is not None
            and lev > early_lev_p90
        )
        cond_sar = (
            early_sar_p10 is not None and sar is not None and sar < early_sar_p10
        )

        if cond_lev or cond_loser_lev or cond_sar:
            T_behavior_ms = b["end_ms"]
            # Classify axis: exposure takes priority when both fire simultaneously
            if cond_lev or cond_loser_lev:
                trigger_axis = "exposure"
            else:
                trigger_axis = "discipline"
            break

    # T_equity
    running_peak = None
    T_equity_ms = None
    for b in series:
        eq = b["equity"]
        if eq is None:
            continue
        if running_peak is None or eq > running_peak:
            running_peak = eq
        if running_peak is not None and running_peak > 0 and eq < 0.90 * running_peak:
            T_equity_ms = b["end_ms"]
            break

    return T_behavior_ms, T_equity_ms, trigger_axis


# Compute for all blowup masters with n_buckets >= 20
blowup_masters = [m for m in masters if m["label"] == "blowup" and m["n_buckets"] >= 20]
n_blowup_ge20 = len(blowup_masters)

leads_days = []   # lead in days where both T_behavior and T_equity are found
leads_axes = []   # trigger axis ("exposure" or "discipline") parallel to leads_days
n_no_behavior = 0

for m in blowup_masters:
    T_b, T_e, axis = compute_model_free_lead(m)
    if T_b is None:
        n_no_behavior += 1
    elif T_e is not None:
        lead_h = (T_e - T_b) / 3.6e6
        leads_days.append(lead_h / 24.0)
        leads_axes.append(axis)

n_both_measurable = len(leads_days)
n_behavior_leads = sum(1 for d in leads_days if d > 0)
pct_behavior_leads = 100.0 * n_behavior_leads / n_both_measurable if n_both_measurable else 0
pct_sudden = 100.0 * n_no_behavior / n_blowup_ge20
median_lead = statistics.median(leads_days) if leads_days else 0.0

# Axis breakdown for the positive-lead (behavior-leads) subset
positive_lead_axes = [ax for d, ax in zip(leads_days, leads_axes) if d > 0]
n_exposure_leads = sum(1 for ax in positive_lead_axes if ax == "exposure")
n_discipline_leads = sum(1 for ax in positive_lead_axes if ax == "discipline")
pct_exposure_leads = 100.0 * n_exposure_leads / n_behavior_leads if n_behavior_leads else 0

print(f"\nFig 1 stats:")
print(f"  n_blowup_ge20={n_blowup_ge20}, n_no_behavior={n_no_behavior} ({pct_sudden:.1f}%)")
print(f"  n_both_measurable={n_both_measurable}, n_behavior_leads={n_behavior_leads}")
print(f"  pct_behavior_leads={pct_behavior_leads:.1f}%, median_lead={median_lead:.2f}d")
print(f"  exposure-triggered leads: {n_exposure_leads}/{n_behavior_leads} ({pct_exposure_leads:.1f}%)")
print(f"  discipline-triggered leads: {n_discipline_leads}/{n_behavior_leads}")

# ---------------------------------------------------------------------------
# Fig 1 — Boundary: behavior vs equity lead histogram
# ---------------------------------------------------------------------------
fig1_outbase = os.path.join(FIGURES_DIR, "fig1_boundary")

fig, ax = plt.subplots(figsize=(5.5, 4.0))
fig.subplots_adjust(left=0.14, right=0.97, top=0.88, bottom=0.14)

BINS = 20
n_hist, bin_edges, patches = ax.hist(
    leads_days, bins=BINS, color="#0072B2", edgecolor="white", linewidth=0.6, alpha=0.88, zorder=3
)

# Shade regions
x_min, x_max = ax.get_xlim()
leads_min = min(leads_days)
leads_max = max(leads_days)
pad = 0.03 * (leads_max - leads_min)

ax.axvspan(leads_min - pad, 0, alpha=0.10, color="#D55E00", zorder=1, label="Equity leads (lag)")
ax.axvspan(0, leads_max + pad, alpha=0.10, color="#009E73", zorder=1, label="Behavior leads (early warning)")

# Vertical line at 0
ax.axvline(0, color="#D55E00", linewidth=1.8, linestyle="--", zorder=4, label="Simultaneous ($t=0$)")

# Median line
ax.axvline(median_lead, color="#0072B2", linewidth=1.4, linestyle=":", zorder=4,
           label=f"Median = {median_lead:.1f} d")

# (In-plot callouts removed to avoid colliding with the legend; the same
#  numbers are stated in the title and the LaTeX caption.)

ax.set_xlabel("Lead time: $T_{\\mathrm{equity}} - T_{\\mathrm{behavior}}$ (days)")
ax.set_ylabel("Number of masters")
ax.set_title(
    "Behavioral drift does NOT generally precede equity loss\n"
    f"(blowup masters with $\\geq$20 buckets, $n={n_blowup_ge20}$; both signals measurable: $n={n_both_measurable}$)",
    fontsize=10.5,
)
ax.legend(loc="upper left", fontsize=8.5, ncol=1, framealpha=0.9)
ax.set_xlim(leads_min - pad * 2, leads_max + pad * 2)

fig.savefig(fig1_outbase + ".pdf", format="pdf", bbox_inches="tight")
fig.savefig(fig1_outbase + ".png", format="png", dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"Fig 1 saved.")

# ---------------------------------------------------------------------------
# Fig 2 — FPR/Recall scatter with lead annotation
# ---------------------------------------------------------------------------
fig2_outbase = os.path.join(FIGURES_DIR, "fig2_fpr_recall")

methods_raw = fair["methods"]

# Data-driven annotation values (keep text<->figure consistent automatically).
_nb_hold = fair.get("n_holdout_blowup")
_ns_hold = fair.get("n_holdout_stable")
_det_fpr = methods_raw["detector"]["fpr"]
_det_lead_d = methods_raw["detector"]["median_lead_days"]
_b1_fpr = methods_raw["B1_leverage_p90"]["fpr"]
_fpr_ratio = (_b1_fpr / _det_fpr) if _det_fpr else float("nan")

methods_plot = {
    "Detector\n(mSPRT)":        methods_raw["detector"],
    "B1: Lev-p90":              methods_raw["B1_leverage_p90"],
    "B2: DD-velocity":          methods_raw["B2_drawdown_velocity"],
    "B3: Lev+Loser-add":        methods_raw["B3_leverage_up_and_add"],
}

labels_list  = list(methods_plot.keys())
fpr_list     = [methods_plot[k]["fpr"]           for k in labels_list]
recall_list  = [methods_plot[k]["recall"]        for k in labels_list]
lead_d_list  = [methods_plot[k]["median_lead_days"] for k in labels_list]

colors = ["#0072B2", "#E69F00", "#D55E00", "#CC79A7"]
sizes  = [180, 80, 80, 80]  # detector larger
markers = ["D", "o", "o", "o"]

fig, (ax_main, ax_lead) = plt.subplots(
    1, 2,
    figsize=(6.0, 3.8),
    gridspec_kw={"width_ratios": [1.6, 1.0]},
)
fig.subplots_adjust(left=0.10, right=0.97, top=0.88, bottom=0.14, wspace=0.45)

# Short labels placed directly above each point (distinct x-positions => no overlap).
short_pt_labels = ["Det", "B1", "B2", "B3"]
label_dy = [0.060, 0.050, 0.045, 0.050]
for i, (fpr, rec, color, sz, mk) in enumerate(
        zip(fpr_list, recall_list, colors, sizes, markers)):
    ax_main.scatter(fpr, rec, color=color, s=sz, marker=mk, zorder=4, edgecolors="white", linewidths=0.7)
    ax_main.annotate(
        short_pt_labels[i], (fpr, rec),
        xytext=(fpr, rec + label_dy[i]),
        ha="center", fontsize=9.5, color=color, fontweight="bold",
        arrowprops=dict(arrowstyle="-", color=color, lw=0.7),
    )

# Diagonal reference (FPR = recall)
diag = [0, 0.60]
ax_main.plot(diag, diag, color="0.75", linestyle="--", linewidth=0.9, zorder=1, label="FPR = recall (chance)")
ax_main.set_xlim(-0.01, 0.28)
ax_main.set_ylim(-0.01, 0.70)
ax_main.set_xlabel("False Positive Rate (stable masters)")
ax_main.set_ylabel("Recall (blowup masters, early fire)")
ax_main.set_title(f"FPR / Recall trade-off\n(held-out: {_nb_hold} blowup, {_ns_hold} stable)", fontsize=10.5)
ax_main.legend(fontsize=8.5, loc="upper left", framealpha=0.8)

# (Detector "Lowest FPR" callout removed: it collided with the x-axis label and
#  duplicates Table 1; the detector point is already clearly the left-most.)

# Right panel: median lead bars
short_labels = ["Det.", "B1", "B2", "B3"]
y_pos = range(len(short_labels))
bars = ax_lead.barh(
    list(y_pos), lead_d_list,
    color=colors, edgecolor="white", height=0.55, zorder=3,
)
ax_lead.set_yticks(list(y_pos))
ax_lead.set_yticklabels(short_labels)
ax_lead.set_xlabel("Median lead (days)")
ax_lead.set_title("Median lead\ntime", fontsize=10.5)
for bar, val in zip(bars, lead_d_list):
    ax_lead.text(
        val + 1.5, bar.get_y() + bar.get_height() / 2,
        f"{val:.0f}d", va="center", ha="left", fontsize=8.5,
    )
ax_lead.set_xlim(0, max(lead_d_list) * 1.25)

fig.savefig(fig2_outbase + ".pdf", format="pdf", bbox_inches="tight")
fig.savefig(fig2_outbase + ".png", format="png", dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("Fig 2 saved.")

# ---------------------------------------------------------------------------
# Fig 3 — Lead-time distribution (behavior-leads subset proxy)
# ---------------------------------------------------------------------------
fig3_outbase = os.path.join(FIGURES_DIR, "fig3_leadtime")

positive_leads = sorted(d for d in leads_days if d > 0)
n_pos = len(positive_leads)
med_pos = statistics.median(positive_leads) if positive_leads else 0.0
p25_pos = _percentile(positive_leads, 25)
p75_pos = _percentile(positive_leads, 75)

print(f"\nFig 3 stats:")
print(f"  n_positive_leads={n_pos}, median={med_pos:.1f}d, p25={p25_pos:.1f}d, p75={p75_pos:.1f}d")

fig, ax = plt.subplots(figsize=(5.0, 3.8))
fig.subplots_adjust(left=0.14, right=0.97, top=0.86, bottom=0.14)

ax.hist(positive_leads, bins=15, color="#009E73", edgecolor="white", linewidth=0.6, alpha=0.88, zorder=3)
ax.axvline(med_pos, color="#0072B2", linewidth=1.8, linestyle="--", zorder=4,
           label=f"Median = {med_pos:.1f} d")
ax.axvspan(p25_pos, p75_pos, alpha=0.18, color="#0072B2", zorder=2,
           label=f"IQR [{p25_pos:.1f}, {p75_pos:.1f}] d")

ax.set_xlabel("Behavioral lead time (days)")
ax.set_ylabel("Number of masters")
ax.set_title(
    f"Early-warning lead distribution — behavior-leads subset\n"
    f"($n={n_pos}$ of {n_blowup_ge20} blowup masters; model-free signal precedes equity loss)",
    fontsize=10.0,
)

# (Source note moved to the LaTeX caption to keep the plot uncluttered:
#  this is the model-free drift rule, not the mSPRT detector.)

ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
fig.savefig(fig3_outbase + ".pdf", format="pdf", bbox_inches="tight")
fig.savefig(fig3_outbase + ".png", format="png", dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("Fig 3 saved.")

# ---------------------------------------------------------------------------
# Fig 4 — Case study: Master A (0x40c75d…)
# ---------------------------------------------------------------------------
# Selected: 0x40c75d831744818e01c768db25aa093163d34927
# T_behavior at bucket 138 (leverage spikes 0.84 -> 24.6 with 44 loser-add events)
# T_equity   at bucket 174 (equity drops 47650 -> 30000, peak drop of 37%)
# Lead: ~6.0 days (36 buckets * 4h each)
# ---------------------------------------------------------------------------
fig4_outbase = os.path.join(FIGURES_DIR, "fig4_casestudy")

PREFERRED_FIG4_ADDR = "0x40c75d831744818e01c768db25aa093163d34927"
m4 = next((m for m in masters if m["address"] == PREFERRED_FIG4_ADDR), None)
if m4 is None:
    # Preferred case-study master not in this cohort: auto-select a representative
    # exposure-driven, positive-lead blow-up (clear leverage ramp before equity loss,
    # enough buckets to show it). Pick the MEDIAN-lead case among exposure-triggered
    # positive-lead masters — typical, not cherry-picked extreme.
    _cands = []
    for _m in masters:
        if _m["label"] != "blowup" or _m["n_buckets"] < 60:
            continue
        _Tb, _Te, _axis = compute_model_free_lead(_m)
        if _Tb is not None and _Te is not None and _Te > _Tb and _axis == "exposure":
            _cands.append((_Te - _Tb, _m))
    if _cands:
        _cands.sort(key=lambda x: x[0])
        m4 = _cands[len(_cands) // 2][1]
    else:
        m4 = max(blowup_masters, key=lambda m: m["n_buckets"])
FIG4_ADDR = m4["address"]
FIG4_ADDR_DISPLAY = f"Master A ({FIG4_ADDR[:6]}…)"
series4 = m4["series"]
n4 = len(series4)
early_end4 = max(4, int(n4 * EARLY_FRAC))

levs4_early = [b["prim"]["leverage"] for b in series4[:early_end4] if b["prim"]["leverage"] is not None]
early_lev_p90_4 = _percentile(levs4_early, 90)

sars4 = [b["prim"]["stop_attach_rate"] for b in series4[:early_end4] if b["prim"]["stop_attach_rate"] is not None]
early_sar_p10_4 = _percentile(sars4, 10)

# Find T_behavior
T_beh_idx4 = None
for i in range(early_end4, n4):
    b = series4[i]
    lev = b["prim"]["leverage"]
    loser_add = b["prim"]["loser_add_count"]
    sar = b["prim"]["stop_attach_rate"]
    cond_lev = lev is not None and early_lev_p90_4 is not None and lev > 1.5 * early_lev_p90_4
    cond_loser_lev = (loser_add is not None and loser_add > 0
                      and lev is not None and early_lev_p90_4 is not None
                      and lev > early_lev_p90_4)
    cond_sar = early_sar_p10_4 is not None and sar is not None and sar < early_sar_p10_4
    if cond_lev or cond_loser_lev or cond_sar:
        T_beh_idx4 = i
        break

# Find T_equity
running_peak4 = None
T_eq_idx4 = None
for i, b in enumerate(series4):
    eq = b["equity"]
    if eq is None:
        continue
    if running_peak4 is None or eq > running_peak4:
        running_peak4 = eq
    if running_peak4 is not None and running_peak4 > 0 and eq < 0.90 * running_peak4:
        T_eq_idx4 = i
        break

# Find final blowup index (equity -> 0 or near-zero)
blowup_idx4 = None
final_eq_thresh = running_peak4 * 0.05 if running_peak4 else 0
for i in range(n4 - 1, -1, -1):
    eq = series4[i]["equity"]
    if eq is not None and eq <= final_eq_thresh:
        blowup_idx4 = i
        break

lead4_days = (series4[T_eq_idx4]["end_ms"] - series4[T_beh_idx4]["end_ms"]) / 3.6e6 / 24

# Data-driven trigger description for figure_data.json (no hard-coded narrative).
_lev_beh4 = series4[T_beh_idx4]["prim"]["leverage"]
_la_beh4 = series4[T_beh_idx4]["prim"]["loser_add_count"]
if _lev_beh4 is not None and early_lev_p90_4:
    _fig4_trigger = (f"leverage {_lev_beh4:.2f} vs early-window p90 {early_lev_p90_4:.2f} "
                     f"({_lev_beh4 / early_lev_p90_4:.1f}x); loser_add_count={_la_beh4}")
else:
    _fig4_trigger = "exposure-axis trigger (leverage > 1.5x early-window p90)"

# Display window: 80 buckets before T_behavior to 60 after T_equity (or end)
WIN_PRE  = 80
WIN_POST = 60
i_start4 = max(0, T_beh_idx4 - WIN_PRE)
i_end4   = min(n4, T_eq_idx4 + WIN_POST)

slice4 = series4[i_start4:i_end4]
end_ms_arr = [b["end_ms"] for b in slice4]
# Convert ms to days-since-start-of-window for cleaner axis
t0 = end_ms_arr[0]
t_days = [(ms - t0) / 8.64e7 for ms in end_ms_arr]

equity_arr   = [b["equity"] for b in slice4]
leverage_arr = [b["prim"]["leverage"] for b in slice4]

# Normalize equity to peak = 1
eq_norm = [(eq / running_peak4) if eq is not None else None for eq in equity_arr]

# Clip leverage to a sane multiple of early_p90 for display
LEV_CLIP = min(30.0, max(leverage_arr) * 1.1) if leverage_arr else 30.0
lev_clipped = [min(lv, LEV_CLIP) if lv is not None else None for lv in leverage_arr]

# Marker positions in window-relative days
t_beh_day = (series4[T_beh_idx4]["end_ms"] - t0) / 8.64e7
t_eq_day  = (series4[T_eq_idx4]["end_ms"]  - t0) / 8.64e7
t_blowup_day = ((series4[blowup_idx4]["end_ms"] - t0) / 8.64e7) if blowup_idx4 else None

fig, ax1 = plt.subplots(figsize=(5.5, 4.0))
fig.subplots_adjust(left=0.14, right=0.87, top=0.88, bottom=0.13)
ax2 = ax1.twinx()

# Plot leverage (left axis) — blue
lev_x = [t for t, lv in zip(t_days, lev_clipped) if lv is not None]
lev_y = [lv for lv in lev_clipped if lv is not None]
ax1.plot(lev_x, lev_y, color="#0072B2", linewidth=1.6, label="Leverage (left)", zorder=3)
ax1.set_ylabel("Effective leverage", color="#0072B2")
ax1.tick_params(axis="y", colors="#0072B2")
ax1.set_ylim(bottom=0)

# Plot equity normalized (right axis) — orange
eq_x = [t for t, eq in zip(t_days, eq_norm) if eq is not None]
eq_y = [eq for eq in eq_norm if eq is not None]
ax2.plot(eq_x, eq_y, color="#E69F00", linewidth=1.8, linestyle="-", label="Equity / peak (right)", zorder=3)
ax2.set_ylabel("Equity (normalized to peak = 1)", color="#E69F00")
ax2.tick_params(axis="y", colors="#E69F00")
ax2.set_ylim(-0.05, 1.20)

# 0.90-peak threshold line
ax2.axhline(0.90, color="#E69F00", linewidth=0.9, linestyle=":", alpha=0.7, zorder=2)
ax2.text(t_days[-1], 0.91, "90% peak", fontsize=8, color="#E69F00", va="bottom", ha="right")

# Markers
ax1.axvline(t_beh_day, color="#009E73", linewidth=1.5, linestyle="--", zorder=4)
ax1.axvline(t_eq_day,  color="#D55E00", linewidth=1.5, linestyle="--", zorder=4)
if t_blowup_day is not None:
    ax1.axvline(t_blowup_day, color="black", linewidth=1.2, linestyle="-.", zorder=4)

# Shaded lead-time region
ax1.axvspan(t_beh_day, t_eq_day, alpha=0.09, color="#009E73", zorder=1)

# Label arrows
y_mid_lev = max(lev_y) * 0.65 if lev_y else 15
ax1.annotate(
    f"$T_{{\\mathrm{{behavior}}}}$",
    (t_beh_day, y_mid_lev),
    xytext=(t_beh_day - WIN_PRE * 0.15, y_mid_lev * 1.25),
    fontsize=8.5, color="#009E73",
    arrowprops=dict(arrowstyle="->", color="#009E73", lw=0.9),
)
ax1.annotate(
    f"$T_{{\\mathrm{{equity}}}}$",
    (t_eq_day, y_mid_lev * 0.5),
    xytext=(t_eq_day + WIN_PRE * 0.10, y_mid_lev * 0.8),
    fontsize=8.5, color="#D55E00",
    arrowprops=dict(arrowstyle="->", color="#D55E00", lw=0.9),
)
if t_blowup_day is not None:
    ax1.annotate(
        "Blowup",
        (t_blowup_day, y_mid_lev * 0.2),
        xytext=(t_blowup_day - WIN_PRE * 0.25, y_mid_lev * 0.4),
        fontsize=8.5, color="black",
        arrowprops=dict(arrowstyle="->", color="black", lw=0.9),
    )

# Lead-time annotation
ax1.annotate(
    "",
    xy=(t_eq_day, max(lev_y) * 0.98 if lev_y else 25),
    xytext=(t_beh_day, max(lev_y) * 0.98 if lev_y else 25),
    arrowprops=dict(arrowstyle="<->", color="#555", lw=1.0),
)
ax1.text(
    (t_beh_day + t_eq_day) / 2,
    max(lev_y) * 1.03 if lev_y else 26,
    f"Lead: {lead4_days:.1f} d",
    ha="center", va="bottom", fontsize=9, color="#333",
)

ax1.set_xlabel("Days from display window start")
ax1.set_title(
    f"{FIG4_ADDR_DISPLAY} — leverage ramp precedes equity loss\n"
    f"(bucket 4 h; early-window lev p90 = {early_lev_p90_4:.2f}; "
    f"T_behavior = +{early_lev_p90_4 * 1.5:.1f}x threshold)",
    fontsize=9.5,
)

# Legend
legend_elements = [
    Line2D([0], [0], color="#0072B2", linewidth=1.6, label="Leverage (left axis)"),
    Line2D([0], [0], color="#E69F00", linewidth=1.8, label="Equity / peak (right axis)"),
    Line2D([0], [0], color="#009E73", linewidth=1.4, linestyle="--", label=r"$T_{\mathrm{behavior}}$"),
    Line2D([0], [0], color="#D55E00", linewidth=1.4, linestyle="--", label=r"$T_{\mathrm{equity}}$"),
    Line2D([0], [0], color="black",   linewidth=1.2, linestyle="-.", label="Blowup"),
]
ax1.legend(handles=legend_elements, loc="upper left", fontsize=8.5, framealpha=0.85)

fig.savefig(fig4_outbase + ".pdf", format="pdf", bbox_inches="tight")
fig.savefig(fig4_outbase + ".png", format="png", dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("Fig 4 saved.")

# ---------------------------------------------------------------------------
# Write figure_data.json
# ---------------------------------------------------------------------------
fig_data = {
    "generated_by": "research/hyperliquid/paper/make_figures.py",
    "fig1_boundary": {
        "description": "Model-free behavioral drift vs equity lead histogram",
        "n_blowup_ge20_buckets": n_blowup_ge20,
        "n_no_behavior_signal": n_no_behavior,
        "pct_sudden_no_gradual_signal": round(pct_sudden, 1),
        "n_both_measurable": n_both_measurable,
        "n_behavior_leads_positive": n_behavior_leads,
        "pct_behavior_leads": round(pct_behavior_leads, 1),
        "median_lead_days": round(median_lead, 2),
        "all_leads_days": [round(d, 3) for d in sorted(leads_days)],
        "exposure_share": {
            "description": "Among the behavior-leads masters (positive lead), how many were triggered by the exposure axis (leverage or loser_add+leverage) vs discipline (stop_attach_rate only)",
            "n_exposure_triggered": n_exposure_leads,
            "n_discipline_triggered": n_discipline_leads,
            "n_behavior_leads_total": n_behavior_leads,
            "pct_exposure": round(pct_exposure_leads, 1),
        },
    },
    "fig2_fpr_recall": {
        "description": "FPR / recall scatter, held-out comparison",
        "n_holdout_blowup": fair["n_holdout_blowup"],
        "n_holdout_stable": fair["n_holdout_stable"],
        "methods": {
            "detector": {
                "fpr": fair["methods"]["detector"]["fpr"],
                "recall": fair["methods"]["detector"]["recall"],
                "median_lead_days": fair["methods"]["detector"]["median_lead_days"],
                "fp": fair["methods"]["detector"]["fp"],
                "n_fire_blowup_early": fair["methods"]["detector"]["n_fire_blowup_early"],
            },
            "B1_leverage_p90": {
                "fpr": fair["methods"]["B1_leverage_p90"]["fpr"],
                "recall": fair["methods"]["B1_leverage_p90"]["recall"],
                "median_lead_days": fair["methods"]["B1_leverage_p90"]["median_lead_days"],
            },
            "B2_drawdown_velocity": {
                "fpr": fair["methods"]["B2_drawdown_velocity"]["fpr"],
                "recall": fair["methods"]["B2_drawdown_velocity"]["recall"],
                "median_lead_days": fair["methods"]["B2_drawdown_velocity"]["median_lead_days"],
            },
            "B3_leverage_up_and_add": {
                "fpr": fair["methods"]["B3_leverage_up_and_add"]["fpr"],
                "recall": fair["methods"]["B3_leverage_up_and_add"]["recall"],
                "median_lead_days": fair["methods"]["B3_leverage_up_and_add"]["median_lead_days"],
            },
        },
        "detector_fpr_vs_B1_ratio": round(
            fair["methods"]["B1_leverage_p90"]["fpr"] / fair["methods"]["detector"]["fpr"], 1
        ),
    },
    "fig3_leadtime": {
        "description": "Early-warning lead distribution (behavior-leads subset proxy)",
        "source": "model-free behavioral-drift rule (NOT the mSPRT detector)",
        "note_detector_median_lead_days": fair["methods"]["detector"]["median_lead_days"],
        "n_positive_leads": n_pos,
        "median_lead_days": round(med_pos, 2),
        "p25_lead_days": round(p25_pos, 2),
        "p75_lead_days": round(p75_pos, 2),
        "all_positive_leads_days": [round(d, 3) for d in positive_leads],
    },
    "fig4_casestudy": {
        "description": "Dual-axis time-series case study: leverage ramp precedes equity loss",
        "master_address": FIG4_ADDR,
        "pseudonym": FIG4_ADDR_DISPLAY,
        "n_buckets": n4,
        "bucket_hours": 4,
        "split": m4["split"],
        "early_window_frac": EARLY_FRAC,
        "early_lev_p90": round(early_lev_p90_4, 4),
        "T_behavior_bucket_idx": T_beh_idx4,
        "T_equity_bucket_idx": T_eq_idx4,
        "blowup_bucket_idx": blowup_idx4,
        "T_behavior_ms": series4[T_beh_idx4]["end_ms"],
        "T_equity_ms": series4[T_eq_idx4]["end_ms"],
        "lead_days": round(lead4_days, 2),
        "peak_equity_usd": round(running_peak4, 2),
        "equity_at_T_behavior_usd": round(series4[T_beh_idx4]["equity"], 2),
        "equity_at_T_equity_usd": round(series4[T_eq_idx4]["equity"], 2),
        "leverage_at_T_behavior": round(series4[T_beh_idx4]["prim"]["leverage"], 4),
        "trigger_condition": _fig4_trigger,
    },
}

with open(FIGURE_DATA_PATH, "w", encoding="utf-8") as fh:
    json.dump(fig_data, fh, indent=2)
print(f"figure_data.json written.")

# ---------------------------------------------------------------------------
# Verify all 8 output files exist
# ---------------------------------------------------------------------------
expected = [
    os.path.join(FIGURES_DIR, "fig1_boundary.pdf"),
    os.path.join(FIGURES_DIR, "fig1_boundary.png"),
    os.path.join(FIGURES_DIR, "fig2_fpr_recall.pdf"),
    os.path.join(FIGURES_DIR, "fig2_fpr_recall.png"),
    os.path.join(FIGURES_DIR, "fig3_leadtime.pdf"),
    os.path.join(FIGURES_DIR, "fig3_leadtime.png"),
    os.path.join(FIGURES_DIR, "fig4_casestudy.pdf"),
    os.path.join(FIGURES_DIR, "fig4_casestudy.png"),
    FIGURE_DATA_PATH,
]

print("\n--- Output file check ---")
all_ok = True
for path in expected:
    exists = os.path.isfile(path)
    size_kb = os.path.getsize(path) / 1024 if exists else 0
    status = f"OK  ({size_kb:.1f} KB)" if exists else "MISSING"
    print(f"  {'[OK]' if exists else '[!!]'}  {os.path.relpath(path, REPO_ROOT)}  {status}")
    if not exists:
        all_ok = False

if all_ok:
    print("\nAll 9 output files present. Done.")
else:
    print("\nSome files are MISSING — check errors above.")
    sys.exit(1)
