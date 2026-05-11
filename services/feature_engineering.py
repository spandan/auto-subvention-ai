"""Business inputs → engineered model features (preserves legacy logic)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from services.constants import LOAN_TERMS


def get_demo_defaults(now: datetime | None = None) -> dict[str, Any]:
    """
    Canonical demo scenario (logical / business names).
    Engineered model fields are derived in calculate_model_features — not entered here.
    """
    ref = now or datetime.now()
    return {
        "credit_score": 715,
        "monthly_gross_income": 8500,
        "monthly_debt_payments": 2400,
        "price_sensitivity_ui": 6,
        "purchase_urgency_ui": 7,
        "brand_preference_ui": 5,
        "purchase_intent_ui": 7,
        "customer_sentiment_ui": 6,
        "customer_segment": "Payment Sensitive",
        "ev_interest_ui": 3,
        "family_utility_need_ui": 7,
        "truck_interest_ui": 4,
        "conquest_likelihood_ui": 5,
        "make": "Toyota",
        "model_name": "RAV4",
        "model_year": 2025,
        "trim": "Limited",
        "body_style": "SUV",
        "fuel_type": "Hybrid",
        "vehicle_segment": "Compact SUV",
        "vehicle_price": 42000,
        "vehicle_age": 1,
        "residual_value_strength_ui": 7,
        "residual_support_pct": 4.5,
        "rv_push_brand_flag": True,
        "dealer_size_tier": "Large",
        "metro_flag": True,
        "avg_monthly_retail_units": 145,
        "dealer_margin_pct": 7.5,
        "expected_unit_margin": 4200,
        "days_in_inventory": 68,
        "on_hand_units": 42,
        "in_transit_units": 18,
        "aging_over_90_days_pct": 24,
        "stockout_risk_flag": False,
        "overstock_flag": True,
        "inventory_pressure_ui": 7,
        "loan_amount": 36000,
        "down_payment": 6000,
        "loan_term": 60,
        "standard_apr": 7.49,
        "baseline_dealer_apr": 6.99,
        "baseline_dealer_monthly_payment": 710,
        "primary_competitor": "Honda",
        "competitor_apr": 6.49,
        "competitor_monthly_payment": 685,
        "competitor_cashback": 1000,
        "competitor_offer_aggressiveness_ui": 7,
        "competitor_sales_momentum_ui": 6,
        "fed_rate": 5.25,
        "ten_year_treasury_yield": 4.30,
        "inflation_rate_cpi": 3.20,
        "base_auto_rate_index": 7.10,
        "market_rate_index": 7.25,
        "month_of_quote": ref.month,
        "day_of_week_quote": ref.weekday(),
        "quarter_end_flag": False,
        "sales_type": "Finance",
        "region": "Southwest",
        "state": "TX",
        "max_oem_customer_cash_support": 3000,
        "max_dealer_cash_support": 1500,
        "max_rate_support_level": 200,
        "allow_loyalty_incentive": True,
        "max_loyalty_incentive": 1000,
        "allow_conquest_incentive": True,
        "max_conquest_incentive": 1000,
        "max_total_support_budget": 4500,
        "minimum_acceptable_remaining_margin": 1200,
        "support_cost_multiplier": 0.65,
        "minimum_meaningful_conversion_lift": 0.02,
        "allowed_loan_terms": [48, 60, 72],
        "rate_support_step": 25,
        "cash_support_step": 500,
    }


def session_defaults_from_demo(now: datetime | None = None) -> dict[str, Any]:
    """Maps get_demo_defaults() → UI state keys used by widgets."""
    d = get_demo_defaults(now)

    def yn(b: bool) -> str:
        return "Yes" if b else "No"

    lift_pp = float(d["minimum_meaningful_conversion_lift"]) * 100.0

    return {
        "sidebar_wizard_step": 0,
        "wizard_step": 0,
        "sb_fico_score": d["credit_score"],
        "sb_monthly_income": d["monthly_gross_income"],
        "sb_monthly_debt_payments": float(d["monthly_debt_payments"]),
        "sb_price_sensitivity_ui": d["price_sensitivity_ui"],
        "sb_purchase_urgency_ui": d["purchase_urgency_ui"],
        "sb_brand_preference_ui": d["brand_preference_ui"],
        "sb_purchase_intent_ui": d["purchase_intent_ui"],
        "sb_sentiment_ui": d["customer_sentiment_ui"],
        "sb_customer_segment": d["customer_segment"],
        "sb_ev_affinity_ui": d["ev_interest_ui"],
        "sb_family_utility_ui": d["family_utility_need_ui"],
        "sb_truck_affinity_ui": d["truck_interest_ui"],
        "sb_conquest_likelihood_ui": d["conquest_likelihood_ui"],
        "sb_make": d["make"],
        "sb_model_name": d["model_name"],
        "sb_model_year": d["model_year"],
        "sb_trim": d["trim"],
        "sb_body_style": d["body_style"],
        "sb_fuel_type": d["fuel_type"],
        "sb_vehicle_segment": d["vehicle_segment"],
        "sb_vehicle_price": d["vehicle_price"],
        "sb_vehicle_age": d["vehicle_age"],
        "sb_rv_strength_ui": d["residual_value_strength_ui"],
        "sb_residual_support_pct_display": float(d["residual_support_pct"]),
        "sb_rv_push_yn": yn(d["rv_push_brand_flag"]),
        "sb_dealer_size_tier": d["dealer_size_tier"],
        "sb_metro_yn": yn(d["metro_flag"]),
        "sb_avg_monthly_retail_units": d["avg_monthly_retail_units"],
        "sb_dealer_margin_pct_display": float(d["dealer_margin_pct"]),
        "sb_expected_unit_margin": float(d["expected_unit_margin"]),
        "sb_days_in_inventory": d["days_in_inventory"],
        "sb_on_hand_units": d["on_hand_units"],
        "sb_in_transit_units": d["in_transit_units"],
        "sb_aging_inventory_pct_display": float(d["aging_over_90_days_pct"]),
        "sb_stockout_yn": yn(d["stockout_risk_flag"]),
        "sb_overstock_yn": yn(d["overstock_flag"]),
        "sb_inventory_pressure_ui": d["inventory_pressure_ui"],
        "sb_loan_amount": d["loan_amount"],
        "sb_down_payment": d["down_payment"],
        "sb_primary_loan_term": int(d["loan_term"]),
        "sb_standard_apr": float(d["standard_apr"]),
        "sb_baseline_dealer_apr": float(d["baseline_dealer_apr"]),
        "sb_baseline_dealer_monthly_payment": float(d["baseline_dealer_monthly_payment"]),
        "sb_primary_competitor": d["primary_competitor"],
        "sb_competitor_apr": float(d["competitor_apr"]),
        "sb_competitor_monthly_payment": float(d["competitor_monthly_payment"]),
        "sb_competitor_cashback": d["competitor_cashback"],
        "sb_competitor_aggr_ui": d["competitor_offer_aggressiveness_ui"],
        "sb_competitor_sales_ui": d["competitor_sales_momentum_ui"],
        "sb_fed_rate": float(d["fed_rate"]),
        "sb_ten_year": float(d["ten_year_treasury_yield"]),
        "sb_inflation_cpi": float(d["inflation_rate_cpi"]),
        "sb_base_auto_rate_index": float(d["base_auto_rate_index"]),
        "sb_market_rate_index": float(d["market_rate_index"]),
        "sb_month_of_quote": int(d["month_of_quote"]),
        "sb_day_of_week_quote": int(d["day_of_week_quote"]),
        "sb_quarter_end_yn": yn(d["quarter_end_flag"]),
        "sb_sales_type": d["sales_type"],
        "sb_region": d["region"],
        "sb_state": d["state"],
        "sb_max_oem_customer_cash": d["max_oem_customer_cash_support"],
        "sb_max_dealer_cash_support": d["max_dealer_cash_support"],
        "sb_max_apr_rate_support": int(d["max_rate_support_level"]),
        "sb_allow_loyalty_incentive": yn(d["allow_loyalty_incentive"]),
        "sb_max_loyalty_incentive": d["max_loyalty_incentive"],
        "sb_allow_conquest_incentive": yn(d["allow_conquest_incentive"]),
        "sb_max_conquest_incentive": d["max_conquest_incentive"],
        "sb_max_total_support_budget": d["max_total_support_budget"],
        "sb_min_acceptable_remaining_margin": d["minimum_acceptable_remaining_margin"],
        "sb_cost_multiplier": float(d["support_cost_multiplier"]),
        "sb_min_meaningful_lift_pp": lift_pp,
        "sb_allowed_loan_terms": list(d["allowed_loan_terms"]),
        "sb_rate_support_step": int(d["rate_support_step"]),
        "sb_cash_support_step": int(d["cash_support_step"]),
        # Dashboard: full scenario grid table is heavy; default shows top curated rows only.
        "dashboard_show_all_scenarios": False,
    }


def income_to_band(monthly_income: float) -> str:
    if monthly_income < 4000:
        return "<4K"
    if monthly_income < 7000:
        return "4K-7K"
    if monthly_income < 11000:
        return "7K-11K"
    if monthly_income < 16000:
        return "11K-16K"
    return "16K+"


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def score_1_10_to_model(score: int) -> float:
    return int(score) / 10.0


def sentiment_ui_to_model(slider: int) -> float:
    return (int(slider) - 5) / 5.0


def map_fuel_ui_to_model(ui: str) -> str:
    return {
        "Gasoline": "Gas",
        "Hybrid": "Hybrid",
        "Plug-in Hybrid": "PHEV",
        "Diesel": "Diesel",
        "EV": "EV",
    }.get(str(ui), "Gas")


def map_sales_ui_to_model(ui: str) -> str:
    return {
        "Retail": "APR",
        "Lease": "Lease",
        "Finance": "Mixed",
        "Cash": "Cash",
    }.get(str(ui), "APR")


def map_body_ui_to_model(ui: str) -> str:
    return {
        "Sedan": "Sedan",
        "SUV": "SUV",
        "Truck": "Truck",
        "Coupe": "Coupe",
        "Hatchback": "Other",
        "Crossover": "SUV",
    }.get(str(ui), "Sedan")


def yes_no_to_bool(selection: object) -> bool:
    return str(selection) == "Yes"


def fico_to_band(score: float) -> str:
    s = float(score)
    if s < 580:
        return "Deep Subprime"
    if s < 620:
        return "Subprime"
    if s < 680:
        return "Near Prime"
    if s < 740:
        return "Prime"
    return "Super Prime"


def fico_to_credit_tier(score: float) -> str:
    s = float(score)
    if s < 620:
        return "Weak"
    if s < 680:
        return "Fair"
    if s < 740:
        return "Good"
    return "Excellent"


def calculate_monthly_payment_if_needed(
    principal: float, annual_rate_pct: float, term_months: int
) -> float:
    if principal <= 0 or term_months <= 0:
        return 0.0
    r = (float(annual_rate_pct) / 100.0) / 12.0
    if r < 1e-12:
        return float(principal) / term_months
    return float(principal * r / (1.0 - (1.0 + r) ** (-term_months)))


def calculate_model_features(inp: dict[str, Any]) -> dict[str, Any]:
    """Build all schema-aligned model features from unified business input dict."""
    mi = float(inp["monthly_income"])
    vp = float(inp["vehicle_price"])
    la = float(inp["loan_amount"])
    dp = float(inp["down_payment"])
    dealer_apr = float(inp["dealer_apr"])
    dealer_payment = float(inp["dealer_monthly_payment"])
    competitor_apr = float(inp["competitor_apr"])
    cmp_pay = float(inp["competitor_monthly_payment"])
    competitor_cashback = float(inp["competitor_cashback"])

    customer_cash = float(inp["customer_cash"])
    loyalty_cash = float(inp["loyalty_cash"])
    conquest_cash = float(inp["conquest_cash"])
    total_cash_rebate = customer_cash + loyalty_cash + conquest_cash

    ps = float(inp["price_sensitivity_score"])
    urg = float(inp["customer_urgency_score"])
    brand = float(inp["brand_loyalty_score"])

    payment_to_income = clip(dealer_payment / mi, 0.001, 1.0) if mi > 0 else 0.5
    ltv = clip(la / vp, 0.01, 2.0) if vp > 0 else 0.8
    down_payment_pct = (dp / vp) if vp > 0 else 0.0

    apr_gap_bps = (dealer_apr - competitor_apr) * 100.0
    payment_gap = dealer_payment - cmp_pay
    cashback_gap = total_cash_rebate - competitor_cashback

    ca_idx = float(inp["competitor_offer_aggressiveness_index"])
    cs_idx = float(inp["competitor_sales_volume_index"])
    competitor_pressure_score = (
        0.5 * ca_idx + 0.3 * cs_idx + 0.2 * max(apr_gap_bps, 0.0) / 300.0
    )

    napr = clip(apr_gap_bps / 300.0, -1.0, 1.0)
    npay = clip(payment_gap / 500.0, -1.0, 1.0)
    ncash = clip(cashback_gap / 5000.0, -1.0, 1.0)
    nloy = clip(loyalty_cash / 3000.0, 0.0, 1.0)
    offer_advantage_score = -0.4 * napr - 0.3 * npay + 0.2 * ncash + 0.1 * nloy

    sensitivity_x_apr_gap = ps * apr_gap_bps
    loyalty_x_payment_gap = brand * payment_gap
    urgency_x_pricing_disadvantage = urg * max(apr_gap_bps, 0.0)

    fico = float(inp["fico_score"])

    standard_apr = float(inp["standard_apr"])
    support_level = float(inp["dealer_rate_support_level"])
    subvented_apr = max(0.5, standard_apr - support_level / 100.0)

    return {
        "fico_score": fico,
        "fico_band": fico_to_band(fico),
        "credit_tier": fico_to_credit_tier(fico),
        "monthly_income": mi,
        "income_band": income_to_band(mi),
        "dti": float(inp["dti"]),
        "payment_to_income": payment_to_income,
        "price_sensitivity_score": ps,
        "customer_urgency_score": urg,
        "brand_loyalty_score": brand,
        "purchase_intent_index": float(inp["purchase_intent_index"]),
        "sentiment_score": float(inp["sentiment_score"]),
        "customer_segment": str(inp["customer_segment"]),
        "loyalty_score": float(inp["loyalty_score"]),
        "conquest_score": float(inp["conquest_score"]),
        "ev_affinity_score": float(inp["ev_affinity_score"]),
        "family_utility_score": float(inp["family_utility_score"]),
        "truck_affinity_score": float(inp["truck_affinity_score"]),
        "make": str(inp["make"]),
        "model_name": str(inp["model_name"]),
        "model_year": int(inp["model_year"]),
        "trim": str(inp["trim"]),
        "body_style": str(inp["body_style"]),
        "fuel_type": str(inp["fuel_type"]),
        "vehicle_segment": str(inp["vehicle_segment"]),
        "vehicle_price": vp,
        "vehicle_age": float(inp["vehicle_age"]),
        "rv_strength_index": float(inp["rv_strength_index"]),
        "rv_push_brand_flag": int(inp["rv_push_brand_flag"]),
        "residual_support_pct": float(inp["residual_support_pct"]),
        "dealer_size_tier": str(inp["dealer_size_tier"]),
        "metro_flag": int(inp["metro_flag"]),
        "avg_monthly_retail_units": float(inp["avg_monthly_retail_units"]),
        "dealer_margin_pct": float(inp["dealer_margin_pct"]),
        "expected_unit_margin": float(inp["expected_unit_margin"]),
        "days_in_inventory": float(inp["days_in_inventory"]),
        "on_hand_units": float(inp["on_hand_units"]),
        "in_transit_units": float(inp["in_transit_units"]),
        "aging_over_90_days_pct": float(inp["aging_over_90_days_pct"]),
        "stockout_risk_flag": int(inp["stockout_risk_flag"]),
        "overstock_flag": int(inp["overstock_flag"]),
        "inventory_pressure_score": float(inp["inventory_pressure_score"]),
        "loan_amount": la,
        "down_payment": dp,
        "ltv": ltv,
        "down_payment_pct": down_payment_pct,
        "loan_term": int(inp["loan_term"]),
        "standard_apr": standard_apr,
        "dealer_apr": dealer_apr,
        "subvented_apr": subvented_apr,
        "dealer_rate_support_level": support_level,
        "dealer_monthly_payment": dealer_payment,
        "customer_cash": customer_cash,
        "dealer_cash": float(inp["dealer_cash"]),
        "loyalty_cash": loyalty_cash,
        "conquest_cash": conquest_cash,
        "total_cash_rebate": total_cash_rebate,
        "promotion_flag": int(inp["promotion_flag"]),
        "primary_competitor": str(inp["primary_competitor"]),
        "competitor_apr": competitor_apr,
        "competitor_monthly_payment": cmp_pay,
        "competitor_cashback": competitor_cashback,
        "competitor_offer_aggressiveness_index": ca_idx,
        "competitor_sales_volume_index": cs_idx,
        "competitor_pressure_score": competitor_pressure_score,
        "apr_gap_bps": apr_gap_bps,
        "payment_gap": payment_gap,
        "cashback_gap": cashback_gap,
        "offer_advantage_score": offer_advantage_score,
        "sensitivity_x_apr_gap": sensitivity_x_apr_gap,
        "loyalty_x_payment_gap": loyalty_x_payment_gap,
        "urgency_x_pricing_disadvantage": urgency_x_pricing_disadvantage,
        "fed_rate": float(inp["fed_rate"]),
        "ten_year_treasury_yield": float(inp["ten_year_treasury_yield"]),
        "inflation_rate_cpi": float(inp["inflation_rate_cpi"]),
        "base_auto_rate_index": float(inp["base_auto_rate_index"]),
        "market_rate_index": float(inp["market_rate_index"]),
        "month_of_quote": int(inp["month_of_quote"]),
        "day_of_week_quote": int(inp["day_of_week_quote"]),
        "quarter_end_flag": int(inp["quarter_end_flag"]),
        "sales_type": str(inp["sales_type"]),
        "region": str(inp["region"]),
        "state": str(inp["state"]),
    }


def build_model_features(business: dict[str, Any]) -> dict[str, Any]:
    return calculate_model_features(business)


def align_to_schema(
    row_dict: dict[str, Any],
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
) -> tuple[pd.DataFrame | None, str | None, list[str], list[str]]:
    required_columns = list(schema["required_columns"])
    extra_keys = sorted(set(row_dict.keys()) - set(required_columns))

    out: dict[str, Any] = {}
    still_missing: list[str] = []

    for col in required_columns:
        if col in row_dict and row_dict[col] is not None:
            out[col] = row_dict[col]
        elif col in sample_defaults and sample_defaults[col] is not None:
            out[col] = sample_defaults[col]
        else:
            still_missing.append(col)

    if still_missing:
        return (
            None,
            "Cannot build model input: missing required columns after merging "
            f"computed features and sample_input.json: {', '.join(still_missing)}",
            still_missing,
            extra_keys,
        )

    df = pd.DataFrame([out])
    df = df[required_columns]
    return df, None, [], extra_keys


def align_rows_for_batch_predict(
    row_dicts: list[dict[str, Any]],
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
) -> tuple[pd.DataFrame | None, str | None]:
    """
    Stack per-row feature dicts (same keys as ``calculate_model_features``) into one
    ``DataFrame`` for a single ``predict_proba`` call. Uses the same column rules as
    ``align_to_schema`` for each row.
    """
    if not row_dicts:
        return pd.DataFrame(), None
    required_columns = list(schema["required_columns"])
    records: list[dict[str, Any]] = []
    for i, row_dict in enumerate(row_dicts):
        out: dict[str, Any] = {}
        still_missing: list[str] = []
        for col in required_columns:
            if col in row_dict and row_dict[col] is not None:
                v = row_dict[col]
                if isinstance(v, float) and (v != v or pd.isna(v)):  # NaN
                    v = None
                if v is not None:
                    out[col] = v
                    continue
            if col in sample_defaults and sample_defaults[col] is not None:
                out[col] = sample_defaults[col]
            else:
                still_missing.append(col)
        if still_missing:
            return (
                None,
                "Cannot build model input: missing required columns after merging "
                f"computed features and sample_input.json (row {i}): {', '.join(still_missing)}",
            )
        records.append(out)
    df = pd.DataFrame(records)[required_columns]
    return df, None


def loan_terms_sorted(raw: Any) -> list[int]:
    if raw is None:
        return [48, 60, 72]
    if isinstance(raw, (int, float)):
        t = int(raw)
        return [t] if t in LOAN_TERMS else [60]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                ts = sorted({int(x) for x in parsed if int(x) in LOAN_TERMS})
                return ts if ts else [60]
        except json.JSONDecodeError:
            pass
        return [60]
    ts = sorted({int(x) for x in raw if int(x) in LOAN_TERMS})
    return ts if ts else [60]


def business_dti_ratio(state: dict[str, Any]) -> float:
    mi = float(state.get("sb_monthly_income") or 0)
    debt = float(state.get("sb_monthly_debt_payments") or 0)
    if mi <= 0:
        return 0.0
    return float(min(max(debt / mi, 0.0), 1.5))


def build_business_inputs(state: dict[str, Any]) -> dict[str, Any]:
    """Assemble unified context dict for the model (baseline before optimization levers)."""
    ps = score_1_10_to_model(int(state["sb_price_sensitivity_ui"]))
    urg = score_1_10_to_model(int(state["sb_purchase_urgency_ui"]))
    brand = score_1_10_to_model(int(state["sb_brand_preference_ui"]))
    dm = float(state["sb_dealer_margin_pct_display"]) / 100.0
    aging = float(state["sb_aging_inventory_pct_display"]) / 100.0
    terms_sorted = loan_terms_sorted(state.get("sb_allowed_loan_terms"))
    want_term = int(state.get("sb_primary_loan_term") or terms_sorted[0])
    if want_term not in terms_sorted:
        want_term = min(terms_sorted, key=lambda t: abs(int(t) - want_term))
    ref_term = int(want_term)
    loan_amt = float(state["sb_loan_amount"])
    std_apr = float(state["sb_standard_apr"])
    baseline_support = 0.0
    dealer_apr_ctx = float(state["sb_baseline_dealer_apr"])
    baseline_payment = float(state["sb_baseline_dealer_monthly_payment"])
    if baseline_payment <= 0:
        baseline_payment = calculate_monthly_payment_if_needed(
            loan_amt, dealer_apr_ctx, ref_term
        )
    return {
        "fico_score": float(state["sb_fico_score"]),
        "monthly_income": float(state["sb_monthly_income"]),
        "dti": business_dti_ratio(state),
        "price_sensitivity_score": ps,
        "customer_urgency_score": urg,
        "brand_loyalty_score": brand,
        "purchase_intent_index": score_1_10_to_model(int(state["sb_purchase_intent_ui"])),
        "sentiment_score": sentiment_ui_to_model(int(state["sb_sentiment_ui"])),
        "customer_segment": str(state["sb_customer_segment"]),
        "loyalty_score": brand,
        "conquest_score": score_1_10_to_model(int(state["sb_conquest_likelihood_ui"])),
        "ev_affinity_score": score_1_10_to_model(int(state["sb_ev_affinity_ui"])),
        "family_utility_score": score_1_10_to_model(int(state["sb_family_utility_ui"])),
        "truck_affinity_score": score_1_10_to_model(int(state["sb_truck_affinity_ui"])),
        "make": str(state["sb_make"]),
        "model_name": str(state["sb_model_name"]),
        "model_year": int(state["sb_model_year"]),
        "trim": str(state["sb_trim"]),
        "body_style": map_body_ui_to_model(str(state["sb_body_style"])),
        "fuel_type": map_fuel_ui_to_model(str(state["sb_fuel_type"])),
        "vehicle_segment": str(state["sb_vehicle_segment"]),
        "vehicle_price": float(state["sb_vehicle_price"]),
        "vehicle_age": float(state["sb_vehicle_age"]),
        "rv_strength_index": score_1_10_to_model(int(state["sb_rv_strength_ui"])),
        "residual_support_pct": float(state["sb_residual_support_pct_display"]) / 100.0,
        "rv_push_brand_flag": yes_no_to_bool(state["sb_rv_push_yn"]),
        "dealer_size_tier": str(state["sb_dealer_size_tier"]),
        "metro_flag": yes_no_to_bool(state["sb_metro_yn"]),
        "avg_monthly_retail_units": float(state["sb_avg_monthly_retail_units"]),
        "dealer_margin_pct": dm,
        "expected_unit_margin": float(state["sb_expected_unit_margin"]),
        "days_in_inventory": float(state["sb_days_in_inventory"]),
        "on_hand_units": float(state["sb_on_hand_units"]),
        "in_transit_units": float(state["sb_in_transit_units"]),
        "aging_over_90_days_pct": aging,
        "stockout_risk_flag": yes_no_to_bool(state["sb_stockout_yn"]),
        "overstock_flag": yes_no_to_bool(state["sb_overstock_yn"]),
        "inventory_pressure_score": score_1_10_to_model(int(state["sb_inventory_pressure_ui"])),
        "loan_amount": loan_amt,
        "down_payment": float(state["sb_down_payment"]),
        "loan_term": ref_term,
        "standard_apr": std_apr,
        "dealer_apr": max(0.5, dealer_apr_ctx),
        "dealer_monthly_payment": max(150.0, baseline_payment),
        "customer_cash": 0.0,
        "dealer_cash": 0.0,
        "loyalty_cash": 0.0,
        "conquest_cash": 0.0,
        "promotion_flag": 0,
        "dealer_rate_support_level": baseline_support,
        "primary_competitor": str(state["sb_primary_competitor"]),
        "competitor_apr": float(state["sb_competitor_apr"]),
        "competitor_monthly_payment": float(state["sb_competitor_monthly_payment"]),
        "competitor_cashback": float(state["sb_competitor_cashback"]),
        "competitor_offer_aggressiveness_index": score_1_10_to_model(
            int(state["sb_competitor_aggr_ui"])
        ),
        "competitor_sales_volume_index": score_1_10_to_model(
            int(state["sb_competitor_sales_ui"])
        ),
        "fed_rate": float(state["sb_fed_rate"]),
        "ten_year_treasury_yield": float(state["sb_ten_year"]),
        "inflation_rate_cpi": float(state["sb_inflation_cpi"]),
        "base_auto_rate_index": float(state["sb_base_auto_rate_index"]),
        "market_rate_index": float(state["sb_market_rate_index"]),
        "month_of_quote": int(state["sb_month_of_quote"]),
        "day_of_week_quote": int(state["sb_day_of_week_quote"]),
        "quarter_end_flag": yes_no_to_bool(state["sb_quarter_end_yn"]),
        "sales_type": map_sales_ui_to_model(str(state["sb_sales_type"])),
        "region": str(state["sb_region"]),
        "state": str(state["sb_state"]),
    }


def validate_business_inputs(
    business: dict[str, Any], state: dict[str, Any]
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if float(business["vehicle_price"]) <= 0:
        errors.append("Vehicle price must be greater than zero.")

    if float(business["monthly_income"]) <= 0:
        errors.append("Monthly gross income must be greater than zero.")

    terms = loan_terms_sorted(state.get("sb_allowed_loan_terms"))
    if not terms:
        errors.append(
            "Select at least one allowed loan term under Optimization Constraints."
        )

    vp = float(business["vehicle_price"])
    la = float(business["loan_amount"])
    dp = float(business["down_payment"])

    if vp > 0 and la > vp * 1.3:
        warnings.append(
            f"Loan amount (${la:,.0f}) exceeds 130% of vehicle price (${vp:,.0f}). "
            "Results may be less reliable."
        )
    if vp > 0 and dp > vp:
        warnings.append(
            f"Down payment (${dp:,.0f}) exceeds vehicle price (${vp:,.0f}). "
            "Please verify inputs."
        )

    return errors, warnings
