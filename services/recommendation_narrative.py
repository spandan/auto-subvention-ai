"""Executive-facing recommendation bullets — heuristics only, no model internals."""

from __future__ import annotations

from typing import Any


def build_reasoning_bullets(
    *,
    state: dict[str, Any],
    rec: Any,
    aggressive: Any,
    baseline_p: float,
    optimization_mode: str,
) -> list[str]:
    bullets: list[str] = []
    lift = float(rec["conversion_lift_vs_baseline"])
    sup = float(rec["estimated_support_cost"])
    apr = float(rec["scenario_dealer_apr"])
    comp_apr = float(state.get("sb_competitor_apr") or 0)
    margin = float(rec["remaining_margin_estimate"])
    inv = int(state.get("sb_inventory_pressure_ui") or 5)
    loy = float(rec["loyalty_cash"])
    cq = float(rec["conquest_cash"])
    agg_sup = float(aggressive["estimated_support_cost"])
    agg_p = float(aggressive["conversion_probability"])
    rec_p = float(rec["conversion_probability"])

    if lift >= 0.12:
        bullets.append("Strong conversion lift with disciplined support spend.")
    elif lift >= 0.05:
        bullets.append("Solid conversion lift relative to baseline with moderate spend.")
    else:
        bullets.append("Meaningful lift while keeping support tightly controlled.")

    if comp_apr > 0 and apr + 0.05 < comp_apr:
        bullets.append("Beats competitor APR while protecting margin economics.")
    elif comp_apr > 0 and apr <= comp_apr:
        bullets.append("Aligns dealer APR competitively versus the benchmark offer.")

    if inv >= 7:
        bullets.append("High inventory pressure supports a sharper APR-led package.")
    elif inv <= 3:
        bullets.append("Lower inventory urgency allows a more margin-preserving structure.")

    if loy < 250 and float(state.get("sb_max_loyalty_incentive") or 0) >= 500:
        bullets.append("Loyalty spend is unnecessary under current conditions.")
    if cq < 250 and float(state.get("sb_max_conquest_incentive") or 0) >= 500:
        bullets.append("Conquest support is not cost-efficient for this scenario set.")

    if agg_sup > sup * 1.35 and agg_p - rec_p < 0.03:
        bullets.append("Additional support spend showed diminishing returns beyond this package.")

    if margin < float(state.get("sb_expected_unit_margin") or 0) * 0.25:
        bullets.append("Recommendation stays close to minimum margin guardrails you set.")

    if optimization_mode == "oem":
        bullets.append("Structured for regional planning using standardized buyer assumptions.")

    # Cap length
    out: list[str] = []
    for b in bullets:
        if b not in out:
            out.append(b)
        if len(out) >= 6:
            break
    return out if out else ["Best tradeoff between predicted close rate and loaded incentive cost."]


def dealer_context_lines(state: dict[str, Any], business: dict[str, Any]) -> list[str]:
    dti = float(business.get("dti") or 0) * 100.0
    pay = float(state.get("sb_baseline_dealer_monthly_payment") or 0)
    comp_pay = float(state.get("sb_competitor_monthly_payment") or 0)
    lines = [
        f"Buyer DTI near {dti:.0f}% — payment comfort is a primary decision driver.",
    ]
    if pay > 0 and comp_pay > 0:
        if pay <= comp_pay:
            lines.append("Recommended structure improves payment posture vs the benchmark alternative.")
        else:
            lines.append("Benchmark alternative still shows a stronger payment — lean on APR and cash levers.")
    lines.append("Likelihood-to-close reflects modeled shopper response to this incentive stack.")
    return lines


def oem_context_lines(state: dict[str, Any]) -> list[str]:
    return [
        f"Regional read: {state.get('sb_region', '—')} with demand intensity {int(state.get('oem_regional_demand_ui') or 5)}/10.",
        f"Inventory aging pressure {float(state.get('sb_aging_inventory_pct_display') or 0):.0f}% over aged threshold.",
        "Support allocation favors the most efficient levers for the evaluated campaign envelope.",
    ]
