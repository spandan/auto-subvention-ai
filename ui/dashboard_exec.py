"""Executive decision-support results layout (replaces chart-heavy default dashboard body)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from nicegui import ui

from services.feature_engineering import business_dti_ratio
from services.recommendation_narrative import (
    build_reasoning_bullets,
)
from services.strategy_spectrum import StrategySpectrumPack, build_strategy_spectrum_pack
from ui.theme import TEXT_SECONDARY


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _pct(x: float, nd: int = 2) -> str:
    return f"{100.0 * x:.{nd}f}%"


_BREAKDOWN_COLORS = ("#334155", "#475569", "#64748b", "#0f766e", "#b45309")


def _breakdown_lists(rec: pd.Series, cm: float) -> tuple[list[str], list[float]]:
    la = float(rec["scenario_loan_amount"])
    sup = float(rec["dealer_rate_support_level"])
    apr_cost = la * (sup / 10000.0) * cm
    return (
        ["OEM APR support", "OEM cash", "Dealer cash", "Loyalty incentive", "Conquest incentive"],
        [
            apr_cost,
            float(rec["customer_cash"]),
            float(rec["dealer_cash"]),
            float(rec["loyalty_cash"]),
            float(rec["conquest_cash"]),
        ],
    )


def _render_exec_support_breakdown(labs: list[str], vals: list[float], total_support: float) -> None:
    """Where support dollars sit — mirrors model inputs; total uses desk estimated support."""
    pos = sum(max(v, 0.0) for v in vals)
    denom = pos if pos > 1e-6 else 1.0
    ui.label("Support cost breakdown").classes("exec-decision-micro exec-decision-micro--breakdown")
    with ui.element("div").classes("exec-support-stack"):
        if pos < 1e-6:
            ui.element("div").classes("exec-support-stack-empty")
        else:
            for i, val in enumerate(vals):
                v = max(float(val), 0.0)
                if v < 1e-9:
                    continue
                c = _BREAKDOWN_COLORS[i % len(_BREAKDOWN_COLORS)]
                ui.element("div").classes("exec-support-stack-seg").style(
                    f"flex:{v} 1 0;min-width:3px;background:{c};"
                )
    with ui.column().classes("exec-breakdown-list w-full"):
        for i, (lab, val) in enumerate(zip(labs, vals, strict=False)):
            v = max(float(val), 0.0)
            pct = 100.0 * v / denom if denom > 1e-6 else 0.0
            c = _BREAKDOWN_COLORS[i % len(_BREAKDOWN_COLORS)]
            with ui.row().classes("exec-breakdown-row w-full items-center no-wrap"):
                with ui.row().classes("items-center gap-2 flex-1 min-w-0"):
                    ui.element("div").classes("exec-breakdown-dot").style(f"background:{c};")
                    ui.label(lab).classes("exec-breakdown-name")
                ui.label(f"{pct:.0f}%").classes("exec-breakdown-pct")
                ui.label(_money(v)).classes("exec-breakdown-amt")
    with ui.row().classes("exec-breakdown-total w-full items-center justify-between"):
        ui.label("Total estimated support").classes("exec-breakdown-total-l")
        ui.label(_money(total_support)).classes("exec-breakdown-total-v")


def render_compact_edit_launchers(
    open_edit: Callable[[str], None],
    specs: tuple[tuple[str, str, str], ...],
) -> None:
    """Single icon row — (section_key, material_icon, tooltip)."""
    with ui.row().classes("rail-edit-icon-row"):
        for sec, icon, tip in specs:
            def make_handler(section: str = sec) -> Callable[[], None]:
                return lambda: open_edit(section)

            ui.button(on_click=make_handler()).props(
                f"flat round dense unelevated icon={icon}"
            ).tooltip(tip).classes("rail-icon-btn")


def _plotly_card(title: str, subtitle: str, fig: go.Figure) -> None:
    with ui.element("div").classes("exec-chart-card w-full"):
        with ui.column().classes("w-full"):
            ui.label(title).classes("exec-chart-title")
            if subtitle:
                ui.label(subtitle).classes("exec-chart-sub")
        payload = fig.to_dict()
        payload.setdefault("config", {})
        payload["config"]["displayModeBar"] = False
        ui.plotly(payload).classes("w-full")


def mk_offer_spectrum_tradeoff_fig(pack: StrategySpectrumPack) -> go.Figure:
    """Named strategies only — conversion vs support cost (executive view)."""
    named: list[tuple[str, pd.Series, str]] = [
        ("Conservative", pack.conservative, "#94a3b8"),
        ("Recommended", pack.recommended, "#166534"),
        ("Balanced alternative", pack.balanced, "#64748b"),
        ("Aggressive growth", pack.aggressive, "#b45309"),
    ]
    if pack.optional is not None:
        named.append((pack.optional_label or "Alternative mix", pack.optional, "#334155"))

    fig = go.Figure()
    for label, row, color in named:
        fig.add_trace(
            go.Scatter(
                x=[float(row["estimated_support_cost"])],
                y=[float(row["conversion_probability"])],
                mode="markers+text",
                name=label,
                text=[label],
                textposition="top center",
                textfont=dict(size=10, color="#475569"),
                marker=dict(size=18, color=color, line=dict(width=2, color="#ffffff")),
                hovertemplate=(
                    f"<b>{label}</b><br>Support: $%{{x:,.0f}}<br>Conversion: %{{y:.1%}}<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#fafafa",
        height=280,
        margin=dict(l=52, r=24, t=20, b=56),
        xaxis=dict(title="Support cost ($)", gridcolor="#f1f5f9", zeroline=False),
        yaxis=dict(title="Predicted conversion", tickformat=".0%", gridcolor="#f1f5f9"),
        showlegend=False,
        font=dict(size=11, color="#475569"),
    )
    return fig


def _oem_cash_stack(row: pd.Series) -> str:
    return _money(
        float(row["customer_cash"])
        + float(row["dealer_cash"])
        + float(row["loyalty_cash"])
        + float(row["conquest_cash"])
    )


def _strategy_matrix_metrics(cm: float) -> tuple[tuple[str, Callable[[pd.Series], str]], ...]:
    """Rows for the strategy comparison table (dealer & OEM): cost roll-up uses same desk multiplier as optimization."""

    def rate_support_est(row: pd.Series) -> str:
        la = float(row["scenario_loan_amount"])
        sup = float(row["dealer_rate_support_level"])
        return _money(la * (sup / 10000.0) * cm)

    return (
        ("APR", lambda r: f"{float(r['scenario_dealer_apr']):.2f}%"),
        ("Payment / mo", lambda r: _money(float(r["scenario_dealer_monthly_payment"]))),
        ("Term", lambda r: f"{int(r['loan_term'])} mo"),
        ("Rate support (est.)", rate_support_est),
        ("Cash incentives (total)", _oem_cash_stack),
        ("Total support cost", lambda r: _money(float(r["estimated_support_cost"]))),
        ("Close rate", lambda r: _pct(float(r["conversion_probability"]))),
        ("Lift vs baseline", lambda r: _pct(float(r["conversion_lift_vs_baseline"]))),
        ("Margin after support", lambda r: _money(float(r["remaining_margin_estimate"]))),
    )


def _render_strategy_comparison_matrix(
    *,
    cur_row: pd.Series | None,
    pack: StrategySpectrumPack,
    rec: pd.Series,
    cm: float,
) -> None:
    """Single comparison table: metric column + one column per strategy (dealer & OEM)."""
    strategies: list[tuple[str, pd.Series, str]] = []
    if cur_row is not None:
        strategies.append(("Current", cur_row, "current"))
    strategies.extend(
        [
            ("Conservative", pack.conservative, "conservative"),
            ("Recommended", rec, "recommended"),
            ("Balanced", pack.balanced, "balanced"),
            ("Aggressive", pack.aggressive, "aggressive"),
        ]
    )
    if pack.optional is not None:
        spec_title = pack.optional_label or "Loyalty / specialty"
        strategies.append((spec_title, pack.optional, "specialty"))

    with ui.element("div").classes("exec-section-tight exec-oem-matrix-section w-full"):
        ui.label("All strategies — side by side").classes("exec-section-h2")
        lede = (
            "One table: each row is a metric; each column is a strategy. "
            "Total support cost is modeled rate support (using your desk multiplier) plus stackable cash. "
            "Scroll horizontally on narrow screens — the metric column stays pinned."
            if cur_row is not None
            else "One table: each row is a metric; each column is a strategy. "
            "Total support cost is modeled rate support plus stackable cash. "
            "No separate “current” column for this run."
        )
        ui.label(lede).classes("exec-oem-matrix-lede")
        with ui.element("div").classes("exec-oem-table-scroll"):
            with ui.element("table").classes("exec-oem-compare-table"):
                with ui.element("thead"):
                    with ui.element("tr"):
                        with ui.element("th").classes(
                            "exec-oem-th exec-oem-th--metric exec-oem-sticky-col"
                        ):
                            ui.label("Metric").classes("exec-oem-th-text")
                        for title, _, role in strategies:
                            th_cls = f"exec-oem-th exec-oem-th--{role}"
                            with ui.element("th").classes(th_cls):
                                ui.label(title).classes("exec-oem-th-text exec-oem-th-strategy")
                with ui.element("tbody"):
                    for m_label, fmt_fn in _strategy_matrix_metrics(cm):
                        with ui.element("tr").classes("exec-oem-tr"):
                            with ui.element("td").classes(
                                "exec-oem-td exec-oem-td--metric exec-oem-sticky-col"
                            ):
                                ui.label(m_label).classes("exec-oem-td-metric-lbl")
                            for _, row, role in strategies:
                                try:
                                    cell = fmt_fn(row)
                                except (KeyError, TypeError, ValueError):
                                    cell = "—"
                                td_cls = f"exec-oem-td exec-oem-td--{role}"
                                with ui.element("td").classes(td_cls):
                                    ui.label(cell).classes("exec-oem-td-val")


def _offer_metric_line(label: str, value: str) -> None:
    with ui.row().classes("w-full items-baseline justify-between exec-offer-line"):
        ui.label(label).classes("exec-offer-lbl")
        ui.label(value).classes("exec-offer-val")


def render_executive_results_body(
    *,
    state: dict[str, Any],
    result_df: pd.DataFrame,
    rec: pd.Series,
    aggressive: pd.Series,
    baseline_p: float,
    cur_row: pd.Series | None,
    business: dict[str, Any],
    cm: float,
    optimization_mode: str,
    redraw: Callable[[], None],
    advanced_content: Callable[[], None],
) -> None:
    pack = build_strategy_spectrum_pack(result_df, rec, aggressive)
    oem = optimization_mode == "oem"
    bullets = build_reasoning_bullets(
        state=state,
        rec=rec,
        aggressive=aggressive,
        baseline_p=baseline_p,
        optimization_mode=optimization_mode,
    )
    labs, vals = _breakdown_lists(rec, cm)
    ref_sup = float(rec["estimated_support_cost"])

    lift = float(rec["conversion_lift_vs_baseline"])
    eff = float(rec["estimated_support_cost"]) / max(lift * 100.0, 0.02)
    inv_press = int(state.get("sb_inventory_pressure_ui") or 5)
    inv_lbl = "High" if inv_press >= 7 else ("Medium" if inv_press >= 4 else "Low")
    comp_apr = float(state.get("sb_competitor_apr") or 0)
    rec_apr = float(rec["scenario_dealer_apr"])
    if comp_apr > 0 and rec_apr + 0.02 < comp_apr:
        comp_lbl = "Above market"
    elif comp_apr > 0 and rec_apr <= comp_apr + 0.05:
        comp_lbl = "Competitive"
    else:
        comp_lbl = "Monitor"

    # --- 2. Decision layer: hero — offer structure + rationale (primary story) ---
    with ui.element("div").classes("exec-decision-hero w-full"):
        with ui.element("div").classes("exec-decision-hero-band"):
            ui.label("Recommendation").classes("exec-decision-hero-eyebrow")
            ui.label(
                "What we recommend for regional planning" if oem else "What we recommend for this deal"
            ).classes("exec-decision-hero-title")
            ui.label(
                "The package to execute—terms on the left, decision logic on the right. "
                "Everything below compares paths against this baseline."
            ).classes("exec-decision-hero-sub")
        with ui.element("div").classes("exec-decision-panel exec-decision-panel--hero w-full"):
            with ui.row().classes("w-full exec-decision-split"):
                with ui.column().classes("exec-decision-col exec-decision-col--offer"):
                    ui.label("Offer structure").classes("exec-decision-col-h exec-decision-col-h--hero")
                    _offer_metric_line("APR", f"{float(rec['scenario_dealer_apr']):.2f}%")
                    _offer_metric_line("Monthly payment", _money(float(rec["scenario_dealer_monthly_payment"])))
                    _offer_metric_line("Term", f"{int(rec['loan_term'])} months")
                    cash = (
                        float(rec["customer_cash"])
                        + float(rec["dealer_cash"])
                        + float(rec["loyalty_cash"])
                        + float(rec["conquest_cash"])
                    )
                    _offer_metric_line("Cash & stackable rebates", _money(cash))
                    ui.element("div").classes("exec-decision-divider")
                    _render_exec_support_breakdown(labs, vals, ref_sup)
                with ui.column().classes("exec-decision-col exec-decision-col--why"):
                    ui.label("Rationale").classes("exec-decision-col-h exec-decision-col-h--hero")
                    with ui.column().classes("exec-bullets-tight"):
                        for b in bullets[:5]:
                            with ui.row().classes("items-start gap-2 exec-bullet-row"):
                                ui.icon("check_circle").classes("exec-bullet-icon")
                                ui.label(b).classes("exec-bullet-text")
                    ui.element("div").classes("exec-decision-divider")
                    ui.label("Strategic read").classes("exec-decision-micro")
                    with ui.row().classes("w-full exec-outcome-chips"):
                        with ui.element("div").classes("exec-outcome-chip"):
                            ui.label("Support efficiency").classes("exec-outcome-chip-k")
                            ui.label(_money(eff)).classes("exec-outcome-chip-v")
                            ui.label("Per lift point").classes("exec-outcome-chip-h")
                        with ui.element("div").classes("exec-outcome-chip"):
                            ui.label("Inventory read").classes("exec-outcome-chip-k")
                            ui.label(inv_lbl).classes("exec-outcome-chip-v")
                            ui.label("Pressure signal").classes("exec-outcome-chip-h")
                        with ui.element("div").classes("exec-outcome-chip"):
                            ui.label("Competitive stance").classes("exec-outcome-chip-k")
                            ui.label(comp_lbl).classes("exec-outcome-chip-v")
                            ui.label("Vs benchmark APR").classes("exec-outcome-chip-h")

    _render_strategy_comparison_matrix(cur_row=cur_row, pack=pack, rec=rec, cm=cm)
    fig_spec = mk_offer_spectrum_tradeoff_fig(pack)
    _plotly_card(
        "Offer spectrum — conversion vs support",
        "Named strategies; recommended highlighted.",
        fig_spec,
    )

    # --- Advanced analysis ---
    with ui.expansion("Advanced analysis", value=False).classes("w-full exec-advanced-exp").props(
        "dense"
    ):
        ui.label("Charts, scenario grids, and diagnostics for analysts.").classes("text-xs").style(
            f"color:{TEXT_SECONDARY};margin-bottom:8px;"
        )
        with ui.column().classes("w-full gap-4"):
            advanced_content()


_DEALER_EDIT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("customer", "person", "Customer"),
    ("vehicle", "directions_car", "Vehicle"),
    ("dealer_inv", "warehouse", "Dealer & inventory"),
    ("financing", "account_balance", "Constraints"),
    ("market", "show_chart", "Market"),
)

_OEM_EDIT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("oem_buyer", "groups", "Target buyer"),
    ("oem_vehicle", "directions_car", "Vehicle strategy"),
    ("oem_dealer_inv", "warehouse", "Dealer & inventory"),
    ("oem_market", "public", "Market conditions"),
    ("oem_competitor", "compare_arrows", "Competitor"),
    ("oem_financing", "account_balance", "Constraints"),
)


def render_executive_sidebar_dealer(
    state: dict[str, Any],
    meta: dict[str, Any],
    *,
    open_edit: Callable[[str], None],
    run_analysis: Callable[[], Any],
    go_wizard: Callable[[], None],
    optimization_running: bool,
) -> None:
    """Dense snapshot + icon edit row."""
    fico = int(state.get("sb_fico_score") or 0)
    dti = business_dti_ratio(state) * 100.0
    urg = int(state.get("sb_purchase_urgency_ui") or 0)
    make = str(state.get("sb_make") or "")
    model = str(state.get("sb_model_name") or "")
    loan = float(state.get("sb_loan_amount") or 0)
    term = int(state.get("sb_primary_loan_term") or 0)
    capr = float(state.get("sb_competitor_apr") or 0)
    cb = float(state.get("sb_competitor_cashback") or 0)
    bud = float(state.get("sb_max_total_support_budget") or 0)
    mx = int(state.get("sb_max_apr_rate_support") or 0)
    search_txt = str(meta.get("search_mode") or "—")

    with ui.element("div").classes("snapshot-pane-heading snapshot-pane-heading--tight"):
        ui.label("Snapshot").classes("snapshot-pane-title")
        ui.label("Read-only context").classes("snapshot-pane-sub")

    with ui.element("div").classes("rail-section rail-section--dense"):
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Customer").classes("snapshot-label-compact")
            ui.label(f"{fico} FICO · {dti:.0f}% DTI · urgency {urg}/10").classes("snapshot-dense-primary")
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Vehicle").classes("snapshot-label-compact")
            vline = f"{(make + ' ' + model).strip() or '—'} · {_money(loan)} financed"
            if term:
                vline += f" · {term} mo"
            ui.label(vline).classes("snapshot-dense-primary")
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Market").classes("snapshot-label-compact")
            ui.label(f"Competitor {capr:.2f}% APR · cashback {_money(cb)}").classes("snapshot-dense-primary")
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Constraints").classes("snapshot-label-compact")
            ui.label(f"Budget {_money(bud)} · APR cap {mx} pts · {search_txt}").classes("snapshot-dense-primary")

    with ui.element("div").classes("rail-section rail-section--dense"):
        ui.label("Inputs").classes("rail-section-label rail-section-label--tight")
        render_compact_edit_launchers(open_edit, _DEALER_EDIT_SPECS)

    with ui.element("div").classes("rail-section rail-section--dense"):
        with ui.element("div").classes("rail-run-stack"):
            rb = ui.button("Re-run", on_click=run_analysis).props("unelevated dense no-caps").classes(
                "btn-dash btn-dash-primary"
            )
            rb.set_enabled(not optimization_running)
            ui.button("Home", on_click=go_wizard).props("outline dense no-caps").classes(
                "btn-dash rail-run-outline"
            )


def render_executive_sidebar_oem(
    state: dict[str, Any],
    meta: dict[str, Any],
    *,
    open_edit: Callable[[str], None],
    run_analysis: Callable[[], Any],
    go_wizard: Callable[[], None],
    optimization_running: bool,
) -> None:
    arch = str(state.get("oem_archetype") or "—")
    mix = str(state.get("oem_use_mix") or "No") == "Yes"
    region = str(state.get("sb_region") or "—")
    inv_p = int(state.get("sb_inventory_pressure_ui") or 0)
    aging = float(state.get("sb_aging_inventory_pct_display") or 0)
    fed = float(state.get("sb_fed_rate") or 0)
    mkt = float(state.get("sb_market_rate_index") or 0)
    demand = int(state.get("oem_regional_demand_ui") or 5)
    budget = float(state.get("sb_max_total_support_budget") or 0)
    max_sup = int(state.get("sb_max_apr_rate_support") or 0)
    search_txt = str(meta.get("search_mode") or "—")

    with ui.element("div").classes("snapshot-pane-heading snapshot-pane-heading--tight"):
        ui.label("Planning snapshot").classes("snapshot-pane-title")
        ui.label("OEM context").classes("snapshot-pane-sub")

    with ui.element("div").classes("rail-section rail-section--dense"):
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Buyer & blend").classes("snapshot-label-compact")
            ui.label(f"{arch} · {'mix' if mix else 'single'}").classes("snapshot-dense-primary")
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Region").classes("snapshot-label-compact")
            ui.label(f"{region} · demand {demand}/10 · mkt index {mkt:.2f}%").classes("snapshot-dense-primary")
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Inventory & macro").classes("snapshot-label-compact")
            ui.label(f"Pressure {inv_p}/10 · aging >90d {aging:.0f}% · Fed {fed:.2f}%").classes(
                "snapshot-dense-primary"
            )
        with ui.element("div").classes("snapshot-card snapshot-card--dense"):
            ui.label("Constraints").classes("snapshot-label-compact")
            ui.label(f"Budget {_money(budget)} · max APR {max_sup} pts · {search_txt}").classes(
                "snapshot-dense-primary"
            )

    with ui.element("div").classes("rail-section rail-section--dense"):
        ui.label("Inputs").classes("rail-section-label rail-section-label--tight")
        render_compact_edit_launchers(open_edit, _OEM_EDIT_SPECS)

    with ui.element("div").classes("rail-section rail-section--dense"):
        with ui.element("div").classes("rail-run-stack"):
            rerun = ui.button("Re-run planning", on_click=run_analysis).props(
                "unelevated dense no-caps"
            ).classes("btn-dash btn-dash-primary")
            rerun.set_enabled(not optimization_running)
            ui.button("Home", on_click=go_wizard).props("outline dense no-caps").classes(
                "btn-dash rail-run-outline"
            )
