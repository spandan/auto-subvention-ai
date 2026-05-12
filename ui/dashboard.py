"""Executive results dashboard + left scenario summary + edit modal hooks."""

from __future__ import annotations

import io
import json
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from nicegui import ui

from services.feature_engineering import (
    build_business_inputs,
)
from services.model_service import get_model_metadata
from services.optimizer import (
    _predict_scenario_row,
    apply_offer_scenario_levers,
    estimate_support_cost,
)
from services.strategy_spectrum import StrategySpectrumPack, build_strategy_spectrum_pack
from ui.dashboard_exec import (
    render_executive_results_body,
    render_executive_sidebar_dealer,
    render_executive_sidebar_oem,
)
from ui.theme import BORDER, TEXT_SECONDARY
from ui.wizard import render_section_for_edit


# Excel export cap (full ranked slice for analysts).
SCENARIOS_TABLE_TOP_N = 100
# Dashboard table: current + recommended + aggressive + top conversion fill.
SCENARIOS_TABLE_UI_MAX = 10
# Cap when user expands the on-page table (large grids are expensive to render).
SCENARIOS_TABLE_SHOW_ALL_CAP = 500


# --- Formatting ----------------------------------------------------------------------
def _fmt_money(x: float) -> str:
    return f"${x:,.0f}"


def _fmt_money_k(x: float) -> str:
    if abs(x) >= 1000:
        return f"${x / 1000:.1f}K"
    return f"${x:,.0f}"


def _fmt_pct(x: float, nd: int = 2) -> str:
    return f"{100.0 * x:.{nd}f}%"


def _pts(x: float) -> str:
    # Non-breaking space keeps the unit on the same line as the number.
    return f"{x * 100:+.1f}\u00a0pts"


_SCENARIO_REC_KEYS = (
    "dealer_rate_support_level",
    "customer_cash",
    "dealer_cash",
    "loyalty_cash",
    "conquest_cash",
    "loan_term",
)


def _row_matches_recommendation(r: pd.Series, rec: pd.Series) -> bool:
    return bool(all(r[k] == rec[k] for k in _SCENARIO_REC_KEYS))


def _same_scenario_levers(a: pd.Series, b: pd.Series) -> bool:
    """True when incentive levers match (same basis as strategy comparison table)."""
    try:
        return bool(all(float(a[k]) == float(b[k]) for k in _SCENARIO_REC_KEYS))
    except (KeyError, TypeError, ValueError):
        return False


def _df_row_index_for_series(df: pd.DataFrame, target: pd.Series) -> int | None:
    """First `df` row index whose scenario levers match `target` (same keys as recommendation match)."""
    if df.empty:
        return None
    for i in range(len(df)):
        r = df.iloc[i]
        try:
            if all(r[k] == target[k] for k in _SCENARIO_REC_KEYS):
                return i
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _curated_scenario_rows(
    df: pd.DataFrame,
    *,
    rec: pd.Series,
    aggressive: pd.Series,
    baseline_match: pd.Series | None,
    max_rows: int = SCENARIOS_TABLE_UI_MAX,
) -> list[tuple[str, int, pd.Series]]:
    """
    Table order: current (baseline levers if present in grid), recommended, aggressive,
    then highest-conversion rows until `max_rows`.
    Each tuple is (kind, iloc_index, row) with kind in current|recommended|aggressive|top.
    """
    ordered: list[tuple[str, int]] = []
    seen: set[int] = set()

    def try_add(kind: str, target: pd.Series | None) -> None:
        if target is None:
            return
        ix = _df_row_index_for_series(df, target)
        if ix is None or ix in seen:
            return
        seen.add(ix)
        ordered.append((kind, ix))

    try_add("current", baseline_match)
    try_add("recommended", rec)
    try_add("aggressive", aggressive)

    order = np.argsort(-df["conversion_probability"].to_numpy(), kind="mergesort")
    for pos in order:
        i = int(pos)
        if len(ordered) >= max_rows:
            break
        if i in seen:
            continue
        seen.add(i)
        ordered.append(("top", i))
    return [(kind, i, df.iloc[i]) for kind, i in ordered]


def top_scenarios_ranked(df: pd.DataFrame, *, n: int = SCENARIOS_TABLE_TOP_N) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.sort_values("conversion_probability", ascending=False).reset_index(drop=True)
    cap = min(int(n), len(out))
    return out.head(cap).copy()


def build_top_scenarios_excel_bytes(df: pd.DataFrame, rec: pd.Series) -> bytes:
    """Narrow export: top N by conversion only (not the full evaluated grid)."""
    top = top_scenarios_ranked(df, n=SCENARIOS_TABLE_TOP_N)
    rows_ex: list[dict[str, Any]] = []
    has_eff = "efficiency_score" in top.columns
    has_loan_amt = "scenario_loan_amount" in top.columns
    for i, (_, row) in enumerate(top.iterrows()):
        recd: dict[str, Any] = {
            "Rank": i + 1,
            "Recommended": "Yes" if _row_matches_recommendation(row, rec) else "No",
            "Rate support index": int(row["dealer_rate_support_level"]),
            "Loan term (months)": int(row["loan_term"]),
            "OEM/customer cash ($)": float(row["customer_cash"]),
            "Dealer cash ($)": float(row["dealer_cash"]),
            "Loyalty ($)": float(row["loyalty_cash"]),
            "Conquest ($)": float(row["conquest_cash"]),
            "Total cash rebate ($)": float(row.get("total_cash_rebate", 0.0)),
            "Dealer APR": float(row["scenario_dealer_apr"]),
            "Monthly payment ($)": float(row["scenario_dealer_monthly_payment"]),
            "Estimated support cost ($)": float(row["estimated_support_cost"]),
            "Conversion probability": float(row["conversion_probability"]),
            "Conversion lift vs baseline": float(row["conversion_lift_vs_baseline"]),
            "Remaining margin ($)": float(row["remaining_margin_estimate"]),
            "Economic score": float(row["expected_value"]),
        }
        if has_loan_amt and pd.notna(row.get("scenario_loan_amount")):
            recd["Loan amount ($)"] = float(row["scenario_loan_amount"])
        if has_eff and pd.notna(row.get("efficiency_score")):
            recd["Efficiency (lift per $ support)"] = float(row["efficiency_score"])
        rows_ex.append(recd)

    exp = pd.DataFrame(rows_ex)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        exp.to_excel(writer, index=False, sheet_name="Top scenarios")
    buf.seek(0)
    return buf.getvalue()


# --- Charts --------------------------------------------------------------------------

LADDER_HOVERTEMPLATE = (
    "<b>Scenario</b><br>"
    "Total support: $%{x:,.0f}<br>"
    "Predicted conversion: %{y:.1%}<br><br>"
    "<b>Offer</b><br>"
    "Dealer APR: %{customdata[0]:.2f}%<br>"
    "Monthly payment: $%{customdata[1]:,.0f}<br>"
    "Loan term: %{customdata[2]} mo<br><br>"
    "<b>Support breakdown</b><br>"
    "APR support cost: $%{customdata[3]:,.0f}<br>"
    "OEM / customer cash: $%{customdata[4]:,.0f}<br>"
    "Dealer cash: $%{customdata[5]:,.0f}<br>"
    "Loyalty incentive: $%{customdata[6]:,.0f}<br>"
    "Conquest incentive: $%{customdata[7]:,.0f}<br>"
    "Total cash rebate: $%{customdata[8]:,.0f}<br><br>"
    "Remaining margin: $%{customdata[9]:,.0f}<br>"
    "Status: %{customdata[10]}<extra></extra>"
)


def apr_support_cost_for_row(row: pd.Series, cm: float) -> float:
    la = float(row.get("scenario_loan_amount") or row.get("loan_amount") or 0.0)
    sup = float(row.get("dealer_rate_support_level") or 0.0)
    return la * (sup / 10000.0) * cm


def scenario_hover_customdata_tuple(row: pd.Series, cm: float, tag: str) -> tuple[Any, ...]:
    """One row × 11 hover fields — matches LADDER_HOVERTEMPLATE customdata[*]."""
    ac = apr_support_cost_for_row(row, cm)
    return (
        float(row.get("scenario_dealer_apr", 0.0)),
        float(row.get("scenario_dealer_monthly_payment", 0.0)),
        int(row.get("loan_term", 0)),
        ac,
        float(row.get("customer_cash", 0.0)),
        float(row.get("dealer_cash", 0.0)),
        float(row.get("loyalty_cash", 0.0)),
        float(row.get("conquest_cash", 0.0)),
        float(row.get("total_cash_rebate", 0.0)),
        float(row.get("remaining_margin_estimate", 0.0)),
        str(tag),
    )


def _ladder_frontier_representatives(df: pd.DataFrame, bins: int = 48) -> pd.DataFrame:
    """
    Within each spend-cost band (same bins as legacy aggregate curve), choose the scenario
    with max predicted conversion — provides a real scenario row per point for hover.
    """
    if df.empty:
        return df.iloc[0:0].copy()
    d = df.copy()
    lo = float(d["estimated_support_cost"].min())
    hi = float(d["estimated_support_cost"].max())
    if hi - lo < 1e-6:
        j = int(d["conversion_probability"].astype(float).idxmax())
        return d.loc[[j]].copy()

    nb = min(bins, max(16, len(d) // 4))
    edges = np.linspace(lo, hi, nb + 1)
    idxs: list[int] = []
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        m = (d["estimated_support_cost"] >= a - 1e-9) & (
            d["estimated_support_cost"] <= b + 1e-9
        )
        if m.any():
            sub = d.loc[m]
            idxs.append(int(sub["conversion_probability"].astype(float).idxmax()))
    if not idxs:
        j = int(d["conversion_probability"].astype(float).idxmax())
        return d.loc[[j]].copy()
    out = d.loc[list(dict.fromkeys(idxs))].copy()
    out = out.sort_values("estimated_support_cost").reset_index(drop=True)
    return out


def mk_incentive_ladder_fig(
    df: pd.DataFrame,
    rec: pd.Series,
    *,
    cur_cost: float,
    cur_p: float,
    agg: pd.Series,
    cm: float,
    baseline_row: pd.Series,
) -> go.Figure:
    frontier_df = _ladder_frontier_representatives(df)
    xd = frontier_df["estimated_support_cost"].astype(float)
    yd = frontier_df["conversion_probability"].astype(float)
    cd_band = [
        scenario_hover_customdata_tuple(row, cm, "Efficient frontier (band)")
        for _, row in frontier_df.iterrows()
    ]

    fig = go.Figure()
    if len(xd):
        fig.add_trace(
            go.Scatter(
                x=xd,
                y=yd,
                mode="lines+markers",
                line=dict(color="#64748b", width=2, shape="spline"),
                marker=dict(size=6, color="#94a3b8"),
                name="Efficient frontier (by spend band)",
                customdata=cd_band,
                hovertemplate=LADDER_HOVERTEMPLATE,
            )
        )

    marker_styles = [
        dict(size=12, symbol="square", color="#94a3b8", line=dict(width=1, color="#475569")),
        dict(size=17, symbol="circle", color="#166534", line=dict(width=1.5, color="#14532d")),
        dict(size=13, symbol="diamond", color="#0f766e", line=dict(width=1, color="#0d9488")),
    ]
    highlights: list[tuple[str, pd.Series, str, float, float]] = [
        (
            "Baseline",
            baseline_row,
            "Baseline (no incremental incentives)",
            float(cur_cost),
            float(cur_p),
        ),
        (
            "Recommended",
            rec,
            "Recommended",
            float(rec["estimated_support_cost"]),
            float(rec["conversion_probability"]),
        ),
        (
            "Aggressive",
            agg,
            "Aggressive (max conversion)",
            float(agg["estimated_support_cost"]),
            float(agg["conversion_probability"]),
        ),
    ]
    seen_xy: set[tuple[float, float]] = set()
    for ms, (lbl, srs, tag, x_pt, y_pt) in zip(marker_styles, highlights, strict=True):
        tup = scenario_hover_customdata_tuple(srs, cm, tag)
        ky = (round(x_pt, 2), round(y_pt, 6))
        if ky in seen_xy and lbl != "Baseline":
            continue
        seen_xy.add(ky)
        fig.add_trace(
            go.Scatter(
                x=[x_pt],
                y=[y_pt],
                mode="markers",
                marker=ms,
                name=lbl,
                customdata=[tup],
                hovertemplate=LADDER_HOVERTEMPLATE,
            )
        )

    fig.update_layout(
        paper_bgcolor="#FAFBFC",
        plot_bgcolor="#FFFFFF",
        height=412,
        margin=dict(l=70, r=32, t=52, b=96),
        showlegend=True,
        font=dict(size=11, color="#475569"),
        xaxis=dict(title=dict(text="Total support cost", font=dict(size=12)), gridcolor="#f1f5f9", zeroline=False),
        yaxis=dict(title=dict(text="Predicted conversion probability", font=dict(size=12)), gridcolor="#f1f5f9"),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.85)",
        ),
        title=dict(text=None),
    )
    return fig


def mk_oem_lift_vs_spend_scatter(df: pd.DataFrame, rec: pd.Series) -> go.Figure:
    """Planning view: conversion lift (pts) vs support spend across evaluated scenarios."""
    if df.empty:
        return go.Figure()
    cap = 4000
    sample = df if len(df) <= cap else df.sample(n=cap, random_state=42)
    lift_pts = sample["conversion_lift_vs_baseline"].astype(float) * 100.0
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=sample["estimated_support_cost"].astype(float),
            y=lift_pts,
            mode="markers",
            marker=dict(size=5, color="#94a3b8", opacity=0.28),
            name="Evaluated scenarios",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[float(rec["estimated_support_cost"])],
            y=[float(rec["conversion_lift_vs_baseline"]) * 100.0],
            mode="markers",
            marker=dict(size=16, color="#166534", line=dict(width=1, color="#14532d")),
            name="Recommended",
        )
    )
    fig.update_layout(
        paper_bgcolor="#FAFBFC",
        plot_bgcolor="#FFFFFF",
        height=340,
        margin=dict(l=56, r=24, t=28, b=72),
        xaxis=dict(title=dict(text="Support spend ($)", font=dict(size=12)), gridcolor="#f1f5f9"),
        yaxis=dict(title=dict(text="Conversion lift (pts)", font=dict(size=12)), gridcolor="#f1f5f9"),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.22,
            x=0,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.9)",
        ),
    )
    return fig


def render_chart_card(title: str, subtitle: str, fig: go.Figure) -> None:
    with ui.element("div").classes("chart-card w-full"):
        with ui.column().classes("chart-header w-full"):
            ui.label(title).classes("chart-title")
            ui.label(subtitle).classes("chart-subtitle")
        payload = fig.to_dict()
        payload.setdefault("config", {})
        payload["config"]["displayModeBar"] = False
        ui.plotly(payload).classes("w-full chart-plot chart-body")


# --- OEM left rail (delegated to executive rail component) -----------------------------


def _render_oem_left_summary_panel(
    state: dict[str, Any],
    meta: dict[str, Any],
    *,
    open_edit: Callable[[str], None],
    run_analysis: Callable[[], Any],
    go_wizard: Callable[[], None],
    optimization_running: bool,
) -> None:
    render_executive_sidebar_oem(
        state,
        meta,
        open_edit=open_edit,
        run_analysis=run_analysis,
        go_wizard=go_wizard,
        optimization_running=optimization_running,
    )


# --- Left summary ----------------------------------------------------------------------
def render_left_summary_panel(
    state: dict[str, Any],
    meta: dict[str, Any],
    *,
    open_edit: Callable[[str], None],
    run_analysis: Callable[[], Any],
    go_wizard: Callable[[], None],
    optimization_running: bool = False,
    optimization_mode: str = "dealer",
) -> None:
    """Sticky executive rail — snapshot → quick edits → run."""
    if optimization_mode == "oem":
        _render_oem_left_summary_panel(
            state,
            meta,
            open_edit=open_edit,
            run_analysis=run_analysis,
            go_wizard=go_wizard,
            optimization_running=optimization_running,
        )
        return

    render_executive_sidebar_dealer(
        state,
        meta,
        open_edit=open_edit,
        run_analysis=run_analysis,
        go_wizard=go_wizard,
        optimization_running=optimization_running,
    )


def _executive_headline(rec: pd.Series, state: dict[str, Any], *, oem: bool) -> str:
    if oem:
        return "Recommended Incentive Strategy"
    lift = float(rec["conversion_lift_vs_baseline"])
    bud = max(float(state.get("sb_max_total_support_budget") or 0), 1.0)
    sup_ratio = float(rec["estimated_support_cost"]) / bud
    if lift >= 0.12 and sup_ratio <= 0.55:
        return "High-Efficiency Conversion Strategy"
    if sup_ratio >= 0.78:
        return "Balanced Growth Package"
    if lift < 0.055:
        return "Margin-Protective Incentive Package"
    return "Recommended Efficient Offer"


def _executive_subcopy(
    state: dict[str, Any],
    business: dict[str, Any],
    *,
    oem: bool,
) -> str:
    if oem:
        return "Campaign structure tuned to regional demand, inventory posture, and macro anchors."
    dti = float(business.get("dti") or 0) * 100.0
    inv = int(state.get("sb_inventory_pressure_ui") or 5)
    return f"Affordability and close-rate focus for ~{dti:.0f}% DTI, inventory pressure {inv}/10, and your caps."


def render_optimization_summary_card(
    meta: dict[str, Any],
    *,
    feasible_n: int,
    scenarios_evaluated: int,
    total_grid: int,
    compact: bool = False,
) -> None:
    rt = meta.get("runtime_seconds")
    if rt is not None:
        try:
            time_s = f"{float(rt):.2f}s"
        except (TypeError, ValueError):
            time_s = "—"
    else:
        time_s = "—"
    ev_val = f"{scenarios_evaluated:,}"
    if total_grid > 0:
        ev_val = f"{scenarios_evaluated:,} / {total_grid:,}"

    with ui.element("div").classes(
        "opt-summary-card opt-summary-card--compact" if compact else "opt-summary-card"
    ):
        ui.label("Run summary" if compact else "Optimization summary").classes(
            "opt-summary-card-title"
            + (" opt-summary-card-title--compact" if compact else "")
        )

        def row(k: str, v: str) -> None:
            with ui.element("div").classes(
                "opt-summary-row opt-summary-row--compact" if compact else "opt-summary-row"
            ):
                ui.label(k).classes("opt-summary-k")
                ui.label(v).classes("opt-summary-v")

        if compact:
            row("Scenarios", f"{feasible_n:,} feasible · {ev_val} evaluated")
            row("Search", str(meta.get("search_mode") or "—"))
            row("Runtime", time_s)
        else:
            row("Search method", str(meta.get("search_mode") or "—"))
            row("Scenarios evaluated", ev_val)
            row("Feasible scenarios", f"{feasible_n:,}")
            row("Optimization time", time_s)


def render_dashboard_hero(
    meta: dict[str, Any],
    *,
    rec: pd.Series,
    state: dict[str, Any],
    business: dict[str, Any],
    feasible_n: int,
    scenarios_evaluated: int,
    total_grid: int,
    relaxed: bool,
    optimization_mode: str = "dealer",
) -> None:
    """Executive summary row: headline + compact run summary (KPIs follow)."""
    oem = optimization_mode == "oem"
    title = _executive_headline(rec, state, oem=oem)
    sub = _executive_subcopy(state, business, oem=oem)
    with ui.row().classes("w-full items-start exec-summary-row"):
        with ui.column().classes("exec-summary-left"):
            ui.label(title).classes("exec-summary-headline")
            ui.label(sub).classes("exec-summary-sub")
            if relaxed:
                ui.label("Constraints were relaxed to find a feasible package.").classes(
                    "exec-summary-warn"
                )
        render_optimization_summary_card(
            meta,
            feasible_n=feasible_n,
            scenarios_evaluated=scenarios_evaluated,
            total_grid=total_grid,
            compact=True,
        )


def render_kpi_row(
    *,
    conv: float,
    lift_pts: float,
    support_cost: float,
    rem_margin: float,
) -> None:
    specs: tuple[tuple[str, str, str, bool], ...] = (
        ("Predicted close", _fmt_pct(conv), "Modeled conversion", True),
        ("Lift vs baseline", _pts(lift_pts), "Incremental probability", False),
        ("Loaded support", _fmt_money(support_cost), "Incentive spend", False),
        ("Margin after support", _fmt_money(rem_margin), "Retained economics", False),
    )
    with ui.element("div").classes("kpi-exec-grid kpi-exec-grid--four"):
        for label, val, hint, accent in specs:
            cell = "kpi-exec-cell kpi-exec-cell--accent" if accent else "kpi-exec-cell"
            with ui.element("div").classes(cell):
                ui.label(label).classes("kpi-exec-label")
                ui.label(val).classes("kpi-exec-value")
                ui.label(hint).classes("kpi-exec-hint")


def render_oem_kpi_row(
    *,
    state: dict[str, Any],
    rec: pd.Series,
    baseline_p: float,
) -> None:
    """Strategic planning KPIs — four compact tiles aligned to OEM planning."""
    _ = baseline_p
    lift = float(rec["conversion_lift_vs_baseline"])
    vol_base = max(1.0, float(state.get("oem_target_sales_volume") or 100))
    vol_idx = lift * vol_base
    support_cost = float(rec["estimated_support_cost"])
    rem_margin = float(rec["remaining_margin_estimate"])
    specs: tuple[tuple[str, str, str, bool], ...] = (
        ("Conversion lift", _pts(lift), "vs baseline incentive", True),
        ("Loaded support", _fmt_money(support_cost), "Program spend", False),
        ("Margin after support", _fmt_money(rem_margin), "Per-unit retained", False),
        ("Volume lift index", f"{vol_idx:,.0f}", "Lift × regional volume proxy", False),
    )
    with ui.element("div").classes("kpi-exec-grid kpi-exec-grid--four"):
        for label, val, hint, accent in specs:
            cell = "kpi-exec-cell kpi-exec-cell--accent" if accent else "kpi-exec-cell"
            with ui.element("div").classes(cell):
                ui.label(label).classes("kpi-exec-label")
                ui.label(val).classes("kpi-exec-value")
                ui.label(hint).classes("kpi-exec-hint")


def _tri_cell(txt: str, *, highlight: bool = False, header: bool = False) -> None:
    st = (
        "font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;"
        if header
        else (
            "font-size:13px;font-weight:700;color:#111827;text-align:right;padding:10px 8px;background:#fdfdfd;"
            if not highlight
            else "font-size:13px;font-weight:700;color:#14532d;text-align:right;padding:10px 8px;background:rgba(220,252,231,0.65);border:1px solid #bbf7d0;"
        )
    )
    ui.label(txt).style(st)


def render_offer_comparison(
    cur_row: pd.Series | None,
    rec: pd.Series,
    agg: pd.Series,
    *,
    cur_support: float | None,
    optimization_mode: str = "dealer",
) -> None:
    def val_conv(s: pd.Series | None, k: str) -> str:
        if s is None:
            return "—"
        return _fmt_pct(float(s[k]))

    def val_money(s: pd.Series | None, k: str) -> str:
        if s is None:
            return "—"
        return _fmt_money(float(s[k]))

    def val_apr_pct(s: pd.Series | None) -> str:
        if s is None:
            return "—"
        return f"{float(s['scenario_dealer_apr']):.2f}%"

    def val_rate_support(s: pd.Series | None) -> str:
        if s is None:
            return "—"
        return f"{int(s['dealer_rate_support_level'])} support points"

    def val_term_months(s: pd.Series | None) -> str:
        if s is None:
            return "—"
        return f"{int(s['loan_term'])} months"

    def val_support_cost(s: pd.Series | None) -> str:
        if s is None and cur_support is None:
            return "—"
        if s is None:
            return _fmt_money(float(cur_support))
        return _fmt_money(float(s["estimated_support_cost"]))

    econ = lambda s: f"{float(s['expected_value']):,.0f}" if s is not None else "—"

    oem = optimization_mode == "oem"
    h_cur = "Current strategy" if oem else "Current offer"
    panel_title = (
        "Strategy comparison — current vs recommended vs aggressive"
        if oem
        else "Current vs Recommended vs Aggressive"
    )
    base_rows = (
        ("Conversion probability", val_conv(cur_row, "conversion_probability"), val_conv(rec, "conversion_probability"), val_conv(agg, "conversion_probability")),
        ("Rate support level", val_rate_support(cur_row), val_rate_support(rec), val_rate_support(agg)),
        ("Dealer APR", val_apr_pct(cur_row), val_apr_pct(rec), val_apr_pct(agg)),
        ("Monthly payment", val_money(cur_row, "scenario_dealer_monthly_payment"), val_money(rec, "scenario_dealer_monthly_payment"), val_money(agg, "scenario_dealer_monthly_payment")),
        ("Loan term", val_term_months(cur_row), val_term_months(rec), val_term_months(agg)),
        ("OEM / Customer cash", val_money(cur_row, "customer_cash"), val_money(rec, "customer_cash"), val_money(agg, "customer_cash")),
        ("Dealer contribution", val_money(cur_row, "dealer_cash"), val_money(rec, "dealer_cash"), val_money(agg, "dealer_cash")),
        ("Loyalty incentive", val_money(cur_row, "loyalty_cash"), val_money(rec, "loyalty_cash"), val_money(agg, "loyalty_cash")),
        ("Conquest incentive", val_money(cur_row, "conquest_cash"), val_money(rec, "conquest_cash"), val_money(agg, "conquest_cash")),
        ("Cash rebate (total)", val_money(cur_row, "total_cash_rebate"), val_money(rec, "total_cash_rebate"), val_money(agg, "total_cash_rebate")),
        ("Estimated support cost", val_support_cost(cur_row), val_support_cost(rec), val_support_cost(agg)),
        ("Remaining margin", val_money(cur_row, "remaining_margin_estimate"), val_money(rec, "remaining_margin_estimate"), val_money(agg, "remaining_margin_estimate")),
    )
    if oem:
        inv_lbl = "Inventory improvement (index)"
        inv_cur = (
            "—"
            if cur_row is None
            else f"{float(cur_row['conversion_lift_vs_baseline']) * 100 / max(float(cur_row.get('estimated_support_cost', 1) or 1), 1):.2f}"
        )
        inv_rec = f"{float(rec['conversion_lift_vs_baseline']) * 100 / max(float(rec['estimated_support_cost']), 1):.2f}"
        inv_agg = f"{float(agg['conversion_lift_vs_baseline']) * 100 / max(float(agg['estimated_support_cost']), 1):.2f}"
        last_row = (inv_lbl, inv_cur, inv_rec, inv_agg)
    else:
        last_row = ("Expected economic score", econ(cur_row), econ(rec), econ(agg))
    rows = base_rows + (last_row,)

    with ui.element("div").classes("dash-panel w-full offer-comparison-panel"):
        ui.label(panel_title).classes("dash-section-h2").style(
            "margin-bottom:16px;text-transform:none;"
        )
        with ui.element("div").classes("offer-comparison-grid-inner"):
            _tri_cell("Metric", header=True)
            _tri_cell(h_cur, header=True)
            _tri_cell("Recommended", header=True)
            _tri_cell("Aggressive", header=True)
            for label, a, b, c in rows:
                ui.label(label).style(
                    "font-size:13px;color:#475569;font-weight:600;"
                    "padding:10px 12px;background:#fafafa;border-bottom:1px solid #f1f5f9;"
                )
                _tri_cell(a)
                _tri_cell(b, highlight=True)
                _tri_cell(c)

        if oem:
            foot = (
                "Recommended balances conversion lift and support spend under OEM constraints. "
                "Aggressive maximizes predicted conversion in the evaluated grid—typically higher "
                "spend with lower incremental efficiency."
            )
        else:
            foot = (
                "Recommended improves conversion while preserving margin under your constraints. "
                "Aggressive is the highest predicted conversion in the evaluated grid—often more spend "
                "with weaker incremental efficiency than the recommendation."
            )
        ui.label(foot).classes("ds-helper mt-4").style("color:#475569;line-height:1.5;font-size:13px;")


def render_top_scenarios_table(
    df: pd.DataFrame,
    rec: pd.Series,
    aggressive: pd.Series,
    *,
    baseline_match: pd.Series | None,
    state: dict[str, Any],
    redraw: Callable[[], None],
    optimization_mode: str = "dealer",
    spectrum_pack: StrategySpectrumPack | None = None,
    spectrum_current: pd.Series | None = None,
) -> None:
    """Curated rows: current (if in grid), recommended, aggressive, then top conversion."""
    state.setdefault("dashboard_show_all_scenarios", False)
    show_all = bool(state.get("dashboard_show_all_scenarios"))
    max_rows = (
        min(SCENARIOS_TABLE_SHOW_ALL_CAP, len(df))
        if show_all
        else SCENARIOS_TABLE_UI_MAX
    )
    curated = _curated_scenario_rows(
        df,
        rec=rec,
        aggressive=aggressive,
        baseline_match=baseline_match,
        max_rows=max_rows,
    )
    total_eval = len(df)

    cols = [
        {"name": "rank", "label": "#", "field": "rank"},
        {"name": "rec", "label": "Scenario", "field": "rec"},
        {"name": "apr", "label": "Dealer APR", "field": "apr"},
        {"name": "pmt", "label": "Monthly payment", "field": "pmt"},
        {"name": "term", "label": "Term", "field": "term"},
        {"name": "cc", "label": "OEM $", "field": "cc"},
        {"name": "dc", "label": "Dealer $", "field": "dc"},
        {"name": "lc", "label": "Loyalty $", "field": "lc"},
        {"name": "cq", "label": "Conquest $", "field": "cq"},
        {"name": "cost", "label": "Support $", "field": "cost"},
        {"name": "conv", "label": "Conversion", "field": "conv"},
        {"name": "lift", "label": "Lift", "field": "lift"},
        {"name": "marg", "label": "Rem. Margin", "field": "marg"},
        {"name": "ev", "label": "Economic score", "field": "ev"},
    ]

    tag_for_kind = (
        {
            "current": "● Current strategy",
            "recommended": "● Recommended strategy",
            "aggressive": "● Aggressive strategy",
            "top": "",
        }
        if optimization_mode == "oem"
        else {
            "current": "● Current offer",
            "recommended": "● Recommended",
            "aggressive": "● Aggressive",
            "top": "",
        }
    )

    rows_out: list[dict[str, Any]] = []
    for disp_i, (kind, _iloc, r) in enumerate(curated, start=1):
        spec_current = False
        spec_conservative = False
        spec_balanced = False
        spec_specialty = False
        if spectrum_pack is not None:
            if spectrum_current is not None:
                spec_current = _same_scenario_levers(r, spectrum_current)
            spec_conservative = _same_scenario_levers(r, spectrum_pack.conservative)
            spec_balanced = _same_scenario_levers(r, spectrum_pack.balanced)
            if spectrum_pack.optional is not None:
                spec_specialty = _same_scenario_levers(r, spectrum_pack.optional)
        rows_out.append(
            {
                "rowKey": f"{kind}-{_iloc}",
                "rank": disp_i,
                "isRecommended": bool(kind == "recommended"),
                "isAggressive": bool(kind == "aggressive"),
                "isCurrent": bool(kind == "current"),
                "specCurrent": spec_current,
                "specConservative": spec_conservative,
                "specBalanced": spec_balanced,
                "specSpecialty": spec_specialty,
                "rec": tag_for_kind.get(kind, ""),
                "apr": f"{float(r['scenario_dealer_apr']):.3f}",
                "pmt": f"{float(r['scenario_dealer_monthly_payment']):,.0f}",
                "term": int(r["loan_term"]),
                "cc": f"{float(r['customer_cash']):,.0f}",
                "dc": f"{float(r['dealer_cash']):,.0f}",
                "lc": f"{float(r['loyalty_cash']):,.0f}",
                "cq": f"{float(r['conquest_cash']):,.0f}",
                "cost": f"{float(r['estimated_support_cost']):,.0f}",
                "conv": f"{float(r['conversion_probability']):.4f}",
                "lift": _fmt_pct(float(r["conversion_lift_vs_baseline"])),
                "marg": f"{float(r['remaining_margin_estimate']):,.0f}",
                "ev": f"{float(r['expected_value']):,.0f}",
            }
        )

    def _toggle_show_all() -> None:
        state["dashboard_show_all_scenarios"] = not bool(
            state.get("dashboard_show_all_scenarios")
        )
        redraw()

    with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
        cap_note = (
            f" (capped at {SCENARIOS_TABLE_SHOW_ALL_CAP:,} rows for responsiveness)"
            if show_all and total_eval > SCENARIOS_TABLE_SHOW_ALL_CAP
            else ""
        )
        hint = (
            " Tinted rows match the strategy comparison table when that package appears in this list."
            if spectrum_pack is not None
            else ""
        )
        ui.label(
            f"Showing {len(rows_out)} curated rows of {total_eval:,} evaluated scenarios · "
            "current, recommended, aggressive, then highest conversion. "
            f"Excel export still includes top {SCENARIOS_TABLE_TOP_N} by conversion."
            f"{cap_note}{hint}"
        ).classes("text-xs").style(f"color:{TEXT_SECONDARY};max-width:720px;line-height:1.45;")

        def export_excel() -> None:
            try:
                data = build_top_scenarios_excel_bytes(df, rec)
                ui.download(
                    data,
                    f"subvention_top_{SCENARIOS_TABLE_TOP_N}_scenarios.xlsx",
                )
            except Exception as e:
                ui.notify(f"Excel export failed: {e}", type="negative")

        with ui.row().classes("items-center gap-2 shrink-0 flex-wrap"):
            if total_eval > SCENARIOS_TABLE_UI_MAX:
                ui.button(
                    "Show top scenarios only" if show_all else "Show all scenarios",
                    on_click=_toggle_show_all,
                ).props("outline dense no-caps").style(
                    f"color:#334155;border-color:{BORDER};"
                )
            ui.button("Download Excel (top 100)", on_click=export_excel).props(
                "outline dense no-caps"
            ).classes("shrink-0").style(f"color:#334155;border-color:{BORDER};")

    tbl = ui.table(columns=cols, rows=rows_out, row_key="rowKey").props("dense flat bordered").classes(
        "w-full text-sm scenarios-results-table mt-3"
    )
    tbl.add_slot(
        "body",
        r"""
        <q-tr :props="props" :class="{
          'scenario-row--recommended': props.row.isRecommended,
          'scenario-row--aggressive': props.row.isAggressive,
          'scenario-row--current': props.row.isCurrent,
          'scenario-row--spec-current': props.row.specCurrent,
          'scenario-row--spec-conservative': props.row.specConservative,
          'scenario-row--spec-balanced': props.row.specBalanced,
          'scenario-row--spec-specialty': props.row.specSpecialty
        }">
            <q-td v-for="col in props.cols" :key="col.name" :props="props">
                {{ props.row[col.field] }}
            </q-td>
        </q-tr>
        """,
    )


def render_model_details_debug(
    *,
    pipeline: Any,
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
    business: dict[str, Any],
    result_df: pd.DataFrame,
    rec: pd.Series,
) -> None:
    md = get_model_metadata() or {}
    preview = ""
    try:
        preview = json.dumps(md, indent=2)
        if len(preview) > 12000:
            preview = preview[:12000] + "\n…(truncated)"
    except Exception as e:
        preview = str(e)

    schema_cols = list(schema.get("required_columns") or [])[:240]
    try:
        row_model, p0, err = _predict_scenario_row(
            apply_offer_scenario_levers(
                business,
                support_level=float(rec["dealer_rate_support_level"]),
                customer_cash=float(rec["customer_cash"]),
                dealer_cash=float(rec["dealer_cash"]),
                loyalty_cash=float(rec["loyalty_cash"]),
                conquest_cash=float(rec["conquest_cash"]),
                loan_term=int(rec["loan_term"]),
            ),
            pipeline,
            schema,
            sample_defaults,
        )
        mr_preview = ""
        if row_model is None:
            mr_preview = err or "(no row)"
        else:
            kk = sorted(row_model.keys())[:60]
            mr_preview = json.dumps({k: row_model[k] for k in kk}, indent=2, default=str)
    except Exception as e:
        mr_preview = str(e)

    with ui.expansion("Technical details for validation only", value=False).classes(
        "rounded-xl"
    ).style(
        f"border:1px solid {BORDER};background:#fff;padding:4px 12px;margin-top:var(--s-5);"
    ):
        ui.separator()
        ui.label("Model metadata").classes("text-xs font-bold mt-4").style(
            "color: #64748b; text-transform: uppercase"
        )
        ui.code(preview).classes("max-h-96 overflow-auto text-xs w-full mt-2")
        ui.label("Feature schema columns (truncated list)").classes("text-xs font-bold mt-4").style(
            "color: #64748b; text-transform: uppercase"
        )
        ui.code("\n".join(schema_cols[:120])).classes("max-h-64 overflow-auto text-xs w-full mt-2")
        ui.label("Model-ready row excerpt (recommended scenario)").classes("text-xs font-bold mt-4").style(
            "color: #64748b; text-transform: uppercase"
        )
        ui.code(mr_preview).classes("max-h-96 overflow-auto text-xs w-full mt-2")
        ui.label("Raw optimizer result — top 25 rows CSV snippet").classes("text-xs font-bold mt-4").style(
            "color: #64748b; text-transform: uppercase"
        )
        try:
            snippet = (
                result_df.sort_values("expected_value", ascending=False)
                .head(25)
                .to_csv(index=False)
            )
        except Exception as e:
            snippet = str(e)
        ui.code(snippet[:10000]).classes("max-h-96 overflow-auto text-xs w-full mt-2")


def render_dashboard(
    *,
    state: dict[str, Any],
    result_df: pd.DataFrame,
    rec: pd.Series,
    aggressive: pd.Series,
    baseline_p: float,
    feasible_n: int,
    meta: dict[str, Any],
    relaxed: bool,
    pipeline: Any,
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
    redraw: Callable[[], None],
    run_analysis: Callable[..., Any],
    open_edit: Callable[[str], None],
    go_wizard: Callable[[], None],
    optimization_running: bool = False,
    optimization_mode: str = "dealer",
) -> None:
    """Post-submit layout: left summary + executive dashboard A→H."""
    oem = optimization_mode == "oem"
    business = build_business_inputs(state)
    cm = float(state.get("sb_cost_multiplier") or 0.65)
    term = int(rec["loan_term"])
    scen_base = apply_offer_scenario_levers(
        business,
        support_level=0.0,
        customer_cash=0.0,
        dealer_cash=0.0,
        loyalty_cash=0.0,
        conquest_cash=0.0,
        loan_term=term,
    )
    cur_support = float(estimate_support_cost(scen_base, 0.0, cm))
    margin_u = float(business["expected_unit_margin"])
    la0 = float(scen_base.get("loan_amount") or business.get("loan_amount") or 0.0)
    if la0 <= 0:
        la0 = float(rec["scenario_loan_amount"])
    rm_b, _, err_b = _predict_scenario_row(scen_base, pipeline, schema, sample_defaults)

    if rm_b is not None and not err_b:
        baseline_hover_row = pd.Series(
            {
                "scenario_dealer_apr": float(rm_b["dealer_apr"]),
                "scenario_dealer_monthly_payment": float(rm_b["dealer_monthly_payment"]),
                "loan_term": term,
                "customer_cash": 0.0,
                "dealer_cash": 0.0,
                "loyalty_cash": 0.0,
                "conquest_cash": 0.0,
                "total_cash_rebate": float(rm_b.get("total_cash_rebate", 0.0)),
                "scenario_loan_amount": la0,
                "dealer_rate_support_level": 0,
                "estimated_support_cost": cur_support,
                "conversion_probability": float(baseline_p),
                "remaining_margin_estimate": margin_u - cur_support,
            }
        )
    else:
        baseline_hover_row = pd.Series(
            {
                "scenario_dealer_apr": float(rec["scenario_dealer_apr"]),
                "scenario_dealer_monthly_payment": float(rec["scenario_dealer_monthly_payment"]),
                "loan_term": term,
                "customer_cash": 0.0,
                "dealer_cash": 0.0,
                "loyalty_cash": 0.0,
                "conquest_cash": 0.0,
                "total_cash_rebate": 0.0,
                "scenario_loan_amount": float(rec["scenario_loan_amount"]),
                "dealer_rate_support_level": 0,
                "estimated_support_cost": cur_support,
                "conversion_probability": float(baseline_p),
                "remaining_margin_estimate": margin_u - cur_support,
            }
        )

    cur_row: pd.Series | None = None
    if rm_b is not None and not err_b:
        ev_cur = float(baseline_p) * margin_u - cur_support
        cur_row = baseline_hover_row.copy()
        cur_row["expected_value"] = float(ev_cur)

    scenarios_evaluated = int(meta.get("scenarios_evaluated") or len(result_df))
    total_grid = int(meta.get("total_grid_scenarios") or 0)

    with ui.element("div").classes("dashboard-shell w-full"):
        with ui.column().classes("sidebar-panel w-full items-stretch"):
            render_left_summary_panel(
                state,
                meta,
                open_edit=open_edit,
                run_analysis=run_analysis,
                go_wizard=go_wizard,
                optimization_running=optimization_running,
                optimization_mode=optimization_mode,
            )
        with ui.column().classes("results-main dash-canvas w-full"):
            render_dashboard_hero(
                meta,
                rec=rec,
                state=state,
                business=business,
                feasible_n=feasible_n,
                scenarios_evaluated=scenarios_evaluated,
                total_grid=total_grid,
                relaxed=relaxed,
                optimization_mode=optimization_mode,
            )
            # Dealer and OEM use different KPI semantics; keep branches separate.
            if oem:
                render_oem_kpi_row(state=state, rec=rec, baseline_p=float(baseline_p))
            else:
                render_kpi_row(
                    conv=float(rec["conversion_probability"]),
                    lift_pts=float(rec["conversion_lift_vs_baseline"]),
                    support_cost=float(rec["estimated_support_cost"]),
                    rem_margin=float(rec["remaining_margin_estimate"]),
                )

            def _render_advanced_scenario_exploration() -> None:
                ladder = mk_incentive_ladder_fig(
                    result_df,
                    rec,
                    cur_cost=cur_support,
                    cur_p=float(baseline_p),
                    agg=aggressive,
                    cm=cm,
                    baseline_row=baseline_hover_row,
                )
                render_chart_card(
                    "Conversion response by support spend",
                    "Efficient-frontier view across evaluated scenarios (analyst).",
                    ladder,
                )
                render_chart_card(
                    "Conversion lift vs. support spend",
                    "Full scenario cloud — recommended highlighted.",
                    mk_oem_lift_vs_spend_scatter(result_df, rec),
                )
                spectrum_pack = build_strategy_spectrum_pack(result_df, rec, aggressive)
                ui.label("Key scenarios").classes("dash-section-h2 w-full").style(
                    "margin-top:var(--s-2);"
                )
                render_top_scenarios_table(
                    result_df,
                    rec,
                    aggressive,
                    baseline_match=baseline_hover_row,
                    state=state,
                    redraw=redraw,
                    optimization_mode=optimization_mode,
                    spectrum_pack=spectrum_pack,
                    spectrum_current=cur_row,
                )
                render_model_details_debug(
                    pipeline=pipeline,
                    schema=schema,
                    sample_defaults=sample_defaults,
                    business=business,
                    result_df=result_df,
                    rec=rec,
                )

            render_executive_results_body(
                state=state,
                result_df=result_df,
                rec=rec,
                aggressive=aggressive,
                baseline_p=float(baseline_p),
                cur_row=cur_row,
                business=business,
                cm=cm,
                optimization_mode=optimization_mode,
                redraw=redraw,
                advanced_content=_render_advanced_scenario_exploration,
            )
