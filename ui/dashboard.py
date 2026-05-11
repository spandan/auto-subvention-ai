"""Executive results dashboard + left scenario summary + edit modal hooks."""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from nicegui import ui
from nicegui.background_tasks import create as create_background_task

from services.feature_engineering import (
    build_business_inputs,
    business_dti_ratio,
)
from services.model_service import get_model_metadata
from services.optimizer import (
    _predict_scenario_row,
    apply_offer_scenario_levers,
    estimate_support_cost,
)
from ui.theme import BORDER, TEXT_SECONDARY
from ui.wizard import render_section_for_edit


# Cap UI + export so we never bind huge scenario grids to the browser.
SCENARIOS_TABLE_TOP_N = 100


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


def mk_support_horizontal_stacked(labels: list[str], values: list[float], *, embedded: bool = False) -> go.Figure:
    """Dashboard-wide stacked bar; embedded=True removes inline title / tightens for chart-card chrome."""
    fig = go.Figure()
    colors = ["#334155", "#475569", "#64748b", "#0f766e", "#b45309"]
    j = 0
    for lab, val in zip(labels, values, strict=False):
        if val <= 1e-9:
            continue
        fig.add_trace(
            go.Bar(
                name=lab,
                x=[float(val)],
                y=["Support breakdown"],
                orientation="h",
                marker=dict(color=colors[j % len(colors)]),
                hovertemplate=f"<b>{lab}</b>: $%{{x:,.0f}}<extra></extra>",
            )
        )
        j += 1
    if embedded:
        # Legend on the right so the x-axis title is not stacked on horizontal legend text.
        fig.update_layout(
            barmode="stack",
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            height=220,
            margin=dict(l=64, r=138, t=20, b=64),
            showlegend=True,
            font=dict(size=11, color="#475569"),
            xaxis=dict(
                title=dict(text="Dollars ($)", font=dict(size=12), standoff=10),
                gridcolor="#f1f5f9",
                automargin=True,
            ),
            yaxis=dict(showgrid=False),
            legend=dict(
                orientation="v",
                xanchor="left",
                x=1.01,
                yanchor="middle",
                y=0.5,
                font=dict(size=11),
                bgcolor="rgba(255,255,255,0.96)",
                bordercolor="#e2e8f0",
                borderwidth=1,
            ),
            title=dict(text=None),
        )
    else:
        fig.update_layout(
            barmode="stack",
            paper_bgcolor="#FAFBFC",
            plot_bgcolor="#FFFFFF",
            height=180,
            margin=dict(l=140, r=40, t=64, b=48),
            title=dict(text="<b>Recommended support cost breakdown</b>", font=dict(size=14, color="#0f172a")),
            font=dict(size=11, color="#475569"),
            xaxis=dict(title=dict(text="Dollars ($)"), gridcolor="#f1f5f9"),
            yaxis=dict(showgrid=False),
            showlegend=True,
            legend=dict(orientation="v", x=1.01, y=0.5, font=dict(size=10)),
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


def breakdown_components(rec: pd.Series, cm: float) -> tuple[list[str], list[float]]:
    la = float(rec["scenario_loan_amount"])
    sup = float(rec["dealer_rate_support_level"])
    apr_cost = la * (sup / 10000.0) * cm
    return (
        ["APR Support", "OEM / Customer Cash", "Dealer Cash", "Loyalty", "Conquest"],
        [
            apr_cost,
            float(rec["customer_cash"]),
            float(rec["dealer_cash"]),
            float(rec["loyalty_cash"]),
            float(rec["conquest_cash"]),
        ],
    )


# --- Left summary ----------------------------------------------------------------------
def render_left_summary_panel(
    state: dict[str, Any],
    meta: dict[str, Any],
    *,
    open_edit: Callable[[str], None],
    run_analysis: Callable[[], Any],
    go_wizard: Callable[[], None],
) -> None:
    """Sticky executive rail — snapshot → quick edits → run."""
    dti_pct = business_dti_ratio(state) * 100.0
    fico = int(state.get("sb_fico_score", 0))
    segment = str(state.get("sb_customer_segment") or "—")
    make = str(state.get("sb_make") or "")
    model = str(state.get("sb_model_name") or "")
    loan_amt = float(state.get("sb_loan_amount") or 0)
    loan_term = int(state.get("sb_primary_loan_term") or 0)
    max_sup = int(state.get("sb_max_apr_rate_support") or 0)
    mk_rate = float(state.get("sb_market_rate_index") or 0.0)
    search_txt = str(meta.get("search_mode") or "—")

    # --- Snapshot header ---
    with ui.element("div").classes("snapshot-pane-heading"):
        ui.label("Scenario snapshot").classes("snapshot-pane-title")
        ui.label("Current inputs").classes("snapshot-pane-sub")

    # --- Snapshot cards ---
    with ui.element("div").classes("rail-section").style("margin-top: 0;"):
        with ui.element("div").classes("snapshot-card"):
            ui.label("Customer").classes("snapshot-label")
            ui.label(f"{fico} FICO").classes("snapshot-primary")
            ui.label(f"DTI {dti_pct:.1f}%").classes("snapshot-secondary")
            ui.label(segment).classes("snapshot-secondary")
        with ui.element("div").classes("snapshot-card"):
            ui.label("Vehicle").classes("snapshot-label")
            ui.label((f"{make} {model}".strip()) or "—").classes("snapshot-primary")
            ui.label(f"{_fmt_money_k(loan_amt)} financed").classes("snapshot-secondary")
            if loan_term > 0:
                ui.label(f"{loan_term} mo loan").classes("snapshot-secondary")
        with ui.element("div").classes("snapshot-card"):
            ui.label("Market").classes("snapshot-label")
            ui.label(f"Competitor APR {float(state.get('sb_competitor_apr') or 0):.2f}%").classes(
                "snapshot-primary"
            )
            ui.label(
                f"Cashback {_fmt_money(float(state.get('sb_competitor_cashback') or 0))}"
            ).classes("snapshot-secondary")
            ui.label(f"Market rate {mk_rate:.2f}%").classes("snapshot-secondary")
        with ui.element("div").classes("snapshot-card"):
            ui.label("Optimization").classes("snapshot-label")
            ui.label(
                f"Budget {_fmt_money(float(state.get('sb_max_total_support_budget') or 0))}"
            ).classes("snapshot-primary")
            ui.label(f"Support cap {max_sup} support points").classes("snapshot-secondary")
            ui.label(search_txt).classes("snapshot-secondary")

    # --- Quick actions (single bordered stack — visually tied to snapshot cards) ---
    with ui.element("div").classes("rail-section"):
        ui.label("Adjust inputs").classes("rail-section-label")
        with ui.element("div").classes("rail-btn-stack"):
            qa: tuple[tuple[str, str], ...] = (
                ("customer", "Customer"),
                ("vehicle", "Vehicle"),
                ("dealer_inv", "Dealer & inventory"),
                ("financing", "Optimization"),
                ("market", "Market"),
            )
            for sec, lbl in qa:
                ui.button(
                    lbl,
                    on_click=lambda _, s=sec: open_edit(s),
                ).props("flat dense no-caps").classes("rail-edit-btn")

    # --- Run ---
    with ui.element("div").classes("rail-section"):
        ui.label("Run Actions").classes("rail-section-label")
        with ui.element("div").classes("rail-run-stack"):
            ui.button(
                "Re-run Optimization",
                on_click=lambda: (
                    create_background_task(run_analysis(), name="run_analysis")
                    if asyncio.iscoroutinefunction(run_analysis)
                    else run_analysis()
                ),
            ).props(
                "unelevated dense no-caps"
            ).classes("btn-dash btn-dash-primary")
            ui.button(
                "Start New Scenario",
                on_click=go_wizard,
            ).props("outline dense no-caps").classes("btn-dash rail-run-outline")


def render_optimization_summary_card(
    meta: dict[str, Any],
    *,
    feasible_n: int,
    scenarios_evaluated: int,
    total_grid: int,
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

    with ui.element("div").classes("opt-summary-card"):
        ui.label("Optimization summary").classes("opt-summary-card-title")

        def row(k: str, v: str) -> None:
            with ui.element("div").classes("opt-summary-row"):
                ui.label(k).classes("opt-summary-k")
                ui.label(v).classes("opt-summary-v")

        row("Search method", str(meta.get("search_mode") or "—"))
        row("Scenarios evaluated", ev_val)
        row("Feasible scenarios", f"{feasible_n:,}")
        row("Optimization time", time_s)


def render_dashboard_hero(
    meta: dict[str, Any],
    *,
    feasible_n: int,
    scenarios_evaluated: int,
    total_grid: int,
    relaxed: bool,
) -> None:
    """Title + summary card on one row; badge row directly under (KPIs follow)."""
    with ui.row().classes("w-full items-start dash-hero-row"):
        with ui.column().classes().style("min-width:0;flex:1 1 360px;"):
            ui.label("Recommended Efficient Offer").classes("dash-title-main")
            ui.label(
                "The optimizer selected the package with the best conversion-to-cost tradeoff "
                "under your current constraints."
            ).classes("dash-title-sub")
        render_optimization_summary_card(
            meta,
            feasible_n=feasible_n,
            scenarios_evaluated=scenarios_evaluated,
            total_grid=total_grid,
        )

    with ui.row().classes("w-full items-center dash-badge-row"):
        ui.label("Recommended").classes("rs-badge")
        if relaxed:
            ui.label("Constraints relaxed for feasibility").classes("text-xs").style(
                f"color:{TEXT_SECONDARY};font-weight:600;"
            )


def render_kpi_row(
    *,
    conv: float,
    lift_pts: float,
    support_cost: float,
    rem_margin: float,
    apr_pct: float,
    monthly_pay: float,
) -> None:
    specs: tuple[tuple[str, str, str, bool], ...] = (
        ("Predicted conversion", _fmt_pct(conv), "Expected close probability", True),
        ("Conversion lift", _pts(lift_pts), "vs. baseline incentive package", False),
        ("Estimated support cost", _fmt_money(support_cost), "Fully loaded incentive spend", False),
        ("Remaining margin", _fmt_money(rem_margin), "After estimated support", False),
        ("Recommended APR", f"{apr_pct:.2f}%", "Subvented dealer rate", False),
        ("Monthly payment", _fmt_money(monthly_pay), "Estimated buyer payment", False),
    )
    with ui.element("div").classes("kpi-exec-grid"):
        for label, val, hint, accent in specs:
            cell = "kpi-exec-cell kpi-exec-cell--accent" if accent else "kpi-exec-cell"
            with ui.element("div").classes(cell):
                ui.label(label).classes("kpi-exec-label")
                ui.label(val).classes("kpi-exec-value")
                ui.label(hint).classes("kpi-exec-hint")


def render_recommended_package_card(rec: pd.Series) -> None:
    with ui.element("div").classes("dash-panel w-full"):
        ui.label("Recommended incentive package").classes("dash-section-h2").style(
            "margin-bottom:12px;"
        )

        defs = (
            ("Rate Support Level", f"{int(rec['dealer_rate_support_level'])} support points"),
            ("Dealer APR", f"{float(rec['scenario_dealer_apr']):.2f}%"),
            ("Monthly Payment", _fmt_money(float(rec["scenario_dealer_monthly_payment"]))),
            ("Loan Term", f"{int(rec['loan_term'])} months"),
            ("OEM / Customer Cash", _fmt_money(float(rec["customer_cash"]))),
            ("Dealer Contribution", _fmt_money(float(rec["dealer_cash"]))),
            ("Loyalty Incentive", _fmt_money(float(rec["loyalty_cash"]))),
            ("Conquest Incentive", _fmt_money(float(rec["conquest_cash"]))),
            ("Estimated Support Cost", _fmt_money(float(rec["estimated_support_cost"]))),
            ("Remaining Margin", _fmt_money(float(rec["remaining_margin_estimate"]))),
        )
        for k, v in defs:
            with ui.element("div").classes("def-row"):
                ui.label(k).style("font-size:13px;color:#64748b;font-weight:500;")
                ui.label(str(v)).style("font-size:13px;color:#111827;font-weight:700;text-align:right;")

        ui.label(
            "Recommended package improves conversion while preserving margin. Higher-spend packages "
            "produced additional conversion, but with weaker incremental efficiency."
        ).classes("ds-helper mt-4").style("color:#475569;line-height:1.5;font-size:13px;")


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
) -> None:
    def val_conv(s: pd.Series | None, k: str) -> str:
        if s is None:
            return "—"
        return _fmt_pct(float(s[k]))

    def val_money(s: pd.Series | None, k: str) -> str:
        if s is None:
            return "—"
        return _fmt_money(float(s[k]))

    def val_float(s: pd.Series | None, k: str, nd: int = 3) -> str:
        if s is None:
            return "—"
        return f"{float(s[k]):.{nd}f}"

    econ = lambda s: f"{float(s['expected_value']):,.0f}" if s is not None else "—"

    rows = (
        ("Conversion probability", val_conv(cur_row, "conversion_probability"), val_conv(rec, "conversion_probability"), val_conv(agg, "conversion_probability")),
        ("Estimated support cost", ("—" if cur_support is None else _fmt_money(cur_support)), _fmt_money(float(rec["estimated_support_cost"])), _fmt_money(float(agg["estimated_support_cost"]))),
        ("Dealer APR", val_float(cur_row, "scenario_dealer_apr"), val_float(rec, "scenario_dealer_apr"), val_float(agg, "scenario_dealer_apr")),
        ("Monthly payment", val_money(cur_row, "scenario_dealer_monthly_payment"), val_money(rec, "scenario_dealer_monthly_payment"), val_money(agg, "scenario_dealer_monthly_payment")),
        ("Cash rebate (total)", val_money(cur_row, "total_cash_rebate"), val_money(rec, "total_cash_rebate"), val_money(agg, "total_cash_rebate")),
        ("Remaining margin", val_money(cur_row, "remaining_margin_estimate"), val_money(rec, "remaining_margin_estimate"), val_money(agg, "remaining_margin_estimate")),
        ("Expected economic score", econ(cur_row), econ(rec), econ(agg)),
    )

    with ui.element("div").classes("dash-panel w-full").style("overflow-x:auto;"):
        ui.label("Current vs Recommended vs Aggressive").classes("dash-section-h2").style(
            "margin-bottom:16px;text-transform:none;"
        )
        with ui.element("div").style(
            "display:grid;"
            "grid-template-columns: 1fr 1fr 1fr 1fr;"
            "gap:0;"
            "border:1px solid #e5e7eb;"
            "border-radius:12px;"
            "overflow:hidden;"
        ):
            _tri_cell("Metric", header=True)
            _tri_cell("Current offer", header=True)
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


def render_top_scenarios_table(df: pd.DataFrame, rec: pd.Series) -> None:
    """Show up to SCENARIOS_TABLE_TOP_N rows by predicted conversion — never full grid."""
    sliced = top_scenarios_ranked(df, n=SCENARIOS_TABLE_TOP_N).reset_index(drop=True)
    sliced.insert(0, "rank", range(1, len(sliced) + 1))

    total_eval = len(df)

    cols = [
        {"name": "rank", "label": "Rank", "field": "rank"},
        {"name": "rec", "label": "Recommendation", "field": "rec"},
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

    rows_out: list[dict[str, Any]] = []
    for _, r in sliced.iterrows():
        is_rec = _row_matches_recommendation(r, rec)
        rows_out.append({
            "rank": int(r["rank"]),
            "isRecommended": bool(is_rec),
            "rec": "● Recommended" if is_rec else "",
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
        })

    with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
        ui.label(
            f"Showing {len(rows_out)} of {total_eval:,} evaluated scenarios · "
            f"sorted by conversion (highest first)."
        ).classes("text-xs").style(f"color:{TEXT_SECONDARY};max-width:640px;line-height:1.45;")

        def export_excel() -> None:
            try:
                data = build_top_scenarios_excel_bytes(df, rec)
                ui.download(
                    data,
                    f"subvention_top_{SCENARIOS_TABLE_TOP_N}_scenarios.xlsx",
                )
            except Exception as e:
                ui.notify(f"Excel export failed: {e}", type="negative")

        ui.button("Download Excel (top 100)", on_click=export_excel).props(
            "outline dense no-caps"
        ).classes("shrink-0").style(f"color:#334155;border-color:{BORDER};")

    tbl = ui.table(columns=cols, rows=rows_out, row_key="rank").props("dense flat bordered").classes(
        "w-full text-sm scenarios-results-table mt-3"
    )
    tbl.add_slot(
        "body",
        r"""
        <q-tr :props="props" :class="props.row.isRecommended ? 'scenario-row--recommended' : ''">
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
) -> None:
    """Post-submit layout: left summary + executive dashboard A→H."""
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
        cur_row = pd.Series(
            {
                "conversion_probability": float(baseline_p),
                "scenario_dealer_apr": float(rm_b["dealer_apr"]),
                "scenario_dealer_monthly_payment": float(rm_b["dealer_monthly_payment"]),
                "total_cash_rebate": float(rm_b.get("total_cash_rebate", 0.0)),
                "remaining_margin_estimate": margin_u - cur_support,
                "expected_value": ev_cur,
            }
        )

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
            )
        with ui.column().classes("results-main dash-canvas w-full"):
            render_dashboard_hero(
                meta,
                feasible_n=feasible_n,
                scenarios_evaluated=scenarios_evaluated,
                total_grid=total_grid,
                relaxed=relaxed,
            )
            render_kpi_row(
                conv=float(rec["conversion_probability"]),
                lift_pts=float(rec["conversion_lift_vs_baseline"]),
                support_cost=float(rec["estimated_support_cost"]),
                rem_margin=float(rec["remaining_margin_estimate"]),
                apr_pct=float(rec["scenario_dealer_apr"]),
                monthly_pay=float(rec["scenario_dealer_monthly_payment"]),
            )
            render_recommended_package_card(rec)
            render_offer_comparison(cur_row, rec, aggressive, cur_support=cur_support)
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
                "Shows how conversion probability rises as incentive spend increases "
                "(efficient-frontier bands use the strongest scenario observed in each cost band).",
                ladder,
            )
            labs, vals = breakdown_components(rec, cm)
            render_chart_card(
                "Recommended support cost breakdown",
                "Estimated dollars by lever for the recommendation — APR support reflects "
                "subvention cost tied to dealer rate.",
                mk_support_horizontal_stacked(labs, vals, embedded=True),
            )
            ui.label("Top 100 scenarios").classes("dash-section-h2 w-full").style(
                "margin-top:var(--s-2);"
            )
            render_top_scenarios_table(result_df, rec)
            render_model_details_debug(
                pipeline=pipeline,
                schema=schema,
                sample_defaults=sample_defaults,
                business=business,
                result_df=result_df,
                rec=rec,
            )
