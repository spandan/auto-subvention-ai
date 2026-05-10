"""
Auto Finance Offer Conversion Simulator — Streamlit app for Hugging Face Spaces.
Business-friendly inputs map to internal model features; ML column names stay off primary UI.
"""

from __future__ import annotations

import copy
import html
import itertools
import math
import os
import re
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import altair as alt
import joblib
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit.errors import StreamlitAPIException

ROOT = Path(__file__).resolve().parent

# Single-lever sensitivity charts: identical Vega width/height so three columns don’t look uneven.
_SIM_SINGLE_LEVER_CHART_W = 300
_SIM_SINGLE_LEVER_CHART_H = 280

# Executive Altair palette — soft neutrals + calm accent (less neon than raw slate/emerald).
_EXEC_CHART_PANEL_BG = "#eef3fb"
_EXEC_CHART_SERIES_LINE = "#87a1c7"
_EXEC_CHART_POINT_MUTED = "#b4c5df"
_EXEC_CHART_POINT_MUTED_STROKE = "#ccd8ea"
_EXEC_CHART_REC_FILL = "#47cba5"
_EXEC_CHART_REC_STROKE = "#14a67f"
_EXEC_CHART_SINGLE_FALLBACK = "#9fb4d2"


def _finalize_exec_altair(chart: alt.Chart) -> alt.Chart:
    """Soft panel, light grids, readable type — easy-on-the-eyes defaults for all exec charts."""
    out = (
        chart.configure_view(
            strokeWidth=0,
            strokeOpacity=0,
            fill=_EXEC_CHART_PANEL_BG,
            cornerRadius=12,
            cursor="default",
        )
        .configure_axis(
            titlePadding=18,
            labelPadding=12,
            labelFontSize=11,
            titleFontSize=12,
            titleFontWeight="normal",
            labelFontWeight="normal",
            labelColor="#5c6b7d",
            titleColor="#3d4d5c",
            domainColor="#d5dee9",
            domainWidth=1,
            tickColor="#d5dee9",
            tickWidth=1,
            grid=True,
            gridColor="#dfe8f4",
            gridOpacity=0.65,
            gridWidth=0.75,
        )
        .configure_title(
            fontSize=15,
            fontWeight=600,
            color="#1e293b",
            subtitleFontSize=11,
            subtitleFontWeight="normal",
            subtitleColor="#64748b",
            anchor="start",
            offset=10,
        )
    )
    try:
        out = out.configure(autosize=alt.AutoSizeParams(type="pad", contains="padding"))
    except (TypeError, ValueError):
        pass
    return out


# Scroll-after-nav uses session pending + injection count (wizard emits twice: after header and
# after footer widgets mount).
_WIZARD_SCROLL_PENDING_KEY = "_wizard_scroll_pending"
_WIZARD_SCROLL_INJECTIONS_LEFT_KEY = "_wizard_scroll_injections_left"

# Bump when bundled demo defaults change so returning sessions pick up the new scenario.
_DEMO_DEFAULTS_VERSION = 5
_DEMO_DEFAULTS_VERSION_KEY = "_demo_defaults_version"


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
    """Maps get_demo_defaults() → Streamlit session_state keys used by widgets."""
    d = get_demo_defaults(now)

    def yn(b: bool) -> str:
        return "Yes" if b else "No"

    lift_pp = float(d["minimum_meaningful_conversion_lift"]) * 100.0

    return {
        "sidebar_wizard_step": 0,
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
    }


def _widget_fb() -> dict[str, Any]:
    """Fresh session fallback map for explicit widget values (ties to get_demo_defaults)."""
    return session_defaults_from_demo(datetime.now())


# Keys that must stay list-valued (e.g. multiselect); all other keys are scalars for sliders.
_GV_LIST_KEYS: frozenset[str] = frozenset({"sb_allowed_loan_terms"})


def _gv(fb: dict[str, Any], key: str) -> Any:
    v = st.session_state.get(key, fb[key])
    if key in _GV_LIST_KEYS:
        return v
    # Unwrap nested singleton lists/tuples (bad session payloads, older runs).
    while isinstance(v, (list, tuple)) and len(v) == 1:
        v = v[0]
    if isinstance(v, (list, tuple)):
        v = fb[key]
    if hasattr(v, "item") and callable(getattr(v, "item", None)):
        try:
            v = v.item()
        except Exception:
            v = fb[key]
    return v


def _normalize_scalar_widget_session(*, fb: dict[str, Any]) -> None:
    """Repair corrupted scalar keys so sliders never receive list values."""
    for key, fallback in fb.items():
        if key in _GV_LIST_KEYS:
            continue
        if key not in st.session_state:
            continue
        v = st.session_state[key]
        if isinstance(v, np.ndarray):
            if v.size == 1:
                st.session_state[key] = float(np.asarray(v).reshape(-1)[0])
            else:
                st.session_state[key] = fallback
            continue
        while isinstance(v, (list, tuple)) and len(v) == 1:
            v = v[0]
            st.session_state[key] = v
            v = st.session_state[key]
        if isinstance(v, (list, tuple)):
            st.session_state[key] = fallback


def _slider_value_int(fb: dict[str, Any], key: str) -> int:
    """Always return a Python int for score / tier sliders."""
    v = _gv(fb, key)
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return int(round(float(fb[key])))


def _slider_value_num(fb: dict[str, Any], key: str) -> float:
    """Coerce session/fallback to float (APR, percentages, macro indices)."""
    v = _gv(fb, key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(fb[key])


def _sync_slider_session_float(fb: dict[str, Any], key: str) -> float:
    """
    Coerce key to float and write session_state (repairs bad payloads).
    Use with float min_value/max_value/step only; omit value= on the widget.
    """
    x = _slider_value_num(fb, key)
    st.session_state[key] = x
    return x


def _sync_slider_session_int(fb: dict[str, Any], key: str) -> int:
    """
    Coerce key to int and write session_state (repairs list-valued keys).
    Call immediately before st.slider(..., key=key) and omit value= — passing both
    triggers Streamlit's session/default widget warning.
    """
    x = _slider_value_int(fb, key)
    st.session_state[key] = x
    return x


def _clamp_scalar_int(v: Any, lo: int, hi: int) -> int:
    try:
        x = int(round(float(v)))
    except (TypeError, ValueError):
        x = lo
    return max(lo, min(hi, x))


def _clamp_scalar_float(v: Any, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = lo
    return float(max(lo, min(hi, x)))


def _exact_text_from_int(v: Any) -> str:
    return str(int(round(float(v))))


def _exact_text_from_float(v: Any, fmt: str | None) -> str:
    x = float(v)
    if fmt == "%.3f":
        return f"{x:.3f}"
    if fmt == "%.2f":
        return f"{x:.2f}"
    return f"{x:.6g}".rstrip("0").rstrip(".") if "." in f"{x:.6g}" else f"{x:.6g}"


def _slider_exact_pair_container():
    """Visually group slider + exact-value field (bordered card; stacked vertically)."""
    try:
        return st.container(border=True)
    except TypeError:
        return st.container()


def _slider_int_with_exact(
    fb: dict[str, Any],
    state_key: str,
    slider_label: str,
    *,
    min_value: int,
    max_value: int,
    step: int = 1,
    help_text: str,
    wizard: bool = True,
) -> None:
    """Slider + exact text in one bordered group (stacked: slider, then exact field)."""
    _sync_slider_session_int(fb, state_key)
    ex = f"{state_key}__exact"
    if ex not in st.session_state:
        st.session_state[ex] = _exact_text_from_int(st.session_state[state_key])

    def _slider_changed() -> None:
        st.session_state[ex] = _exact_text_from_int(st.session_state[state_key])

    def _exact_changed() -> None:
        raw = (st.session_state.get(ex) or "").strip()
        cur = int(st.session_state[state_key])
        if raw == "":
            st.session_state[ex] = _exact_text_from_int(cur)
            return
        try:
            st.session_state[state_key] = _clamp_scalar_int(
                float(raw.replace(",", "")), min_value, max_value
            )
            st.session_state[ex] = _exact_text_from_int(st.session_state[state_key])
        except ValueError:
            st.session_state[ex] = _exact_text_from_int(cur)

    def _draw_slider() -> None:
        st.slider(
            slider_label,
            min_value=min_value,
            max_value=max_value,
            step=step,
            key=state_key,
            on_change=_slider_changed,
            label_visibility="collapsed",
            **_input_help(help_text, wizard=wizard),
        )

    def _draw_exact() -> None:
        st.text_input(
            "Exact value",
            key=ex,
            placeholder="Exact value",
            on_change=_exact_changed,
            label_visibility="collapsed",
        )

    with _slider_exact_pair_container():
        _draw_slider()
        if wizard:
            st.caption("Exact value")
        _draw_exact()


def _slider_float_with_exact(
    fb: dict[str, Any],
    state_key: str,
    slider_label: str,
    *,
    min_value: float,
    max_value: float,
    step: float,
    help_text: str,
    fmt: str | None = None,
    wizard: bool = True,
) -> None:
    """Float slider + exact text in one bordered group (stacked vertically)."""
    _sync_slider_session_float(fb, state_key)
    ex = f"{state_key}__exact"
    if ex not in st.session_state:
        st.session_state[ex] = _exact_text_from_float(st.session_state[state_key], fmt)

    def _slider_changed() -> None:
        st.session_state[ex] = _exact_text_from_float(st.session_state[state_key], fmt)

    def _exact_changed() -> None:
        raw = (st.session_state.get(ex) or "").strip()
        cur = float(st.session_state[state_key])
        if raw == "":
            st.session_state[ex] = _exact_text_from_float(cur, fmt)
            return
        try:
            st.session_state[state_key] = _clamp_scalar_float(
                float(raw.replace(",", "")), min_value, max_value
            )
            st.session_state[ex] = _exact_text_from_float(st.session_state[state_key], fmt)
        except ValueError:
            st.session_state[ex] = _exact_text_from_float(cur, fmt)

    kw: dict[str, Any] = dict(
        label_visibility="collapsed",
        **_input_help(help_text, wizard=wizard),
    )
    if fmt is not None:
        kw["format"] = fmt

    def _draw_slider() -> None:
        st.slider(
            slider_label,
            min_value=min_value,
            max_value=max_value,
            step=step,
            key=state_key,
            on_change=_slider_changed,
            **kw,
        )

    def _draw_exact() -> None:
        st.text_input(
            "Exact value",
            key=ex,
            placeholder="Exact value",
            on_change=_exact_changed,
            label_visibility="collapsed",
        )

    with _slider_exact_pair_container():
        _draw_slider()
        if wizard:
            st.caption("Exact value")
        _draw_exact()


SCENARIO_SUBVENTION_BPS = [0, 25, 50, 75, 100, 125, 150, 200, 250, 300]

# Multi-lever demo reference grids (documentation / wizard hints only)
MULTI_LEVER_RATE_LEVELS = [0, 25, 50, 75, 100, 150, 200]
MULTI_LEVER_CUSTOMER_CASH = [0, 500, 1000, 1500, 2000, 2500, 3000]
MULTI_LEVER_DEALER_CASH = [0, 500, 1000, 1500]
MULTI_LEVER_LOYALTY_CASH = [0, 500, 1000]
MULTI_LEVER_CONQUEST_CASH = [0, 500, 1000]
MULTI_LEVER_LOAN_TERM = [48, 60, 72]

# Full enumeration when the configured grid is up to this many combinations (no random sampling).
MAX_FULL_ENUMERATION = 25000

LOAN_TERMS = [36, 48, 60, 72, 84]

# --- Phase 2 synthetic UI categoricals (business labels; mapped to model tokens in code) ---
CUSTOMER_SEGMENTS: list[str] = [
    "Value Shopper",
    "Payment Sensitive",
    "Loyalist",
    "Conquest Buyer",
    "Premium Buyer",
    "Utility Buyer",
    "EV Interested",
]

# Rich selectbox labels (canonical value unchanged in session_state / model).
CUSTOMER_SEGMENT_OPTION_LABELS: dict[str, str] = {
    "Value Shopper": "Value Shopper — chases rebates, discounts, and lowest total out-the-door.",
    "Payment Sensitive": "Payment Sensitive — buys on monthly payment and wallet comfort first.",
    "Loyalist": "Loyalist — loves the brand; repeat buyer; hard to lure away.",
    "Conquest Buyer": "Conquest Buyer — cross-shopping; winnable from a rival with the right offer.",
    "Premium Buyer": "Premium Buyer — pays for prestige, features, and experience over bare price.",
    "Utility Buyer": "Utility Buyer — mission-first: space, towing, durability, or work use.",
    "EV Interested": "EV Interested — prefers electric or plug-in when range and charging work.",
}


def format_customer_segment_option(segment: str) -> str:
    return CUSTOMER_SEGMENT_OPTION_LABELS.get(segment, segment)


MODEL_BY_MAKE: dict[str, list[str]] = {
    "Toyota": ["Camry", "Corolla", "RAV4", "Highlander", "Tacoma"],
    "Honda": ["Civic", "Accord", "CR-V", "Pilot"],
    "Ford": ["F-150", "Escape", "Explorer", "Mustang"],
    "Chevrolet": ["Silverado", "Equinox", "Tahoe", "Malibu"],
    "Hyundai": ["Elantra", "Sonata", "Tucson", "Palisade"],
    "Kia": ["K5", "Sportage", "Telluride", "Sorento"],
    "Nissan": ["Altima", "Rogue", "Pathfinder", "Frontier"],
    "Jeep": ["Wrangler", "Grand Cherokee", "Compass"],
    "BMW": ["330i", "X3", "X5", "i4"],
    "Mercedes": ["C300", "GLE350", "E350", "EQE"],
    "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
}
MAKES: list[str] = list(MODEL_BY_MAKE.keys())

TRIM_LEVELS: list[str] = [
    "Base",
    "Sport",
    "Premium",
    "Limited",
    "Touring",
    "Platinum",
]

BODY_STYLES_UI: list[str] = [
    "Sedan",
    "SUV",
    "Truck",
    "Coupe",
    "Hatchback",
    "Crossover",
]

FUEL_TYPES_UI: list[str] = [
    "Gasoline",
    "Hybrid",
    "Plug-in Hybrid",
    "Diesel",
    "EV",
]

VEHICLE_SEGMENTS: list[str] = [
    "Economy",
    "Compact SUV",
    "Midsize SUV",
    "Luxury",
    "Truck",
    "Sedan",
    "EV",
]

DEALER_SIZE_TIERS: list[str] = ["Small", "Medium", "Large", "Mega"]

PRIMARY_COMPETITORS: list[str] = [
    "Toyota",
    "Honda",
    "Ford",
    "Chevrolet",
    "Hyundai",
    "Kia",
    "Nissan",
    "Tesla",
    "BMW",
]

SALES_TYPES_UI: list[str] = ["Retail", "Lease", "Finance", "Cash"]

REGIONS: list[str] = [
    "Northeast",
    "Southeast",
    "Midwest",
    "Southwest",
    "West",
]

STATES: list[str] = [
    "TX",
    "CA",
    "FL",
    "NY",
    "NJ",
    "IL",
    "AZ",
    "WA",
    "GA",
    "NC",
]

MONTH_OPTIONS: list[int] = list(range(1, 13))
MONTH_LABELS: list[str] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

DOW_LABELS: list[str] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

YES_NO: tuple[str, ...] = ("Yes", "No")


def rate_support_tier_label(level: int) -> str:
    """Executive-facing label for internal rate-support index (0–300)."""
    if level == 0:
        return "No Support"
    if level == 25:
        return "Very Low Support"
    if level == 50:
        return "Low Support"
    if level == 75:
        return "Moderate Support"
    if level == 100:
        return "Strong Support"
    if level >= 125:
        return "Very Strong Support"
    return f"Support tier ({level})"


def EXEC_FONT_LINKS() -> str:
    """Inter — same class of UI font as modern research/analytics products (e.g. Perplexity-style polish)."""
    return """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
"""


def EXEC_THEME_CSS() -> str:
    return """
<style>
    /* --- Typography: Inter + sensible system stack (free, open font) --- */
    html, body, .stApp {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
            "Helvetica Neue", Arial, sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* --- Remove Streamlit’s large default top gap (main + sidebar) --- */
    [data-testid="stAppViewContainer"] {
        padding-top: 0 !important;
    }
    [data-testid="stHeader"] {
        background: rgba(250, 250, 250, 0.96) !important;
        border-bottom: 1px solid #e4e4e7 !important;
    }
    /* Decorative gradient blob — hides extra vertical gap on many Streamlit versions */
    [data-testid="stDecoration"] {
        display: none !important;
    }
    /* Main column: default block-container padding-top is ~5–6rem — tighten heavily */
    [data-testid="stMain"] > div:first-child,
    section.main > div {
        padding-top: 0 !important;
    }
    [data-testid="stMain"] .block-container,
    section.main > div.block-container,
    .main .block-container {
        padding-top: 0.75rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 100% !important;
    }
    /* Sidebar: same issue — excess padding above first heading */
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0 !important;
    }
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] {
        padding-top: 0.25rem !important;
    }
    [data-testid="stSidebar"] .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    /* --- Base app surface --- */
    .stApp {
        background: linear-gradient(180deg, #f4f4f5 0%, #ebebed 100%) !important;
        color: #18181b !important;
    }
    [data-testid="stSidebar"] {
        background-color: #fafafa !important;
        border-right: 1px solid #e4e4e7 !important;
    }

    /* Edit panel: single-column feel — full-width dropdowns, air between control groups */
    [data-testid="stSidebar"] div[data-baseweb="select"],
    [data-testid="stSidebar"] [data-testid="stSelectbox"] > div,
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] > div {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
        margin-top: 0.35rem !important;
        margin-bottom: 1.35rem !important;
    }
    [data-testid="stSidebar"] div[data-testid="element-container"]:has([data-baseweb="select"]) {
        margin-bottom: 0.85rem !important;
        width: 100% !important;
        max-width: 100% !important;
    }
    [data-testid="stSidebar"] .stSlider {
        margin-bottom: 0.15rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stTextInput"] {
        margin-bottom: 0.35rem !important;
    }

    /* Altair embeds: extra inset so axis titles / % ticks aren’t clipped at container edges */
    [data-testid="stVegaLiteChart"] {
        padding: 0.45rem 0.6rem 0.8rem 0.55rem !important;
        box-sizing: border-box !important;
    }

    /* Results view: scroll-to-top target sits above the page title */
    .results-view-scroll-target {
        scroll-margin-top: 0.5rem;
    }

    /* --- All widget labels (sidebar + main): force readable contrast --- */
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] p,
    label[data-testid="stWidgetLabel"] {
        color: #18181b !important;
        opacity: 1 !important;
        font-weight: 500 !important;
        font-size: 0.9375rem !important;
    }
    /* ? chip + hover popup (DOM text; avoids stripped title= in st.markdown HTML) */
    .exec-field-help-wrap {
        position: relative;
        display: inline-flex;
        align-items: center;
        align-self: center;
        vertical-align: middle;
        margin-left: 0.35rem;
        flex-shrink: 0;
    }
    .exec-field-help-trigger {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1rem;
        height: 1rem;
        border-radius: 9999px;
        border: 1px solid #d4d4d8;
        background: #fafafa;
        color: #71717a;
        font-size: 0.62rem;
        font-weight: 700;
        cursor: pointer;
        line-height: 1;
        user-select: none;
    }
    .exec-field-help-popup {
        visibility: hidden;
        opacity: 0;
        pointer-events: none;
        position: absolute;
        z-index: 999999;
        left: 50%;
        top: calc(100% + 6px);
        transform: translateX(-50%);
        min-width: 280px;
        max-width: min(480px, 92vw);
        padding: 10px 12px;
        background: #18181b;
        color: #fafafa;
        font-size: 0.8125rem;
        font-weight: 400;
        line-height: 1.45;
        text-align: left;
        letter-spacing: normal;
        text-transform: none;
        border-radius: 10px;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.22);
        word-break: break-word;
        transition: opacity 0.12s ease, visibility 0.12s ease;
    }
    .exec-field-help-popup::after {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        margin-left: -6px;
        border: 6px solid transparent;
        border-bottom-color: #18181b;
    }
    .exec-field-help-wrap:hover .exec-field-help-popup,
    .exec-field-help-wrap:focus-within .exec-field-help-popup {
        visibility: visible;
        opacity: 1;
        pointer-events: auto;
    }
    /* Popups use position:absolute; parent overflow:hidden would clip them */
    .stMarkdown:has(.exec-field-help-wrap),
    [data-testid="stMarkdownContainer"]:has(.exec-field-help-wrap) {
        overflow: visible !important;
    }
    /* Slider accent (primary theme is set in .streamlit/config.toml for HF + local) */
    .stSlider [role="slider"] {
        accent-color: #475569 !important;
    }
    /*
     * Thumb value / numeric ticks: Streamlit/Base Web default to a monospace stack so digits
     * line up; override to Inter like the rest of the UI (keep tabular figures for alignment).
     */
    .stSlider [data-testid="stThumbValue"] {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
            sans-serif !important;
        font-variant-numeric: tabular-nums;
    }

    /* --- Tabs: inactive must stay legible --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: transparent !important;
        border-bottom: 1px solid #d4d4d8 !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #3f3f46 !important;
        opacity: 1 !important;
        font-weight: 500 !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 0.5rem 1rem !important;
    }
    .stTabs [aria-selected="false"] {
        color: #3f3f46 !important;
        background: transparent !important;
        border-bottom: 2px solid transparent !important;
    }
    .stTabs [aria-selected="true"] {
        background: #ffffff !important;
        color: #18181b !important;
        font-weight: 600 !important;
        border: 1px solid #e4e4e7 !important;
        border-bottom: 2px solid #475569 !important;
    }

    /* --- Metrics (native Streamlit): label + value --- */
    [data-testid="stMetricContainer"] {
        background: #ffffff !important;
        border: 1px solid #e4e4e7 !important;
        border-radius: 10px !important;
        padding: 0.85rem 1rem !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05) !important;
    }
    [data-testid="stMetricLabel"] {
        opacity: 1 !important;
    }
    [data-testid="stMetricLabel"] div,
    [data-testid="stMetricLabel"] label,
    [data-testid="stMetricLabel"] p {
        color: #3f3f46 !important;
        font-weight: 600 !important;
        font-size: 0.8125rem !important;
    }
    [data-testid="stMetricValue"] {
        color: #18181b !important;
        font-weight: 700 !important;
        font-size: 1.35rem !important;
    }

    /* --- Sidebar section headings --- */
    [data-testid="stSidebar"] h3 {
        color: #18181b !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        margin-top: 1rem !important;
    }

    /* --- Cards --- */
    .exec-hero-card {
        background: #ffffff;
        border: 1px solid #e4e4e7;
        border-radius: 12px;
        padding: 1.75rem 2rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }
    .exec-hero-card .exec-label {
        color: #52525b;
        font-size: 0.8125rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }
    .exec-hero-card .exec-value {
        color: #18181b;
        font-size: 2.65rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        line-height: 1.1;
        margin: 0;
    }

    .exec-hero-metrics-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.75rem 0 1.25rem 0;
    }
    @media (max-width: 1100px) {
        .exec-hero-metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 560px) {
        .exec-hero-metrics-grid { grid-template-columns: 1fr; }
    }
    .exec-hero-metric-tile {
        background: #f8fafc;
        border: 1px solid #e4e4e7;
        border-radius: 10px;
        padding: 1rem 1.15rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }
    .exec-hero-metric-tile.exec-hero-metric-rec {
        background: #ecfdf5;
        border-color: #bbf7d0;
    }
    .exec-hero-metric-tile .ehm-label {
        color: #52525b;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin: 0 0 0.35rem 0;
    }
    .exec-hero-metric-tile .ehm-value {
        color: #18181b;
        font-size: 1.35rem;
        font-weight: 700;
        margin: 0;
        line-height: 1.2;
    }
    .exec-hero-metric-tile .ehm-sub {
        color: #64748b;
        font-size: 0.78rem;
        margin: 0.35rem 0 0 0;
        line-height: 1.35;
    }

    .exec-summary-callout {
        background: #ffffff;
        border: 1px solid #e4e4e7;
        border-left: 4px solid #14a67f;
        border-radius: 10px;
        padding: 1.1rem 1.35rem;
        margin: 0 0 1.25rem 0;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }
    .exec-summary-callout p {
        margin: 0;
        color: #334155;
        font-size: 1.02rem;
        line-height: 1.55;
    }

    .exec-scenario-compare-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.85rem;
        margin: 0.5rem 0 1rem 0;
    }
    @media (max-width: 900px) {
        .exec-scenario-compare-grid { grid-template-columns: 1fr; }
    }
    .exec-scenario-compare-card {
        background: #ffffff;
        border: 1px solid #e4e4e7;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }
    .exec-scenario-compare-card.exec-scen-rec {
        background: #ecfdf5;
        border-color: #bbf7d0;
    }
    .exec-scenario-compare-card .esc-title {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        color: #475569;
        margin: 0 0 0.65rem 0;
    }
    .exec-scenario-compare-card .esc-row {
        display: flex;
        justify-content: space-between;
        gap: 0.5rem;
        font-size: 0.88rem;
        padding: 0.28rem 0;
        border-bottom: 1px solid #f1f5f9;
        color: #334155;
    }
    .exec-scenario-compare-card .esc-row:last-child { border-bottom: none; }
    .exec-scenario-compare-card .esc-k { color: #64748b; }
    .exec-scenario-compare-card .esc-v { font-weight: 600; color: #0f172a; text-align: right; }

    /* Four-up scenario snapshot cards — CSS Grid keeps equal height per row */
    .exec-subcard-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.85rem;
        align-items: stretch;
        margin: 0.5rem 0 0.75rem 0;
    }
    .exec-subcard-grid .exec-subcard {
        min-width: 0;
        min-height: 100%;
        display: flex;
        flex-direction: column;
        box-sizing: border-box;
    }
    @media (max-width: 1100px) {
        .exec-subcard-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    @media (max-width: 560px) {
        .exec-subcard-grid {
            grid-template-columns: 1fr;
        }
    }
    .exec-subcard {
        background: #ffffff;
        border: 1px solid #e4e4e7;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        height: 100%;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }
    .exec-subcard .esl {
        color: #52525b;
        font-size: 0.8125rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.35rem;
    }
    .exec-subcard .esv {
        color: #18181b;
        font-size: 1.1rem;
        font-weight: 700;
    }
    .exec-subcard .exec-muted-small {
        color: #52525b !important;
        font-size: 0.875rem !important;
        line-height: 1.45 !important;
        margin-top: 0.5rem !important;
    }
    /* Scenario exploration charts — title row + summary strip */
    .exec-chart-title-main {
        margin: 0 !important;
        padding: 0.15rem 0 0 0 !important;
        color: #18181b !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
        line-height: 1.35 !important;
    }
    .exec-chart-guide {
        font-size: 0.875rem;
        color: #3f3f46;
        line-height: 1.55;
        margin: 0 0 0.85rem 0;
        padding: 0.65rem 1rem 0.7rem 1rem;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        border-left: 4px solid #64748b;
    }
    .exec-muted-small .exec-field-help-wrap {
        display: inline-flex;
        vertical-align: middle;
        margin-left: 0.2rem;
    }
    .exec-section-title {
        color: #27272a;
        font-size: 1rem;
        font-weight: 700;
        margin: 1.35rem 0 0.75rem 0;
        letter-spacing: -0.01em;
    }
    .exec-muted {
        color: #52525b;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .exec-note {
        color: #52525b;
        font-size: 0.95rem;
        line-height: 1.5;
        margin: 0.35rem 0 0.75rem 0;
    }

    .exec-rec-card {
        border-color: #86efac !important;
        background: linear-gradient(180deg, #ecfdf5 0%, #ffffff 55%) !important;
        box-shadow: 0 2px 10px rgba(22, 101, 52, 0.07) !important;
    }

    h1 {
        color: #18181b !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        margin-top: 0.15rem !important;
        margin-bottom: 0.35rem !important;
    }
    h2, h3 { color: #27272a !important; }

    /* Captions & small body: never rely on faint gray alone */
    .stCaption, [data-testid="stCaption"],
    div[data-testid="stCaptionContainer"] {
        color: #52525b !important;
        font-size: 0.95rem !important;
        opacity: 1 !important;
    }

    /* Finance loader overlay (model / prediction / simulations) */
    @keyframes exec-ml-pulse {
        0%, 100% { opacity: 0.45; transform: translateX(0); }
        50% { opacity: 1; transform: translateX(2px); }
    }
    @keyframes exec-ml-track {
        0% { stroke-dashoffset: 40; }
        100% { stroke-dashoffset: 0; }
    }
    .exec-ml-panel {
        border: 1px solid #e4e4e7;
        border-radius: 12px;
        padding: 2rem 2rem 1.75rem;
        margin: 0 0 1rem 0;
        background: linear-gradient(165deg, #fafafa 0%, #ffffff 55%);
        text-align: center;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
    }
    .exec-ml-car-wrap {
        display: inline-block;
        animation: exec-ml-pulse 2s ease-in-out infinite;
    }
    .exec-ml-road {
        margin: 0 auto 0.5rem;
        max-width: 160px;
        height: 3px;
        border-radius: 2px;
        background: linear-gradient(90deg, #e4e4e7 0%, #cbd5e1 50%, #e4e4e7 100%);
    }
    .exec-ml-road svg path {
        stroke-dasharray: 8 6;
        animation: exec-ml-track 1.2s linear infinite;
    }
    .exec-ml-label {
        margin-top: 0.85rem;
        color: #27272a;
        font-family: Inter, system-ui, sans-serif;
        font-size: 0.95rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }
    .exec-ml-sub {
        margin-top: 0.35rem;
        color: #71717a;
        font-family: Inter, system-ui, sans-serif;
        font-size: 0.8125rem;
        font-weight: 500;
    }
    /* Full-viewport blocker while model loads / analysis runs (above main + sidebar) */
    .exec-ml-fullscreen {
        position: fixed !important;
        inset: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 100002 !important;
        margin: 0 !important;
        padding: 2rem 1rem !important;
        box-sizing: border-box !important;
        background: rgba(247, 248, 250, 0.98) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .exec-ml-fullscreen .exec-ml-panel {
        margin: 0 auto !important;
        max-width: min(520px, 100%) !important;
        width: 100% !important;
    }

    /* Same as wizard: slider + exact text row — border on input only (sidebar edit + main) */
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:first-child [data-testid="element-container"],
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:nth-child(2) [data-testid="element-container"] {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:first-child [data-testid="stVerticalBlock"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:nth-child(2) [data-testid="stTextInput"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:nth-child(2) [data-testid="stTextInput"] input {
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
        background: #FFFFFF !important;
        padding: 0.4rem 0.55rem !important;
        box-shadow: none !important;
    }
</style>
"""


def MODEL_LOADING_PANEL_HTML(
    title: str = "Loading analytical model",
    subtitle: str = "Calibrating finance conversion engine — one moment.",
    *,
    fullscreen: bool = False,
) -> str:
    """Professional auto-themed loader panel (CSS lives in EXEC_THEME_CSS)."""
    t = html.escape(title)
    s = html.escape(subtitle)
    inner = f"""
<div class="exec-ml-panel">
  <div class="exec-ml-road">
    <svg width="160" height="4" viewBox="0 0 160 4" xmlns="http://www.w3.org/2000/svg">
      <path d="M0 2 H160" stroke="#94a3b8" stroke-width="1.5" fill="none"/>
    </svg>
  </div>
  <div class="exec-ml-car-wrap">
    <svg width="132" height="56" viewBox="0 0 132 56" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M8 38 L22 28 L38 22 L58 18 H96 L112 22 L124 30 L128 38 V42 H8 Z"
            stroke="#334155" stroke-width="1.75" fill="none" stroke-linejoin="round"/>
      <path d="M42 22 L52 14 H84 L94 18" stroke="#64748b" stroke-width="1.25" fill="none" stroke-linecap="round"/>
      <circle cx="36" cy="40" r="9" stroke="#475569" stroke-width="1.75" fill="#f4f4f5"/>
      <circle cx="98" cy="40" r="9" stroke="#475569" stroke-width="1.75" fill="#f4f4f5"/>
      <circle cx="36" cy="40" r="3.5" fill="#94a3b8"/>
      <circle cx="98" cy="40" r="3.5" fill="#94a3b8"/>
    </svg>
  </div>
  <div class="exec-ml-label">{t}</div>
  <div class="exec-ml-sub">{s}</div>
</div>
"""
    if fullscreen:
        return f'<div class="exec-ml-fullscreen">{inner}</div>'
    return inner


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def load_model():
    path = ROOT / "model_pipeline.pkl"
    if not path.is_file():
        raise FileNotFoundError(f"Model file not found: {path}")
    # Register native extension + sklearn bindings before unpickling the pipeline.
    import lightgbm  # noqa: F401
    from lightgbm.sklearn import LGBMClassifier  # noqa: F401

    try:
        return joblib.load(path)
    except Exception as e:
        raise RuntimeError(
            f"Could not unpickle model at {path}: {type(e).__name__}: {e}. "
            "Use scikit-learn==1.6.1 and lightgbm==4.5.0 (see requirements.txt). "
            "On Linux deploys, install OpenMP (e.g. apt package libgomp1) if LightGBM fails to load."
        ) from e


@st.cache_data(show_spinner=False)
def load_json(filename: str) -> dict | list | None:
    path = ROOT / filename
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_feature_schema() -> dict:
    data = load_json("feature_schema.json")
    if not isinstance(data, dict):
        raise ValueError(
            "feature_schema.json is missing or invalid. Expected a JSON object with "
            '"required_columns".'
        )
    cols = data.get("required_columns")
    if not isinstance(cols, list) or not cols:
        raise ValueError(
            'feature_schema.json must contain a non-empty list "required_columns".'
        )
    return data


def get_sample_defaults() -> dict:
    raw = load_json("sample_input.json")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("sample_input.json must be a JSON object (key → value).")
    return raw


def _deployment_startup_gate() -> None:
    """
    Railway-oriented checks: required artifact paths and eager load of model/schema at startup.
    """
    required_files = ["model_pipeline.pkl", "feature_schema.json"]
    missing = [f for f in required_files if not (ROOT / f).is_file()]

    if missing:
        st.error(f"Missing required deployment files: {missing}")
        st.stop()

    try:
        load_model()
    except Exception as e:
        st.error(f"Failed to load ML pipeline: {e}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())
        st.stop()

    try:
        get_feature_schema()
    except ValueError as e:
        st.error(str(e))
        with st.expander("Traceback"):
            st.code(traceback.format_exc())
        st.stop()


# ---------------------------------------------------------------------------
# Business logic → model features (internal names unchanged)
# ---------------------------------------------------------------------------


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
    """Map 1–10 slider to model scale: value / 10 (typically 0.1–1.0)."""
    return int(score) / 10.0


def sentiment_ui_to_model(slider: int) -> float:
    """Map 1–10 sentiment slider to an approximately −1…+1 score: (v−5)/5."""
    return (int(slider) - 5) / 5.0


def map_fuel_ui_to_model(ui: str) -> str:
    """Map business fuel label → pipeline / training label."""
    return {
        "Gasoline": "Gas",
        "Hybrid": "Hybrid",
        "Plug-in Hybrid": "PHEV",
        "Diesel": "Diesel",
        "EV": "EV",
    }.get(str(ui), "Gas")


def map_sales_ui_to_model(ui: str) -> str:
    """Map business sales type → pipeline / training label."""
    return {
        "Retail": "APR",
        "Lease": "Lease",
        "Finance": "Mixed",
        "Cash": "Cash",
    }.get(str(ui), "APR")


def map_body_ui_to_model(ui: str) -> str:
    """Map business body style → pipeline / training label."""
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


def render_behavioral_scoring_guide_main() -> None:
    """Compact reference for 1–10 behavioral sliders."""
    st.markdown(
        """
Most attitude and sensitivity inputs use a **1–10** scale. Internally they are converted with  
**score ÷ 10** (values from **0.1** to **1.0**).

**Customer sentiment** is different: the model uses **(score − 5) ÷ 5**, so **5 ≈ neutral**,
**1 ≈ very negative**, and **10 ≈ very positive**.

Use **5** or **6** when you are unsure for most sliders — that is a neutral-to-moderate position.
        """
    )


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
    """Standard amortizing monthly payment (optional sanity check / approximation)."""
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

    payment_to_income = (
        clip(dealer_payment / mi, 0.001, 1.0) if mi > 0 else 0.5
    )
    ltv = clip(la / vp, 0.01, 2.0) if vp > 0 else 0.8
    down_payment_pct = (dp / vp) if vp > 0 else 0.0

    apr_gap_bps = (dealer_apr - competitor_apr) * 100.0
    payment_gap = dealer_payment - cmp_pay
    cashback_gap = total_cash_rebate - competitor_cashback

    ca_idx = float(inp["competitor_offer_aggressiveness_index"])
    cs_idx = float(inp["competitor_sales_volume_index"])
    competitor_pressure_score = (
        0.5 * ca_idx
        + 0.3 * cs_idx
        + 0.2 * max(apr_gap_bps, 0.0) / 300.0
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
    # Effective customer rate after support (matches scenario sweep: std − support/100, floor 0.5%)
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
    """Alias for compatibility — Phase 2 unified inputs."""
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


def predict_conversion(pipeline: Any, model_df: pd.DataFrame) -> float:
    if not hasattr(pipeline, "predict_proba"):
        raise AttributeError(
            "The loaded pipeline does not support predict_proba(). "
            "Use a classifier with probability estimates."
        )
    proba = pipeline.predict_proba(model_df)
    if proba.ndim != 2 or proba.shape[1] < 2:
        raise ValueError(
            f"Unexpected predict_proba output shape: {getattr(proba, 'shape', None)}"
        )
    return float(proba[0, 1])


def estimate_support_cost(inputs_row: dict[str, Any], support_level: float, cm: float) -> float:
    """Phase 2 total estimated support cost including cash components."""
    la = float(inputs_row["loan_amount"])
    cc = float(inputs_row["customer_cash"])
    lc = float(inputs_row["loyalty_cash"])
    cq = float(inputs_row["conquest_cash"])
    dc = float(inputs_row["dealer_cash"])
    return (
        la * (float(support_level) / 10000.0) * float(cm)
        + cc
        + lc
        + cq
        + dc
    )


def scenario_adjusted_loan_amount(
    base_inputs: dict[str, Any],
    customer_cash: float,
    dealer_cash: float,
    loyalty_cash: float,
    conquest_cash: float,
) -> float:
    """
    Financed amount decreases when stacked incentives exceed the baseline quote
    (same nominal vehicle/down assumption; incremental cash vs baseline reduces principal).
    """
    base_la = float(base_inputs["loan_amount"])
    bc = float(base_inputs["customer_cash"])
    bd = float(base_inputs["dealer_cash"])
    bl = float(base_inputs["loyalty_cash"])
    bq = float(base_inputs["conquest_cash"])
    delta_cash = (
        (float(customer_cash) - bc)
        + (float(dealer_cash) - bd)
        + (float(loyalty_cash) - bl)
        + (float(conquest_cash) - bq)
    )
    return max(5000.0, base_la - delta_cash)


def apply_offer_scenario_levers(
    base_inputs: dict[str, Any],
    *,
    support_level: float,
    customer_cash: float,
    dealer_cash: float,
    loyalty_cash: float,
    conquest_cash: float,
    loan_term: int,
) -> dict[str, Any]:
    """Apply multi-lever edits; APR from support tier; payment from amortization."""
    s = copy.deepcopy(base_inputs)
    s["dealer_rate_support_level"] = float(support_level)
    s["customer_cash"] = float(customer_cash)
    s["dealer_cash"] = float(dealer_cash)
    s["loyalty_cash"] = float(loyalty_cash)
    s["conquest_cash"] = float(conquest_cash)
    s["loan_term"] = int(loan_term)
    std = float(s["standard_apr"])
    s["dealer_apr"] = max(0.5, std - float(support_level) / 100.0)
    la = scenario_adjusted_loan_amount(
        base_inputs, customer_cash, dealer_cash, loyalty_cash, conquest_cash
    )
    s["loan_amount"] = la
    s["dealer_monthly_payment"] = calculate_monthly_payment_if_needed(
        la, s["dealer_apr"], int(loan_term)
    )
    return s


def _predict_scenario_row(
    scenario: dict[str, Any],
    pipeline: Any,
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
) -> tuple[dict[str, Any] | None, float | None, str | None]:
    row_model = calculate_model_features(scenario)
    X, err, _, _ = align_to_schema(row_model, schema, sample_defaults)
    if err or X is None:
        return None, None, err or "Alignment failed."
    try:
        p = predict_conversion(pipeline, X)
    except Exception as e:
        return None, None, str(e)
    return row_model, float(p), None


def _loan_terms_sorted_from_session(raw: Any) -> list[int]:
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


def build_optimization_constraints_from_session() -> dict[str, Any]:
    """User-defined search bounds — not scenario values."""
    terms = _loan_terms_sorted_from_session(st.session_state.get("sb_allowed_loan_terms"))
    return {
        "max_oem_customer_cash": float(st.session_state.get("sb_max_oem_customer_cash") or 0),
        "max_dealer_cash": float(st.session_state.get("sb_max_dealer_cash_support") or 0),
        "max_rate_support": max(0, int(st.session_state.get("sb_max_apr_rate_support") or 0)),
        "allow_loyalty": yes_no_to_bool(st.session_state.get("sb_allow_loyalty_incentive")),
        "max_loyalty_cash": float(st.session_state.get("sb_max_loyalty_incentive") or 0),
        "allow_conquest": yes_no_to_bool(st.session_state.get("sb_allow_conquest_incentive")),
        "max_conquest_cash": float(st.session_state.get("sb_max_conquest_incentive") or 0),
        "max_total_support_budget": float(
            st.session_state.get("sb_max_total_support_budget") or 1e12
        ),
        "min_acceptable_remaining_margin": float(
            st.session_state.get("sb_min_acceptable_remaining_margin") or 0
        ),
        "min_conversion_lift_vs_no_support": float(
            (st.session_state.get("sb_min_meaningful_lift_pp") or 2.0) / 100.0
        ),
        "allowed_loan_terms": terms,
    }


def _rate_support_grid(mx: int) -> list[int]:
    step = int(
        st.session_state.get("sb_rate_support_step")
        or get_demo_defaults()["rate_support_step"]
    )
    step = max(1, step)
    return [r for r in range(0, max(0, int(mx)) + 1, step)]


def _cash_steps_500(max_usd: float) -> list[float]:
    step = float(
        st.session_state.get("sb_cash_support_step")
        or get_demo_defaults()["cash_support_step"]
    )
    step = max(1.0, step)
    mx = float(max_usd)
    if mx <= 0:
        return [0.0]
    vals: list[float] = []
    v = 0.0
    while v <= mx + 1e-9:
        vals.append(round(v, 2))
        v += step
    return vals


def _rate_support_grid_fixed(mx: int, step: int) -> list[int]:
    step = max(1, int(step))
    return [r for r in range(0, max(0, int(mx)) + 1, step)]


def _cash_steps_fixed(max_usd: float, step: float) -> list[float]:
    step = max(1.0, float(step))
    mx = float(max_usd)
    if mx <= 0:
        return [0.0]
    vals: list[float] = []
    v = 0.0
    while v <= mx + 1e-9:
        vals.append(round(v, 2))
        v += step
    return vals


def _fine_optimization_grids(constraints: dict[str, Any]) -> tuple:
    return (
        _rate_support_grid(int(constraints["max_rate_support"])),
        _cash_steps_500(float(constraints["max_oem_customer_cash"])),
        _cash_steps_500(float(constraints["max_dealer_cash"])),
        _cash_steps_500(float(constraints["max_loyalty_cash"]))
        if constraints["allow_loyalty"]
        else [0.0],
        _cash_steps_500(float(constraints["max_conquest_cash"]))
        if constraints["allow_conquest"]
        else [0.0],
        [int(x) for x in constraints["allowed_loan_terms"]],
    )


def _coarse_optimization_grids(constraints: dict[str, Any]) -> tuple:
    return (
        _rate_support_grid_fixed(int(constraints["max_rate_support"]), 50),
        _cash_steps_fixed(float(constraints["max_oem_customer_cash"]), 1000.0),
        _cash_steps_fixed(float(constraints["max_dealer_cash"]), 1000.0),
        _cash_steps_fixed(float(constraints["max_loyalty_cash"]), 1000.0)
        if constraints["allow_loyalty"]
        else [0.0],
        _cash_steps_fixed(float(constraints["max_conquest_cash"]), 1000.0)
        if constraints["allow_conquest"]
        else [0.0],
        [int(x) for x in constraints["allowed_loan_terms"]],
    )


def _combo_tuple_from_parts(
    sup: float | int,
    cc: float,
    dc: float,
    lc: float,
    cq: float,
    term: int,
) -> tuple[Any, ...]:
    return (
        int(sup),
        round(float(cc), 2),
        round(float(dc), 2),
        round(float(lc), 2),
        round(float(cq), 2),
        int(term),
    )


def _series_to_combo_tuple(row: pd.Series) -> tuple[Any, ...]:
    return _combo_tuple_from_parts(
        row["dealer_rate_support_level"],
        float(row["customer_cash"]),
        float(row["dealer_cash"]),
        float(row["loyalty_cash"]),
        float(row["conquest_cash"]),
        int(row["loan_term"]),
    )


def _refined_neighbor_tuples(
    row: pd.Series,
    optimization_constraints: dict[str, Any],
) -> set[tuple[Any, ...]]:
    mx_rate = int(optimization_constraints["max_rate_support"])
    max_cc = float(optimization_constraints["max_oem_customer_cash"])
    max_dc = float(optimization_constraints["max_dealer_cash"])
    allow_loyalty = optimization_constraints["allow_loyalty"]
    max_loy = float(optimization_constraints["max_loyalty_cash"]) if allow_loyalty else 0.0
    allow_conquest = optimization_constraints["allow_conquest"]
    max_cq = float(optimization_constraints["max_conquest_cash"]) if allow_conquest else 0.0
    terms = sorted(int(x) for x in optimization_constraints["allowed_loan_terms"])

    sup0 = int(row["dealer_rate_support_level"])
    cc0 = float(row["customer_cash"])
    dc0 = float(row["dealer_cash"])
    lc0 = float(row["loyalty_cash"])
    cq0 = float(row["conquest_cash"])
    t0 = int(row["loan_term"])

    def clamp_cash(x: float, mxv: float) -> float:
        return round(max(0.0, min(float(mxv), x)), 2)

    term_neighbors: set[int] = {t0}
    if t0 in terms:
        ti = terms.index(t0)
        if ti > 0:
            term_neighbors.add(terms[ti - 1])
        if ti < len(terms) - 1:
            term_neighbors.add(terms[ti + 1])

    loyalty_ds = (-500, 0, 500) if allow_loyalty else (0,)
    conquest_ds = (-500, 0, 500) if allow_conquest else (0,)

    out: set[tuple[Any, ...]] = set()
    for ds in (-25, 0, 25):
        sup = sup0 + ds
        if sup < 0 or sup > mx_rate:
            continue
        for dcc in (-500, 0, 500):
            cc = clamp_cash(cc0 + dcc, max_cc)
            for ddc in (-500, 0, 500):
                dc = clamp_cash(dc0 + ddc, max_dc)
                for dll in loyalty_ds:
                    lc = clamp_cash(lc0 + dll, max_loy) if allow_loyalty else 0.0
                    for dcq in conquest_ds:
                        cq = clamp_cash(cq0 + dcq, max_cq) if allow_conquest else 0.0
                        for term in term_neighbors:
                            out.add(_combo_tuple_from_parts(sup, cc, dc, lc, cq, term))
    return out


def _score_offer_combination_list(
    base_inputs: dict[str, Any],
    combos: list[tuple[Any, ...]],
    pipeline: Any,
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
    cost_multiplier: float,
    *,
    idx_offset: int = 0,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    term_baseline_cache: dict[int, float] = {}

    def get_p_no_incentive_package(term: int) -> float:
        t = int(term)
        if t not in term_baseline_cache:
            scen0 = apply_offer_scenario_levers(
                base_inputs,
                support_level=0.0,
                customer_cash=0.0,
                dealer_cash=0.0,
                loyalty_cash=0.0,
                conquest_cash=0.0,
                loan_term=t,
            )
            _rm, p0, err = _predict_scenario_row(
                scen0, pipeline, schema, sample_defaults
            )
            term_baseline_cache[t] = 0.0 if err or p0 is None else float(p0)
        return float(term_baseline_cache[t])

    p_zero_rate_cache: dict[tuple[float, float, float, float, int], float] = {}

    def get_p_zero_rate_same_cash(
        cc: float, dc: float, lc: float, cq: float, term: int
    ) -> float:
        key = (cc, dc, lc, cq, term)
        if key not in p_zero_rate_cache:
            scen0 = apply_offer_scenario_levers(
                base_inputs,
                support_level=0.0,
                customer_cash=cc,
                dealer_cash=dc,
                loyalty_cash=lc,
                conquest_cash=cq,
                loan_term=term,
            )
            _rm, p0, err = _predict_scenario_row(
                scen0, pipeline, schema, sample_defaults
            )
            if err or p0 is None:
                p_zero_rate_cache[key] = 0.0
            else:
                p_zero_rate_cache[key] = float(p0)
        return float(p_zero_rate_cache[key])

    rows: list[dict[str, Any]] = []
    margin = float(base_inputs["expected_unit_margin"])
    cm = float(cost_multiplier)

    for i, (sup, cc, dc, lc, cq, term) in enumerate(combos):
        scen = apply_offer_scenario_levers(
            base_inputs,
            support_level=float(sup),
            customer_cash=float(cc),
            dealer_cash=float(dc),
            loyalty_cash=float(lc),
            conquest_cash=float(cq),
            loan_term=int(term),
        )
        rm, p, err = _predict_scenario_row(scen, pipeline, schema, sample_defaults)
        if err or rm is None or p is None:
            return None, err or "Prediction failed in multi-lever sweep."

        p_pkg0 = get_p_no_incentive_package(int(term))
        p_rate0 = get_p_zero_rate_same_cash(
            float(cc), float(dc), float(lc), float(cq), int(term)
        )
        lift_vs_baseline = float(p) - float(p_pkg0)
        lift_marginal_rate = float(p) - float(p_rate0)
        la = float(scen["loan_amount"])
        esc = (
            la * (float(sup) / 10000.0) * cm
            + float(cc)
            + float(dc)
            + float(lc)
            + float(cq)
        )
        ev = float(p) * margin - esc
        eff = lift_vs_baseline / max(esc, 1.0)
        rem_margin = margin - esc

        rows.append(
            {
                "scenario_idx": idx_offset + i,
                "dealer_rate_support_level": int(sup),
                "rate_support_tier": rate_support_tier_label(int(sup)),
                "scenario_dealer_apr": float(rm["dealer_apr"]),
                "subvented_apr": float(rm["subvented_apr"]),
                "scenario_dealer_monthly_payment": float(rm["dealer_monthly_payment"]),
                "loan_term": int(term),
                "scenario_loan_amount": la,
                "customer_cash": float(cc),
                "dealer_cash": float(dc),
                "loyalty_cash": float(lc),
                "conquest_cash": float(cq),
                "total_cash_rebate": float(rm["total_cash_rebate"]),
                "conversion_probability": float(p),
                "conversion_lift_vs_baseline": lift_vs_baseline,
                "conversion_lift_vs_no_support": lift_vs_baseline,
                "conversion_lift_vs_zero_apr_same_cash": lift_marginal_rate,
                "conversion_lift_vs_current": lift_vs_baseline,
                "estimated_support_cost": esc,
                "expected_value": ev,
                "efficiency_score": eff,
                "remaining_margin_estimate": rem_margin,
            }
        )

    return rows, None


def select_recommended_constrained(
    enriched_df: pd.DataFrame,
    expected_unit_margin: float,
    constraints: dict[str, Any],
) -> tuple[pd.Series, pd.DataFrame, bool]:
    """
    Rank feasible scenarios by net deal outcome (`expected_value`), apply tie-break.

    Returns (recommended_row, feasible_df, relaxed_constraints_fallback).

    Feasibility requires:
      - estimated_support_cost <= max_total_support_budget
      - expected_unit_margin - support_cost >= min_acceptable_remaining_margin
      - conversion_lift_vs_baseline >= min_conversion_lift_vs_no_support
        (full no-incentive baseline at the scenario loan term)

    Tie-break: among scenarios within 5% of feasible max net deal outcome, prefer lower support cost.
    """
    df = enriched_df.copy()
    m = float(expected_unit_margin)
    bud = float(constraints["max_total_support_budget"])
    min_rem = float(constraints["min_acceptable_remaining_margin"])
    min_lift = float(constraints["min_conversion_lift_vs_no_support"])
    if "conversion_lift_vs_baseline" not in df.columns and "conversion_lift_vs_no_support" in df.columns:
        df["conversion_lift_vs_baseline"] = df["conversion_lift_vs_no_support"].astype(float)
    if "remaining_margin_estimate" not in df.columns:
        df["remaining_margin_estimate"] = m - df["estimated_support_cost"].astype(float)

    feasible = df[
        (df["estimated_support_cost"].astype(float) <= bud + 1e-6)
        & (df["remaining_margin_estimate"].astype(float) >= min_rem - 1e-6)
        & (
            df["conversion_lift_vs_baseline"].astype(float)
            >= min_lift - 1e-9
        )
    ].copy()

    relaxed = feasible.empty
    if relaxed:
        chosen = select_recommended_expected_value(df)
        return chosen, feasible, True

    max_ev = float(feasible["expected_value"].max())
    pool = feasible[feasible["expected_value"] >= max_ev * 0.95].copy()
    if pool.empty:
        pool = feasible
    chosen = pool.sort_values(
        ["estimated_support_cost", "dealer_rate_support_level"],
        ascending=[True, True],
    ).iloc[0]
    return chosen, feasible, False


def run_constraint_based_offer_scenarios(
    base_inputs: dict[str, Any],
    optimization_constraints: dict[str, Any],
    pipeline: Any,
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
    cost_multiplier: float,
) -> tuple[pd.DataFrame | None, str | None, dict[str, Any] | None]:
    """
    Search configured lever grids. Either evaluates the **full** fine grid (<= MAX_FULL_ENUMERATION
    combinations) or runs a deterministic **coarse-to-fine** expansion — never random sampling.
    """
    t0 = time.perf_counter()
    fine_grids = _fine_optimization_grids(optimization_constraints)
    fine_combos = list(itertools.product(*fine_grids))
    n_fine = len(fine_combos)

    if n_fine <= MAX_FULL_ENUMERATION:
        rows, err = _score_offer_combination_list(
            base_inputs,
            fine_combos,
            pipeline,
            schema,
            sample_defaults,
            cost_multiplier,
            idx_offset=0,
        )
        if err or rows is None:
            return None, err or "Prediction failed in multi-lever sweep.", None
        df = pd.DataFrame(rows)
        elapsed = time.perf_counter() - t0
        meta: dict[str, Any] = {
            "search_mode": "Full grid search",
            "total_grid_scenarios": n_fine,
            "scenarios_evaluated": len(df),
            "runtime_seconds": elapsed,
            "coarse_evaluated": len(df),
            "refined_evaluated": 0,
            "coarse_grid_truncated": False,
        }
        return df, None, meta

    coarse_grids = _coarse_optimization_grids(optimization_constraints)
    coarse_combos = sorted(itertools.product(*coarse_grids))
    coarse_truncated = False
    if len(coarse_combos) > MAX_FULL_ENUMERATION:
        stride = math.ceil(len(coarse_combos) / MAX_FULL_ENUMERATION)
        coarse_combos = coarse_combos[::stride]
        coarse_truncated = True

    rows_c, err = _score_offer_combination_list(
        base_inputs,
        list(coarse_combos),
        pipeline,
        schema,
        sample_defaults,
        cost_multiplier,
        idx_offset=0,
    )
    if err or rows_c is None:
        return None, err or "Prediction failed in coarse optimization.", None

    df_c = pd.DataFrame(rows_c)
    top_n = min(25, len(df_c))
    top_block = df_c.nlargest(top_n, "expected_value")

    coarse_keys: set[tuple[Any, ...]] = {_series_to_combo_tuple(r) for _, r in df_c.iterrows()}

    refined_set: set[tuple[Any, ...]] = set()
    for _, row in top_block.iterrows():
        for tup in _refined_neighbor_tuples(row, optimization_constraints):
            if tup not in coarse_keys:
                refined_set.add(tup)

    refined_combos = sorted(refined_set)
    rows_r: list[dict[str, Any]] = []
    if refined_combos:
        rows_r, err_r = _score_offer_combination_list(
            base_inputs,
            refined_combos,
            pipeline,
            schema,
            sample_defaults,
            cost_multiplier,
            idx_offset=len(rows_c),
        )
        if err_r or rows_r is None:
            return None, err_r or "Prediction failed in refined optimization.", None

    all_rows = rows_c + rows_r
    for i, row in enumerate(all_rows):
        row["scenario_idx"] = i

    df = pd.DataFrame(all_rows)
    elapsed = time.perf_counter() - t0
    meta = {
        "search_mode": "Coarse-to-fine search",
        "total_grid_scenarios": n_fine,
        "scenarios_evaluated": len(df),
        "coarse_evaluated": len(rows_c),
        "refined_evaluated": len(rows_r),
        "coarse_grid_truncated": coarse_truncated,
        "runtime_seconds": elapsed,
    }
    return df, None, meta


def scenario_rows_match(rec: pd.Series, df: pd.DataFrame) -> pd.Series:
    """Boolean mask for the lever tuple identifying a scenario row."""
    keys = (
        "dealer_rate_support_level",
        "customer_cash",
        "dealer_cash",
        "loyalty_cash",
        "conquest_cash",
        "loan_term",
    )
    m = pd.Series(True, index=df.index)
    for k in keys:
        m &= df[k] == rec[k]
    return m


def select_recommended_expected_value(enriched_df: pd.DataFrame) -> pd.Series:
    """Highest expected value; tie-break among scenarios within 5% of max EV → lower support cost."""
    max_ev = float(enriched_df["expected_value"].max())
    pool = enriched_df[enriched_df["expected_value"] >= max_ev * 0.95].copy()
    if pool.empty:
        pool = enriched_df.copy()
    return pool.sort_values(
        ["estimated_support_cost", "dealer_rate_support_level"],
        ascending=[True, True],
    ).iloc[0]


def select_highest_conversion_scenario(enriched_df: pd.DataFrame) -> pd.Series:
    mx = float(enriched_df["conversion_probability"].max())
    ties = enriched_df[enriched_df["conversion_probability"] == mx]
    return ties.sort_values(
        ["estimated_support_cost", "dealer_rate_support_level"],
        ascending=[True, True],
    ).iloc[0]


def run_support_scenarios(
    base_inputs: dict[str, Any],
    pipeline: Any,
    schema: dict[str, Any],
    sample_defaults: dict[str, Any],
    scenario_levels: list[int],
) -> tuple[pd.DataFrame | None, str | None]:
    """Sweep dealer_rate_support_level; APR and payment from amortization on base loan amount."""
    base_std = float(base_inputs["standard_apr"])
    la0 = float(base_inputs["loan_amount"])
    term = int(base_inputs["loan_term"])

    rows: list[dict[str, Any]] = []
    for candidate in scenario_levels:
        scenario = copy.deepcopy(base_inputs)
        scenario["dealer_rate_support_level"] = float(candidate)
        subvented = max(0.5, base_std - float(candidate) / 100.0)
        scenario["dealer_apr"] = subvented
        scenario["dealer_monthly_payment"] = max(
            150.0,
            calculate_monthly_payment_if_needed(la0, subvented, term),
        )

        row_model = calculate_model_features(scenario)
        X, err, _, _ = align_to_schema(row_model, schema, sample_defaults)
        if err or X is None:
            return None, err or "Alignment failed."

        try:
            p = predict_conversion(pipeline, X)
        except Exception as e:
            return None, f"Prediction failed in simulation: {e}"

        rows.append(
            {
                "dealer_rate_support_level": int(candidate),
                "rate_support_tier": rate_support_tier_label(int(candidate)),
                "scenario_dealer_apr": float(row_model["dealer_apr"]),
                "scenario_dealer_monthly_payment": float(row_model["dealer_monthly_payment"]),
                "apr_gap_bps": float(row_model["apr_gap_bps"]),
                "conversion_probability": p,
            }
        )

    return pd.DataFrame(rows), None


def enrich_offer_simulator_metrics(
    sim_df: pd.DataFrame,
    base_inputs: dict[str, Any],
    cost_multiplier: float,
) -> pd.DataFrame:
    df = sim_df.sort_values("dealer_rate_support_level").reset_index(drop=True)
    cm = float(cost_multiplier)

    df["estimated_support_cost"] = df["dealer_rate_support_level"].apply(
        lambda x: estimate_support_cost(base_inputs, float(x), cm)
    )

    p0_series = df.loc[df["dealer_rate_support_level"] == 0, "conversion_probability"]
    if p0_series.empty:
        p0 = float(df["conversion_probability"].iloc[0])
    else:
        p0 = float(p0_series.iloc[0])

    df["conversion_lift_vs_no_support"] = df["conversion_probability"].astype(float) - p0

    inc_gains: list[float] = []
    inc_costs: list[float] = []
    for i in range(len(df)):
        if i == 0:
            inc_gains.append(float("nan"))
            inc_costs.append(float("nan"))
        else:
            inc_gains.append(
                float(df.loc[i, "conversion_probability"])
                - float(df.loc[i - 1, "conversion_probability"])
            )
            inc_costs.append(
                float(df.loc[i, "estimated_support_cost"])
                - float(df.loc[i - 1, "estimated_support_cost"])
            )

    df["incremental_conversion_gain"] = inc_gains
    df["incremental_support_cost"] = inc_costs

    lift = df["conversion_lift_vs_no_support"].astype(float)
    esc = df["estimated_support_cost"].astype(float)
    df["support_cost_per_conversion_point"] = esc / np.maximum(lift * 100.0, 0.01)
    df["efficient_offer_score"] = (lift * 100.0) / np.maximum(esc / 1000.0, 0.01)

    return df


def select_preferred_max_conversion_min_support(enriched_df: pd.DataFrame) -> pd.Series:
    """Highest predicted conversion; ties broken by lowest support level."""
    d = enriched_df.sort_values(
        "dealer_rate_support_level", ascending=True
    ).reset_index(drop=True)
    mx = float(d["conversion_probability"].max())
    ties = d[d["conversion_probability"] == mx]
    return ties.iloc[0]


def select_recommended_efficient_scenario(enriched_df: pd.DataFrame) -> pd.Series:
    """
    Lowest-cost efficient scenario per stakeholder rules (lift thresholds + efficiency score).
    """
    d = enriched_df.sort_values("dealer_rate_support_level").reset_index(drop=True)
    lift = d["conversion_lift_vs_no_support"]
    pool = d.copy() if (lift < 0.02).all() else d[lift >= 0.02].copy()
    if pool.empty:
        pool = d.copy()

    mask_keep = np.ones(len(pool), dtype=bool)
    for i in range(len(pool)):
        ig = pool["incremental_conversion_gain"].iloc[i]
        isc = pool["incremental_support_cost"].iloc[i]
        if pd.notna(ig) and pd.notna(isc):
            if float(ig) < 0.005 and float(isc) > 0:
                mask_keep[i] = False
    pool = pool.loc[mask_keep].copy()
    if pool.empty:
        pool = d.copy()

    best = float(pool["efficient_offer_score"].max())
    near_best = pool[pool["efficient_offer_score"] >= best * 0.95]
    return near_best.sort_values(
        ["estimated_support_cost", "dealer_rate_support_level"],
        ascending=[True, True],
    ).iloc[0]


def select_lowest_cost_scenario(enriched_df: pd.DataFrame) -> pd.Series:
    idx = enriched_df["estimated_support_cost"].idxmin()
    return enriched_df.loc[idx]


def likelihood_band(p: float) -> str:
    if p < 0.35:
        return "Low"
    if p <= 0.65:
        return "Moderate"
    return "High"


def competitive_position_detail(apr_gap_bps: float) -> tuple[str, str]:
    """
    Returns (short headline, plain-language explanation).
    Thresholds match internal APR comparison scale (not shown to users).
    """
    if apr_gap_bps < -50:
        return ("Dealer Advantage", "Dealer offer is meaningfully better")
    if apr_gap_bps <= 50:
        return ("Neutral Position", "Offers are roughly comparable")
    return ("Competitor Advantage", "Competing offer appears stronger")


# Sidebar wizard: one section visible at a time; widget keys persist across steps.
SIDEBAR_SECTION_LABELS: dict[str, str] = {
    "customer": "1 · Customer Profile",
    "vehicle": "2 · Vehicle / Product",
    "dealer_inv": "3 · Dealer & Inventory",
    "financing": "4 · Optimization Constraints",
    "competitor": "5 · Competitor Offer",
    "macro": "6 · Rates, Timing & Geography",
}

SIDEBAR_SECTION_ORDER: tuple[str, ...] = (
    "customer",
    "vehicle",
    "dealer_inv",
    "financing",
    "competitor",
    "macro",
)

# Wizard / executive UI display titles (Step N label)
WIZARD_STEP_TITLE: dict[str, str] = {
    "customer": "Customer Profile",
    "vehicle": "Vehicle & Product",
    "dealer_inv": "Dealer & Inventory",
    "financing": "Optimization Constraints",
    "competitor": "Competitor & Market",
    "macro": "Financial Market Conditions",
}

# What scores 1, 5, and 10 mean for each 1–10 slider (wizard + sidebar captions).
SLIDER_SCALE_ANCHORS: dict[str, tuple[str, str, str]] = {
    "sb_price_sensitivity_ui": (
        "Barely notices APR, payment, or rebate differences.",
        "Balanced — compares offers when the price gap is meaningful.",
        "Extremely sensitive — tiny pricing gaps can win or lose the deal.",
    ),
    "sb_purchase_urgency_ui": (
        "Casually browsing; no near-term purchase timeline.",
        "Planning to buy within a few months if terms feel fair.",
        "Must purchase now (replacement, lease end, or urgent need).",
    ),
    "sb_brand_preference_ui": (
        "No loyalty — open to any make or dealer.",
        "Mild preference — could switch brands for the right deal.",
        "Extremely loyal — unlikely to consider alternatives.",
    ),
    "sb_purchase_intent_ui": (
        "Very low intent / tire-kicker.",
        "Moderate — interested but not committed to this store or unit.",
        "Ready to sign today if terms are acceptable.",
    ),
    "sb_sentiment_ui": (
        "Very negative toward the offer, vehicle, or dealer experience.",
        "Neutral or mixed feelings about the shopping experience.",
        "Extremely positive — enthusiastic advocate for moving forward.",
    ),
    "sb_ev_affinity_ui": (
        "No interest in electric or plug-in vehicles.",
        "Open to EV if range, price, and charging realistically work.",
        "Wants an EV — strongly prefers plug-in or battery electric.",
    ),
    "sb_family_utility_ui": (
        "Minimal passenger or cargo needs (solo or couples).",
        "Typical household needs — school runs, errands, occasional hauling.",
        "Must maximize family utility (third row, space, versatility).",
    ),
    "sb_truck_affinity_ui": (
        "No interest in pickup trucks.",
        "Would consider a truck if capability and deal align.",
        "Truck-first shopper — wants pickups when the mission fits.",
    ),
    "sb_conquest_likelihood_ui": (
        "Likely captive / repeat buyer to the shopper’s current brand.",
        "Could be swayed by a competitive offer if execution is sharp.",
        "Actively cross-shopping rivals — prime conquest opportunity.",
    ),
    "sb_rv_strength_ui": (
        "Weak expected resale or residual versus segment peers.",
        "Average residual expectations for this segment.",
        "Top-tier residual strength — class-leading resale outlook.",
    ),
    "sb_inventory_pressure_ui": (
        "Little urgency to retail this unit or cohort.",
        "Normal stocking discipline — routine turn expectations.",
        "Critical — heavy pressure to move metal immediately.",
    ),
    "sb_competitor_aggr_ui": (
        "Competing offer feels weak or easy to beat.",
        "Moderately competitive — typical for your market.",
        "Extremely aggressive — hard to match without deeper support.",
    ),
    "sb_competitor_sales_ui": (
        "Competitor looks weak or quiet in your trading area.",
        "Average competitive footprint and showroom traffic.",
        "Dominant momentum — perceived market leader locally.",
    ),
}

# Low / mid / high end of each continuous slider (wizard + sidebar captions).
SLIDER_RANGE_ANCHORS: dict[str, tuple[str, str, str]] = {
    "sb_fico_score": (
        "Deep subprime / thin file — financing is difficult or expensive.",
        "Near-prime to prime — typical approval band for standard programs.",
        "Excellent credit — best-tier pricing and captive approval odds.",
    ),
    "sb_monthly_income": (
        "Modest household income — tight payment-to-income headroom.",
        "Middle income — common retail auto buyer band.",
        "High income — ample capacity; less payment stress on the deal.",
    ),
    "sb_monthly_debt_payments": (
        "Minimal reported obligations — debt load is light versus income.",
        "Typical debt stack — cards, rent, and loans near an average mix.",
        "Heavy monthly obligations — affordability and stip risk rise.",
    ),
    "sb_model_year": (
        "Older model year — heavier depreciation; watch CPO vs new overlap.",
        "Mid-cycle year — mainstream inventory age for the quote.",
        "Current or future model year — newest sheet metal and tech content.",
    ),
    "sb_vehicle_price": (
        "Budget transaction — economy or high-incentive vehicle band.",
        "Typical new- or used-retail ticket for mass-market units.",
        "Premium ticket — luxury, large SUV, or loaded configuration.",
    ),
    "sb_vehicle_age": (
        "New or uncredited age — virgin MSRP-style economics.",
        "Young used — mild depreciation versus new.",
        "Aged used — resale and warranty optics dominate the story.",
    ),
    "sb_residual_support_pct_display": (
        "No/low residual subsidy — OEM cash goes elsewhere.",
        "Typical captive lift — noticeable lease/FI sweetener.",
        "Aggressive subsidized residual — artificially strong lease payments.",
    ),
    "sb_avg_monthly_retail_units": (
        "Small rooftop throughput — boutique or rural pace.",
        "Average monthly retail cadence — healthy single-point store.",
        "High-velocity store — volume leader; scale can absorb support.",
    ),
    "sb_dealer_margin_pct_display": (
        "Thin front-end margin — little room before pack and reserve.",
        "Average front gross as a percent of revenue.",
        "Strong front margin — more internal room to fund the deal.",
    ),
    "sb_expected_unit_margin": (
        "Low dollars per car — minis or heavy discounting.",
        "Typical expected unit gross before F&I.",
        "High per-unit margin — premium mix or strong local pricing.",
    ),
    "sb_days_in_inventory": (
        "Fresh stock — first-turn units; little carrying cost pressure.",
        "Normal days supply — standard turn expectations.",
        "Stale inventory — aged unit; discount and support pressure build.",
    ),
    "sb_on_hand_units": (
        "Tight ground stock — risk of missed sales on hot trims.",
        "Balanced on-hand count for this model line.",
        "Deep ground stock — capital tied up; room to deal.",
    ),
    "sb_in_transit_units": (
        "No inbound pipeline — allocation visibility is limited.",
        "Moderate pipeline — incoming units cover near-term demand.",
        "Heavy in-transit wave — future supply relieves stockout risk.",
    ),
    "sb_aging_inventory_pct_display": (
        "Fresh mix — most units under your aging threshold.",
        "Average aged mix — some units need retail focus.",
        "High aged share — fire-sale risk; support may be needed to move metal.",
    ),
    "sb_loan_amount": (
        "Small finance balance — entry price or large down payment.",
        "Typical amount financed for this segment.",
        "Large balance — payment and rate sensitivity magnify.",
    ),
    "sb_down_payment": (
        "Little or no cash down — high LTV; lender scrutiny rises.",
        "Average customer cash in — balanced structure.",
        "Large cash in — lower LTV; stronger lender story.",
    ),
    "sb_standard_apr": (
        "Very low retail APR environment — cheap money era.",
        "Mid-market retail APR before buy-downs.",
        "High retail APR — subprime lane or stressed credit macro.",
    ),
    "sb_dealer_apr": (
        "Low customer rate after programs — easy payment story.",
        "Typical posted APR after stackable support.",
        "High customer APR — less rate subsidy layered in.",
    ),
    "sb_dealer_monthly_payment": (
        "Low payment — small balance, long term, or deep buy rate.",
        "Typical payment for this vehicle and term band.",
        "High payment — short term, light down, or rate pressure.",
    ),
    "sb_customer_cash": (
        "No manufacturer or dealer cash to the customer.",
        "Typical rebate / bonus cash visible on the buyer’s worksheet.",
        "Large customer cash stack — dominates the headline offer.",
    ),
    "sb_dealer_cash": (
        "No discretionary dealer contribution on paper.",
        "Moderate dealer cash from the rooftop.",
        "Heavy dealer cash — priced to win a shopping war.",
    ),
    "sb_loyalty_cash": (
        "No OEM loyalty concession.",
        "Standard loyalty bounty for retained owners.",
        "Aggressive loyalty offer — captive retention push.",
    ),
    "sb_conquest_cash": (
        "No conquest dollars — shopper must switch without bounty.",
        "Typical switch-in incentive from the OEM.",
        "Large conquest check — engineered to steal a rival owner.",
    ),
    "sb_competitor_apr": (
        "Competitor’s rate looks cheap — pricing pressure.",
        "Typical APR on the rival quote.",
        "Competitor is expensive — easier to beat on finance charges.",
    ),
    "sb_competitor_monthly_payment": (
        "Competing payment is attractive — shopper may anchor here.",
        "Average competitive payment expectation.",
        "Rival payment is high — leverage for your counter-offer.",
    ),
    "sb_competitor_cashback": (
        "Little or no cash on competing store’s banner.",
        "Typical rebates on the competitor’s sheet.",
        "Massive competitor cash — they are buying share.",
    ),
    "sb_fed_rate": (
        "Accommodative policy rates — favorable funding backdrop.",
        "Neutral monetary stance for this macro snapshot.",
        "Restrictive short rates — captive and bank costs rise.",
    ),
    "sb_ten_year": (
        "Low long yields — reflating risk premiums favor credit.",
        "Average long-rate environment for budgeting curves.",
        "Elevated Treasury yields — auto finance benchmarks drift up.",
    ),
    "sb_inflation_cpi": (
        "Low inflation regime — muted vehicle price escalation.",
        "Moderate CPI — steady input cost creep.",
        "High inflation narrative — rebates and sticker gap widen.",
    ),
    "sb_base_auto_rate_index": (
        "Low internal auto benchmark — cheap wholesale money.",
        "Typical captive/bank baseline for standard tiers.",
        "High baseline index — tougher standard rates before support.",
    ),
    "sb_market_rate_index": (
        "Market rates sit below normal — shopper sees cheap loans.",
        "Average observed retailer APR index.",
        "Market rates spike — shopper expects expensive paper.",
    ),
    "sb_cost_multiplier": (
        "Low modeled cost curve — optimizes aggressively on support ROI.",
        "Baseline calibration for support dollar costing.",
        "High modeled cost — each bps bite is expensive to the rooftop.",
    ),
}


# Rich dropdown labels — canonical stored value unchanged in session_state.
MAKE_OPTION_LABELS: dict[str, str] = {
    "Toyota": "Toyota — mass-market reliability; strong retained value.",
    "Honda": "Honda — retail efficiency; commuter and family mix.",
    "Ford": "Ford — truck-heavy; Blue Oval conquest battles common.",
    "Chevrolet": "Chevrolet — full-line domestics; fleet and retail blends.",
    "Hyundai": "Hyundai — value-led; long warranty optics.",
    "Kia": "Kia — design-led value SUV mix; youthful demo.",
    "Nissan": "Nissan — payment-driven marketing; Rogue/Altima core.",
    "Jeep": "Jeep — lifestyle SUV/truck ethos; rugged positioning.",
    "BMW": "BMW — sports-luxury; captive finance nuances.",
    "Mercedes": "Mercedes — premium executive; disciplined pricing.",
    "Tesla": "Tesla — EV-first digital purchase journey.",
}


def format_make_option(make: str) -> str:
    return MAKE_OPTION_LABELS.get(make, make)


def format_model_option(model: str) -> str:
    mk = str(st.session_state.get("sb_make") or "")
    return (
        f"{model} — {mk} showroom nameplate; pick the unit closest to inventory."
        if mk
        else f"{model} — pick the closest unit on lot."
    )


TRIM_OPTION_LABELS: dict[str, str] = {
    "Base": "Base — essentials; lowest content and sticker.",
    "Sport": "Sport — appearance or handling trim without full luxury.",
    "Premium": "Premium — added comfort and tech over mainstream.",
    "Limited": "Limited — high-content; near flagship features.",
    "Touring": "Touring — road-trip comfort and driver assists.",
    "Platinum": "Platinum — top-line equipment and materials.",
}


def format_trim_option(trim: str) -> str:
    return TRIM_OPTION_LABELS.get(trim, trim)


BODY_STYLE_OPTION_LABELS: dict[str, str] = {
    "Sedan": "Sedan — three-box passenger car; commuter efficiency.",
    "SUV": "SUV — high ride height and flexible cargo bay.",
    "Truck": "Truck — open bed capability; towing mission.",
    "Coupe": "Coupe — two-door sporty silhouette.",
    "Hatchback": "Hatchback — liftgate cargo access; urban friendly.",
    "Crossover": "Crossover — unibody SUV manners; everyday utility.",
}


def format_body_style_option(style: str) -> str:
    return BODY_STYLE_OPTION_LABELS.get(style, style)


FUEL_TYPE_OPTION_LABELS: dict[str, str] = {
    "Gasoline": "Gasoline — conventional ICE retail and lender norms.",
    "Hybrid": "Hybrid — blended mpg story; bridging to full EV.",
    "Plug-in Hybrid": "Plug-in hybrid — recharge + gas backup; nuanced lease math.",
    "Diesel": "Diesel — torque and hauling; narrower retail band.",
    "EV": "EV — electrons only; rebates and charging caveats.",
}


def format_fuel_type_option(fuel: str) -> str:
    return FUEL_TYPE_OPTION_LABELS.get(fuel, fuel)


VEHICLE_SEGMENT_OPTION_LABELS: dict[str, str] = {
    "Economy": "Economy — entry payments; rebate wars common.",
    "Compact SUV": "Compact SUV — hottest retail cross-shopping bucket.",
    "Midsize SUV": "Midsize SUV — family default; content arms race.",
    "Luxury": "Luxury — premium features; tighter discount discipline.",
    "Truck": "Truck — pickup mission; high ticket and conquest drama.",
    "Sedan": "Sedan — car alternative to SUV; payment sensitive.",
    "EV": "EV — electric segment lens; incentives and range anxiety.",
}


def format_vehicle_segment_option(seg: str) -> str:
    return VEHICLE_SEGMENT_OPTION_LABELS.get(seg, seg)


DEALER_SIZE_OPTION_LABELS: dict[str, str] = {
    "Small": "Small — limited capacity; every deal matters.",
    "Medium": "Medium — typical single-point throughput.",
    "Large": "Large — volume store; more fixed-cost absorption.",
    "Mega": "Mega — auto-mall scale; pricing power and throughput.",
}


def format_dealer_size_option(tier: str) -> str:
    return DEALER_SIZE_OPTION_LABELS.get(tier, tier)


SALES_TYPE_OPTION_LABELS: dict[str, str] = {
    "Retail": "Retail — standard showroom delivery and registration path.",
    "Lease": "Lease — mileage, RV, and captive lease programs dominate.",
    "Finance": "Finance — retail installment emphasis on the worksheet.",
    "Cash": "Cash — one-pay or external financing; no captive APR story.",
}


def format_sales_type_option(stp: str) -> str:
    return SALES_TYPE_OPTION_LABELS.get(stp, stp)


REGION_OPTION_LABELS: dict[str, str] = {
    "Northeast": "Northeast — snow belt; AWD mix and salt-belt resale.",
    "Southeast": "Southeast — Sun Belt growth; truck and SUV heavy.",
    "Midwest": "Midwest — domestic share; pragmatic payment buyers.",
    "Southwest": "Southwest — truck/SUV mix; long driving distances.",
    "West": "West — coastal EV/reg compliance; eclectic mix imports.",
}


def format_region_option(reg: str) -> str:
    return REGION_OPTION_LABELS.get(reg, reg)


STATE_OPTION_LABELS: dict[str, str] = {
    "TX": "TX — large-volume Sun Belt registrations.",
    "CA": "CA — ZEV/regulatory overlays; affluent coastal metros.",
    "FL": "FL — transplant demand; retirees and hurricanes affect mix.",
    "NY": "NY — urban density plus upstate commuter patterns.",
    "NJ": "NJ — tri-state commuter; captive-heavy luxury pockets.",
    "IL": "IL — Chicago hub; sedan/SUV commuter blend.",
    "AZ": "AZ — Sun Belt growth; truck-heavy mix.",
    "WA": "WA — tech wages; hybrid/EV openness.",
    "GA": "GA — Southeast logistics hub; diverse imports.",
    "NC": "NC — banking/auto manufacturing adjacency.",
}


def format_state_option(st: str) -> str:
    return STATE_OPTION_LABELS.get(st, st)


LOAN_TERM_OPTION_LABELS: dict[int, str] = {
    36: "36 mo — short term; higher payment, less interest paid.",
    48: "48 mo — balanced note; still common for used.",
    60: "60 mo — mainstream new-car retail term.",
    72: "72 mo — stretch payment; watch negative equity risk.",
    84: "84 mo — maximum stretch; rate and LTV sensitive.",
}


def format_loan_term_option(months: int) -> str:
    return LOAN_TERM_OPTION_LABELS.get(int(months), f"{int(months)} mo — custom term.")


PRIMARY_COMPETITOR_LABELS: dict[str, str] = {
    "Toyota": "Toyota — benchmark Japanese reliability rival.",
    "Honda": "Honda — retail efficiency and family cross-shop.",
    "Ford": "Ford — truck and SUV conquest pressure.",
    "Chevrolet": "Chevrolet — domestic full-line alternative.",
    "Hyundai": "Hyundai — value warranty story vs your unit.",
    "Kia": "Kia — design-led value SUV rival.",
    "Nissan": "Nissan — payment-leader cross-shop.",
    "Tesla": "Tesla — EV-first digital benchmark.",
    "BMW": "BMW — sports-luxury lease/finance rival.",
}


def format_primary_competitor_option(brand: str) -> str:
    return PRIMARY_COMPETITOR_LABELS.get(brand, f"{brand} — primary bench rival on this deal.")


YES_NO_OPTION_LABELS: dict[str, dict[str, str]] = {
    "sb_rv_push_yn": {
        "Yes": "Yes — OEM residual push program is active for this brand line.",
        "No": "No — no special residual push; book rates only.",
    },
    "sb_metro_yn": {
        "Yes": "Yes — metro / high-density market; traffic and digital leads differ.",
        "No": "No — non-metro or smaller DMA shopping patterns.",
    },
    "sb_stockout_yn": {
        "Yes": "Yes — risk of selling out hot trims; demand > supply.",
        "No": "No — stock position covers near-term demand.",
    },
    "sb_overstock_yn": {
        "Yes": "Yes — inventory heavy vs sell-through; deal sweeteners likely.",
        "No": "No — stocking level is balanced with demand.",
    },
    "sb_promotion_yn": {
        "Yes": "Yes — time-bound promo or stair-step is in play.",
        "No": "No — no special promotion window on this quote.",
    },
    "sb_quarter_end_yn": {
        "Yes": "Yes — quarter-end lift or stair-step pressure is elevated.",
        "No": "No — normal month cadence without quarter-end spike.",
    },
}


def format_yes_no_option(state_key: str, yn: str) -> str:
    row = YES_NO_OPTION_LABELS.get(state_key)
    if not row:
        return yn
    return row.get(yn, yn)


def format_quote_month_option(m: int) -> str:
    name = MONTH_LABELS[int(m) - 1]
    return f"{name} — seasonality, weather, and holiday traffic context for the quote."


def format_dow_option(i: int) -> str:
    name = DOW_LABELS[int(i)]
    return f"{name} — intra-week showroom traffic and closing cadence."


def format_dealer_rate_support_bps(bps: int | float) -> str:
    """
    Compact tick labels for select_slider (format_func is applied to every mark).
    Tier names are omitted so endpoints are not repeated; semantics stay in the field help.
    """
    return f"{int(bps)} bps"


def EXEC_WIZARD_DEMO_UI_CSS() -> str:
    """Executive wizard: centered layout, slate accents, no sidebar (pre-submit only)."""
    return """
<style>
    section[data-testid="stSidebar"] { display: none !important; }
    /* Do not hide collapsedControl: Streamlit puts the widget help (?) there when
       label_visibility="collapsed". Hiding it removes every native tooltip in the wizard. */

    .stMainBlockContainer { background: #F7F8FA !important; padding-top: 0.5rem !important; }
    .main .block-container {
        max-width: 1180px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 0.25rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
    }
    [data-testid="stHeader"] { background: #F7F8FA !important; border-bottom: 1px solid #E5E7EB !important; }
    [data-testid="stDecoration"] { display: none !important; }

    /* Page title — centered above wizard card, same max-width as content */
    .demo-hero {
        box-sizing: border-box !important;
        max-width: 1180px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        margin-bottom: 1.25rem !important;
        padding: 0.35rem 1rem 1rem 1rem !important;
        text-align: center !important;
    }
    .demo-hero-title {
        display: block !important;
        color: #111827 !important;
        font-size: clamp(1.5rem, 3.5vw, 2rem) !important;
        font-weight: 700 !important;
        letter-spacing: -0.035em !important;
        line-height: 1.15 !important;
        margin: 0 auto 0.5rem auto !important;
        padding: 0 !important;
        text-align: center !important;
        max-width: 56rem !important;
    }
    .demo-hero-sub {
        display: block !important;
        color: #6B7280 !important;
        font-size: 1rem !important;
        font-weight: 400 !important;
        margin: 0 auto !important;
        padding: 0 !important;
        line-height: 1.5 !important;
        text-align: center !important;
        max-width: 40rem !important;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 14px !important;
        box-shadow: 0 1px 2px rgba(17, 24, 39, 0.04) !important;
        padding: 0.65rem 0.85rem 0.75rem 0.85rem !important;
        margin-bottom: 0.65rem !important;
    }

    /* Scroll-to-top targets this wrapper (long steps keep the step header in view). */
    .wizard-step-scroll-target {
        scroll-margin-top: 4.5rem;
    }
    .demo-step-meta {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #6B7280;
        margin: 0 0 0.35rem 0;
    }
    .demo-step-title {
        color: #111827;
        font-size: 1.35rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0 0 1rem 0;
        line-height: 1.25;
    }

    .demo-section-title {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #9CA3AF;
        margin: 1.25rem 0 0.65rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid #F3F4F6;
    }

    .demo-field-label {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.35rem;
        font-size: 0.8125rem;
        font-weight: 600;
        color: #111827;
        margin: 0 0 0.35rem 0;
        line-height: 1.3;
    }
    .demo-field-hint {
        font-size: 0.78rem !important;
        color: #6B7280 !important;
        margin: 0.1rem 0 0.45rem 0 !important;
        line-height: 1.35 !important;
    }

    .demo-metric-pill {
        background: #F3F4F6;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 0.75rem 1rem;
        margin-top: 0.25rem;
    }
    .demo-metric-pill-label {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.35rem;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #6B7280;
        margin-bottom: 0.25rem;
    }
    .demo-metric-pill-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #111827;
        letter-spacing: -0.02em;
    }
    .demo-metric-pill-help {
        font-size: 0.78rem;
        color: #6B7280;
        margin: 0.5rem 0 0 0;
        line-height: 1.35;
    }

    .demo-nav-row { margin-top: 0.5rem; padding-top: 1rem; border-top: 1px solid #F3F4F6; align-items: center; }

    button[kind="primary"] {
        background-color: #334155 !important;
        border-color: #334155 !important;
        color: #ffffff !important;
    }
    button[kind="primary"]:hover {
        background-color: #1e293b !important;
        border-color: #1e293b !important;
    }

    .main .stSlider [data-baseweb="slider"] { margin-top: 0; margin-bottom: 0; }
    .main .stSlider [data-testid="stThumbValue"] { font-size: 0.8rem; color: #374151; }
    /* Slider row: less vertical padding around the widget block */
    .main [data-testid="column"] div[data-testid="stVerticalBlock"] > div[data-testid="element-container"]:has(.stSlider) {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    .main [data-testid="column"] div[data-testid="stVerticalBlock"] > div[data-testid="element-container"]:has(.stTextInput) {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }

    /*
     * Slider + exact-value row ([4,1] columns): no bordered wrappers; border only on the input.
     * Scoped to rows with slider in column 1 + text input in column 2 (main + sidebar).
     */
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:first-child [data-testid="element-container"],
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:nth-child(2) [data-testid="element-container"] {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:first-child [data-testid="stVerticalBlock"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:nth-child(2) [data-testid="stTextInput"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="column"]:first-child .stSlider):has([data-testid="column"]:nth-child(2) [data-testid="stTextInput"]) [data-testid="column"]:nth-child(2) [data-testid="stTextInput"] input {
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
        background: #FFFFFF !important;
        padding: 0.4rem 0.55rem !important;
        box-shadow: none !important;
    }

    .exec-slider-hint {
        font-size: 0.78rem !important;
        color: #6B7280 !important;
        margin: 0.15rem 0 0.75rem 0 !important;
        line-height: 1.35 !important;
    }

    /*
     * Equal-height bordered cards in two-column rows (Customer Profile, etc.): stretch the
     * shorter card to match the taller peer. Scoped to rows that contain bordered wrappers
     * and never to the footer row (:not(:has([data-testid="stButton"]))).
     */
    .main div[data-testid="stHorizontalBlock"]:not(:has([data-testid="stButton"])):has([data-testid="column"] [data-testid="stVerticalBlockBorderWrapper"]) {
        align-items: stretch !important;
    }
    .main div[data-testid="stHorizontalBlock"]:not(:has([data-testid="stButton"])) [data-testid="column"]:has([data-testid="stVerticalBlockBorderWrapper"]) {
        display: flex !important;
        flex-direction: column !important;
        align-items: stretch !important;
        align-self: stretch !important;
    }
    .main div[data-testid="stHorizontalBlock"]:not(:has([data-testid="stButton"])) [data-testid="column"]:has([data-testid="stVerticalBlockBorderWrapper"]) > div[data-testid="element-container"] {
        flex: 1 1 auto !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0 !important;
    }
    .main div[data-testid="stHorizontalBlock"]:not(:has([data-testid="stButton"])) [data-testid="column"]:has([data-testid="stVerticalBlockBorderWrapper"]) [data-testid="stVerticalBlockBorderWrapper"] {
        flex: 1 1 auto !important;
        min-height: 0 !important;
        height: 100% !important;
        box-sizing: border-box !important;
    }

    /*
     * Wizard footer ONLY (Back / Next): must NOT use :has(button) — selectboxes, sliders,
     * and other widgets embed native <button> inside column rows, so that matched Vehicle &
     * Product and broke the grid. Streamlit wraps st.button in [data-testid="stButton"].
     */
    .main div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) {
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        gap: 0 !important;
        padding: 0.75rem 0 0 0 !important;
        margin: 0 !important;
        background: transparent !important;
    }
    .main div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) [data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        border-width: 0 !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        background: transparent !important;
        min-height: 0 !important;
        height: auto !important;
    }
    .main div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) [data-testid="column"] {
        border: none !important;
        background: transparent !important;
    }
    .main div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) [data-testid="stVerticalBlock"] {
        gap: 0 !important;
        padding: 0 !important;
        background: transparent !important;
    }

    /*
     * Offer analytics chart pair + popovers: the footer-row rule above matches any row with
     * [data-testid="stButton"] (includes ? popovers), forcing align-items:center and stripping
     * borders from bordered containers — cards stay different heights and tops drift. Anchor wins.
     */
    .main div[data-testid="stHorizontalBlock"]:has(.exec-chart-pair-anchor) {
        align-items: stretch !important;
        align-content: stretch !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    .main div[data-testid="stHorizontalBlock"]:has(.exec-chart-pair-anchor) [data-testid="column"] {
        display: flex !important;
        flex-direction: column !important;
        align-items: stretch !important;
        align-self: stretch !important;
    }
    .main div[data-testid="stHorizontalBlock"]:has(.exec-chart-pair-anchor)
        [data-testid="column"]:has([data-testid="stVerticalBlockBorderWrapper"]) > div[data-testid="element-container"] {
        flex: 1 1 auto !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0 !important;
    }
    .main div[data-testid="stHorizontalBlock"]:has(.exec-chart-pair-anchor)
        [data-testid="stVerticalBlockBorderWrapper"] {
        flex: 1 1 auto !important;
        min-height: 0 !important;
        height: 100% !important;
        box-sizing: border-box !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 14px !important;
        box-shadow: 0 1px 2px rgba(17, 24, 39, 0.04) !important;
        padding: 0.65rem 0.85rem 0.75rem 0.85rem !important;
        margin-bottom: 0.65rem !important;
        background: #FFFFFF !important;
    }
</style>
"""


def init_session_state() -> None:
    """Wizard / analysis flags and one-time migration from legacy session keys."""
    if "current_step" not in st.session_state:
        st.session_state.current_step = 0
    if "analysis_submitted" not in st.session_state:
        st.session_state.analysis_submitted = False
    if "_ui_migrated_v2" not in st.session_state:
        if "quote_submitted" in st.session_state:
            st.session_state.analysis_submitted = bool(
                st.session_state.quote_submitted
            )
        if "sidebar_wizard_step" in st.session_state:
            st.session_state.current_step = int(
                st.session_state.sidebar_wizard_step
            )
        st.session_state._ui_migrated_v2 = True
    st.session_state.current_step = max(
        0,
        min(int(st.session_state.current_step), len(SIDEBAR_SECTION_ORDER) - 1),
    )
    if "edit_panel_section" not in st.session_state:
        st.session_state.edit_panel_section = SIDEBAR_SECTION_ORDER[0]
    if "analysis_compute_requested" not in st.session_state:
        st.session_state.analysis_compute_requested = False


def _slider_scale_anchor_html(state_key: str, *, css_class: str) -> str | None:
    triple = SLIDER_SCALE_ANCHORS.get(state_key)
    if not triple:
        return None
    a1, a5, a10 = triple
    return (
        f'<p class="{html.escape(css_class)}">'
        f'<strong>1</strong> — {html.escape(a1)}<br/>'
        f'<strong>5</strong> — {html.escape(a5)}<br/>'
        f'<strong>10</strong> — {html.escape(a10)}'
        "</p>"
    )


def _slider_scale_caption(state_key: str, *, wizard: bool = False) -> None:
    if not wizard:
        return
    css = "demo-field-hint" if wizard else "exec-slider-hint"
    block = _slider_scale_anchor_html(state_key, css_class=css)
    if block:
        st.markdown(block, unsafe_allow_html=True)


def _slider_range_anchor_html(state_key: str, *, css_class: str) -> str | None:
    triple = SLIDER_RANGE_ANCHORS.get(state_key)
    if not triple:
        return None
    lo, mid, hi = triple
    return (
        f'<p class="{html.escape(css_class)}">'
        f'<strong>Low</strong> — {html.escape(lo)}<br/>'
        f'<strong>Mid</strong> — {html.escape(mid)}<br/>'
        f'<strong>High</strong> — {html.escape(hi)}'
        "</p>"
    )


def _slider_range_caption(state_key: str, *, wizard: bool = False) -> None:
    if not wizard:
        return
    css = "demo-field-hint" if wizard else "exec-slider-hint"
    block = _slider_range_anchor_html(state_key, css_class=css)
    if block:
        st.markdown(block, unsafe_allow_html=True)


def _two_cols(wizard: bool):
    """Two columns in the wizard; edit panel uses one full-width vertical stack."""
    if wizard:
        try:
            return st.columns(2, gap="small")
        except TypeError:
            return st.columns(2)
        except Exception as e:
            if type(e).__name__ == "StreamlitAPIException" or "gap" in str(e).lower():
                return st.columns(2)
            raise
    stack = st.sidebar.container()
    return stack, stack


def _inline_md_bold_to_html(text: str) -> str:
    """Allow ``**bold**`` in short UI strings embedded in HTML `<p>` (escape everything else)."""
    if not text:
        return ""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(html.escape(part))
        else:
            out.append(f"<strong>{html.escape(part)}</strong>")
    return "".join(out)


def _help_plain_for_tooltip(
    help_md: str, *, max_len: int | None = 420
) -> str:
    """Light markdown → plain text for hover copy (native title is unreliable in Streamlit HTML)."""
    s = help_md or ""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[(.+?)\]\([^)]+\)", r"\1", s)
    s = s.replace("\n\n", " · ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if max_len is not None and len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _hint(help_md: str) -> str:
    """Shorthand for inline HTML ? chip + hover popup (same as `_help_icon_html`)."""
    return _help_icon_html(help_md)


def _hero_metric_label(label: str, help_md: str) -> str:
    """Uppercase-style hero tile title + ? explanation."""
    return (
        f'<p class="ehm-label" style="display:flex;align-items:center;gap:0.3rem;flex-wrap:wrap;'
        f'margin:0 0 0.25rem 0;">'
        f"{html.escape(label)}{_hint(help_md)}</p>"
    )


def _comparison_metric_row(label: str, value_html: str, help_md: str) -> str:
    """One row in scenario comparison cards: label + ? , value."""
    return (
        f'<div class="esc-row">'
        f'<span class="esc-k" style="display:flex;align-items:center;gap:0.28rem;flex-wrap:wrap;">'
        f"{html.escape(label)}{_hint(help_md)}</span>"
        f'<span class="esc-v">{value_html}</span></div>'
    )


def _labeled_hint(label: str, help_md: str) -> str:
    """Bold label + ? chip for inline summary lines."""
    return f"<b>{html.escape(label)}</b>{_hint(help_md)}"


def _detail_line_with_hint(label: str, value_html: str, help_md: str) -> str:
    """Label + ? + value on one row (expander / annex blocks). value_html may include safe markup."""
    return (
        f'<p class="exec-muted-small" style="margin:0 0 0.55rem 0;line-height:1.5;display:flex;'
        f'flex-wrap:wrap;justify-content:space-between;gap:0.5rem;align-items:flex-start;">'
        f'<span style="display:inline-flex;align-items:center;gap:0.28rem;flex-wrap:wrap;max-width:72%;">'
        f"{_labeled_hint(label, help_md)}</span>"
        f'<span style="font-weight:700;color:#0f172a;text-align:right;">{value_html}</span></p>'
    )


def _technical_lift_detail_html(rec: pd.Series) -> str:
    """Expandable block: each derived metric with ? — how computed + why shown."""
    ev = float(rec["expected_value"])
    lv_b = float(rec["conversion_lift_vs_baseline"])
    lv_apr = float(rec["conversion_lift_vs_zero_apr_same_cash"])
    eff = float(rec["efficiency_score"])
    esc = float(rec["estimated_support_cost"])

    h_base = (
        "**How:** model probability for the recommended package **minus** model probability for a "
        "**zero-incentive** scenario at the **same loan term** (no rate buy-down and no stacked cash "
        "in that baseline row). **Why:** anchors incremental conversion against a full strip baseline."
    )
    h_apr = (
        "**How:** model probability for the recommended package **minus** probability when **rate support "
        "is set to 0** while keeping **this row’s cash stack and term**—isolates the APR subsidy path. "
        "**Why:** see how much lift comes from buy-down versus cash."
    )
    h_ev = (
        "**How:** **predicted conversion × expected unit margin − total modeled support** "
        "(`expected_value` in code). **Why:** ranks packages on **expected economic outcome** under "
        "uncertainty (you only earn margin when the deal closes), not on gross margin if everyone signed."
    )
    h_eff = (
        "**How:** **(conversion lift vs no-incentive baseline) ÷ max(estimated support cost, $1)** — "
        "same lift as the first line, dollars from your support formula. **Why:** highlights packages "
        "that buy a lot of probability lift per modeled incentive dollar."
    )

    ev_disp = f"<code>{ev:,.0f}</code> USD"
    return (
        '<div style="max-width:52rem;">'
        + _detail_line_with_hint(
            "Lift vs no-incentive baseline (same term)",
            html.escape(f"{lv_b:.2%}"),
            h_base,
        )
        + _detail_line_with_hint(
            "Lift from APR subsidy (cash held fixed)",
            html.escape(f"{lv_apr:.2%}"),
            h_apr,
        )
        + _detail_line_with_hint(
            "Net deal outcome (USD)",
            ev_disp,
            h_ev,
        )
        + _detail_line_with_hint(
            "Support efficiency (lift ÷ spend)",
            html.escape(f"{eff:.4f} (support ≈ {esc:,.0f} USD)"),
            h_eff,
        )
        + "</div>"
    )


def _help_icon_html(help_md: str) -> str:
    """
    Visible ? plus a real text popup on hover (CSS), not browser title= tooltips —
    Streamlit’s HTML sanitizer often strips or breaks title attributes.
    """
    plain = _help_plain_for_tooltip(help_md, max_len=None)
    body = html.escape(plain)
    aria = html.escape(plain)
    return (
        f'<span class="exec-field-help-wrap" tabindex="0" role="note" aria-label="{aria}">'
        f'<span class="exec-field-help-trigger">?</span>'
        f'<span class="exec-field-help-popup">{body}</span>'
        f"</span>"
    )


def _field_label(
    label: str,
    help_md: str,
    *,
    wizard: bool,
    root=None,
) -> None:
    if wizard:
        st.markdown(
            f'<p class="demo-field-label">{html.escape(label)}{_help_icon_html(help_md)}</p>',
            unsafe_allow_html=True,
        )
    else:
        _sb_row_label_help(label, help_md, root=root, compact=True)


def _input_help(help_text: str, *, wizard: bool = True) -> dict[str, str]:
    """Streamlit `help=` tooltips (? icon) on widgets — wizard and sidebar both use the same copy."""
    _ = wizard  # callers pass wizard=wizard for readability; always attach native help
    return {"help": help_text}


def _computed_dti_ratio_display() -> str:
    mi = float(st.session_state.get("sb_monthly_income") or 0)
    debt = float(st.session_state.get("sb_monthly_debt_payments") or 0)
    if mi <= 0:
        return "—"
    return f"{100.0 * debt / mi:.2f}%"


def _business_dti_ratio() -> float:
    """Monthly debt payments ÷ gross monthly income, clipped for the model."""
    mi = float(st.session_state.get("sb_monthly_income") or 0)
    debt = float(st.session_state.get("sb_monthly_debt_payments") or 0)
    if mi <= 0:
        return 0.0
    return float(min(max(debt / mi, 0.0), 1.5))


def _sb_row_label_help(
    label: str,
    help_md: str,
    *,
    root=None,
    compact: bool = False,
) -> None:
    """
    Label + inline ? (hover shows explanation). Widget `help=` remains for native tooltip parity.
    """
    icon = _help_icon_html(help_md)
    if compact:
        para = (
            f'<p style="margin:0 0 0.35rem 0;font-weight:600;font-size:0.75rem;color:#71717a;'
            f'display:flex;align-items:center;flex-wrap:wrap;gap:0.35rem;">'
            f"{html.escape(label)}{icon}</p>"
        )
    else:
        para = (
            f'<p style="margin:0 0 0.35rem 0;font-weight:600;font-size:0.9375rem;color:#18181b;'
            f'display:flex;align-items:center;flex-wrap:wrap;gap:0.35rem;">'
            f"{html.escape(label)}{icon}</p>"
        )

    _ = root
    st.markdown(para, unsafe_allow_html=True)


def _help_scale(title: str, l1: str, l5: str, l8: str, l10: str) -> str:
    return (
        f"**{title}** (1–10)\n\n"
        f"**1** — {l1}\n\n"
        f"**5** — {l5}\n\n"
        f"**8** — {l8}\n\n"
        f"**10** — {l10}"
    )


def _validate_wizard_section(section_id: str) -> list[str]:
    errs: list[str] = []
    if section_id == "customer":
        if float(st.session_state.get("sb_monthly_income") or 0) <= 0:
            errs.append("Monthly gross income must be greater than zero.")
    elif section_id == "vehicle":
        if not str(st.session_state.get("sb_make") or "").strip():
            errs.append("Vehicle make is required.")
        if not str(st.session_state.get("sb_model_name") or "").strip():
            errs.append("Vehicle model is required.")
        if float(st.session_state.get("sb_loan_amount") or 0) <= 0:
            errs.append("Loan amount must be greater than zero.")
        tl = _loan_terms_sorted_from_session(
            st.session_state.get("sb_allowed_loan_terms")
        )
        if not tl:
            errs.append("Select at least one allowed loan term.")
    elif section_id == "financing":
        pass
    elif section_id == "competitor":
        if not str(st.session_state.get("sb_primary_competitor") or "").strip():
            errs.append("Primary competitor name is required.")
    elif section_id == "macro":
        if not str(st.session_state.get("sb_region") or "").strip():
            errs.append("Region is required.")
        if not str(st.session_state.get("sb_state") or "").strip():
            errs.append("State is required.")
    return errs


def _sidebar_all_sections_complete() -> bool:
    return all(
        bool(st.session_state.get(f"section_done_{s}", False))
        for s in SIDEBAR_SECTION_ORDER
    )


def _render_wizard_progress(current_step: int) -> None:
    st.sidebar.markdown("##### Progress")
    for i, sec in enumerate(SIDEBAR_SECTION_ORDER):
        done = bool(st.session_state.get(f"section_done_{sec}", False))
        label = SIDEBAR_SECTION_LABELS[sec]
        if done:
            line = (
                f'<span style="color:#16a34a;font-weight:700;">✓</span> '
                f'<span style="color:#3f3f46;">{html.escape(label)}</span>'
            )
        elif i == current_step:
            line = f"▸ **{html.escape(label)}**"
        else:
            line = f'<span style="color:#a1a1aa;">○ {html.escape(label)}</span>'
        st.sidebar.markdown(line, unsafe_allow_html=True)


def _sidebar_migrate_phase2_ui() -> None:
    """Align legacy session keys with Phase 2 UI option lists and Yes/No controls."""
    yn_map: list[tuple[str, str, str]] = [
        ("sb_metro_yn", "sb_metro_flag", "Yes"),
        ("sb_promotion_yn", "sb_promotion_flag", "No"),
        ("sb_overstock_yn", "sb_overstock_flag", "No"),
        ("sb_stockout_yn", "sb_stockout_risk_flag", "No"),
        ("sb_quarter_end_yn", "sb_quarter_end_flag", "No"),
        ("sb_rv_push_yn", "sb_rv_push_brand_flag", "Yes"),
    ]
    for new_k, old_k, default_yn in yn_map:
        if new_k not in st.session_state:
            if old_k in st.session_state:
                st.session_state[new_k] = (
                    "Yes" if bool(st.session_state[old_k]) else "No"
                )
            else:
                st.session_state[new_k] = default_yn

    salestype = str(st.session_state.get("sb_sales_type", ""))
    if salestype and salestype not in SALES_TYPES_UI:
        st.session_state.sb_sales_type = {
            "APR": "Retail",
            "Lease": "Lease",
            "Cash": "Cash",
            "Mixed": "Finance",
        }.get(salestype, "Retail")

    ft = str(st.session_state.get("sb_fuel_type", ""))
    if ft and ft not in FUEL_TYPES_UI:
        st.session_state.sb_fuel_type = {
            "Gas": "Gasoline",
            "PHEV": "Plug-in Hybrid",
            "Other": "Gasoline",
        }.get(ft, "Gasoline")

    bs = str(st.session_state.get("sb_body_style", ""))
    if bs and bs not in BODY_STYLES_UI:
        st.session_state.sb_body_style = {
            "Wagon": "Hatchback",
            "Van": "SUV",
            "Other": "Sedan",
        }.get(bs, "Sedan")

    mk = str(st.session_state.get("sb_make") or "")
    if mk not in MODEL_BY_MAKE:
        st.session_state.sb_make = MAKES[0]
    mo = str(st.session_state.get("sb_model_name") or "")
    allowed_m = MODEL_BY_MAKE[str(st.session_state.sb_make)]
    if mo not in allowed_m:
        st.session_state.sb_model_name = allowed_m[0]

    tr = str(st.session_state.get("sb_trim") or "")
    if tr not in TRIM_LEVELS:
        st.session_state.sb_trim = "Sport"

    pc = str(st.session_state.get("sb_primary_competitor") or "")
    if pc not in PRIMARY_COMPETITORS:
        st.session_state.sb_primary_competitor = "Honda"

    if str(st.session_state.get("sb_region", "")) not in REGIONS:
        st.session_state.sb_region = "Midwest"
    if str(st.session_state.get("sb_state", "")) not in STATES:
        st.session_state.sb_state = "IL"

    if (
        "sb_allowed_loan_terms" not in st.session_state
        and "sb_loan_term" in st.session_state
    ):
        lt = int(st.session_state.sb_loan_term)
        st.session_state.sb_allowed_loan_terms = (
            [lt] if lt in LOAN_TERMS else [48, 60, 72]
        )


def _sidebar_init_defaults(now: datetime) -> None:
    """Seed session_state once so inputs survive when sections are not rendered."""
    if "sb_monthly_debt_payments" not in st.session_state and "sb_dti" in st.session_state:
        try:
            mi = float(
                st.session_state.get("sb_monthly_income")
                or get_demo_defaults()["monthly_gross_income"]
            )
            st.session_state.sb_monthly_debt_payments = round(
                float(st.session_state.sb_dti) * mi, 2
            )
        except Exception:
            st.session_state.sb_monthly_debt_payments = float(
                get_demo_defaults()["monthly_debt_payments"]
            )

    defaults = session_defaults_from_demo(now)

    try:
        stored_ver = int(st.session_state.get(_DEMO_DEFAULTS_VERSION_KEY, -1))
    except (TypeError, ValueError):
        stored_ver = -1
    if stored_ver != _DEMO_DEFAULTS_VERSION:
        for k, v in defaults.items():
            st.session_state[k] = v
        st.session_state[_DEMO_DEFAULTS_VERSION_KEY] = _DEMO_DEFAULTS_VERSION
        st.session_state.current_step = 0
        for sec in SIDEBAR_SECTION_ORDER:
            st.session_state[f"section_done_{sec}"] = False
    else:
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

    for sec in SIDEBAR_SECTION_ORDER:
        sk = f"section_done_{sec}"
        if sk not in st.session_state:
            st.session_state[sk] = False

    _normalize_scalar_widget_session(fb=defaults)
    _sidebar_migrate_phase2_ui()


def build_business_inputs() -> dict[str, Any]:
    """Assemble unified context dict for the model (baseline before optimization levers)."""
    ps = score_1_10_to_model(int(st.session_state.sb_price_sensitivity_ui))
    urg = score_1_10_to_model(int(st.session_state.sb_purchase_urgency_ui))
    brand = score_1_10_to_model(int(st.session_state.sb_brand_preference_ui))
    dm = float(st.session_state.sb_dealer_margin_pct_display) / 100.0
    aging = float(st.session_state.sb_aging_inventory_pct_display) / 100.0
    terms_sorted = _loan_terms_sorted_from_session(
        st.session_state.get("sb_allowed_loan_terms")
    )
    want_term = int(st.session_state.get("sb_primary_loan_term") or terms_sorted[0])
    if want_term not in terms_sorted:
        want_term = min(terms_sorted, key=lambda t: abs(int(t) - want_term))
    ref_term = int(want_term)
    loan_amt = float(st.session_state.sb_loan_amount)
    std_apr = float(st.session_state.sb_standard_apr)
    # Baseline: no rate buy-down and no stacked cash — optimizer searches from here.
    baseline_support = 0.0
    dealer_apr_ctx = float(st.session_state.sb_baseline_dealer_apr)
    baseline_payment = float(st.session_state.sb_baseline_dealer_monthly_payment)
    if baseline_payment <= 0:
        baseline_payment = calculate_monthly_payment_if_needed(
            loan_amt, dealer_apr_ctx, ref_term
        )
    return {
        "fico_score": float(st.session_state.sb_fico_score),
        "monthly_income": float(st.session_state.sb_monthly_income),
        "dti": _business_dti_ratio(),
        "price_sensitivity_score": ps,
        "customer_urgency_score": urg,
        "brand_loyalty_score": brand,
        "purchase_intent_index": score_1_10_to_model(
            int(st.session_state.sb_purchase_intent_ui)
        ),
        "sentiment_score": sentiment_ui_to_model(int(st.session_state.sb_sentiment_ui)),
        "customer_segment": str(st.session_state.sb_customer_segment),
        "loyalty_score": brand,
        "conquest_score": score_1_10_to_model(
            int(st.session_state.sb_conquest_likelihood_ui)
        ),
        "ev_affinity_score": score_1_10_to_model(int(st.session_state.sb_ev_affinity_ui)),
        "family_utility_score": score_1_10_to_model(
            int(st.session_state.sb_family_utility_ui)
        ),
        "truck_affinity_score": score_1_10_to_model(
            int(st.session_state.sb_truck_affinity_ui)
        ),
        "make": str(st.session_state.sb_make),
        "model_name": str(st.session_state.sb_model_name),
        "model_year": int(st.session_state.sb_model_year),
        "trim": str(st.session_state.sb_trim),
        "body_style": map_body_ui_to_model(str(st.session_state.sb_body_style)),
        "fuel_type": map_fuel_ui_to_model(str(st.session_state.sb_fuel_type)),
        "vehicle_segment": str(st.session_state.sb_vehicle_segment),
        "vehicle_price": float(st.session_state.sb_vehicle_price),
        "vehicle_age": float(st.session_state.sb_vehicle_age),
        "rv_strength_index": score_1_10_to_model(
            int(st.session_state.sb_rv_strength_ui)
        ),
        "residual_support_pct": float(st.session_state.sb_residual_support_pct_display)
        / 100.0,
        "rv_push_brand_flag": yes_no_to_bool(st.session_state.sb_rv_push_yn),
        "dealer_size_tier": str(st.session_state.sb_dealer_size_tier),
        "metro_flag": yes_no_to_bool(st.session_state.sb_metro_yn),
        "avg_monthly_retail_units": float(st.session_state.sb_avg_monthly_retail_units),
        "dealer_margin_pct": dm,
        "expected_unit_margin": float(st.session_state.sb_expected_unit_margin),
        "days_in_inventory": float(st.session_state.sb_days_in_inventory),
        "on_hand_units": float(st.session_state.sb_on_hand_units),
        "in_transit_units": float(st.session_state.sb_in_transit_units),
        "aging_over_90_days_pct": aging,
        "stockout_risk_flag": yes_no_to_bool(st.session_state.sb_stockout_yn),
        "overstock_flag": yes_no_to_bool(st.session_state.sb_overstock_yn),
        "inventory_pressure_score": score_1_10_to_model(
            int(st.session_state.sb_inventory_pressure_ui)
        ),
        "loan_amount": loan_amt,
        "down_payment": float(st.session_state.sb_down_payment),
        "loan_term": ref_term,
        "standard_apr": std_apr,
        "dealer_apr": max(0.5, dealer_apr_ctx),
        "dealer_monthly_payment": max(150.0, baseline_payment),
        "customer_cash": 0.0,
        "dealer_cash": 0.0,
        "loyalty_cash": 0.0,
        "conquest_cash": 0.0,
        "promotion_flag": False,
        "dealer_rate_support_level": baseline_support,
        "primary_competitor": str(st.session_state.sb_primary_competitor),
        "competitor_apr": float(st.session_state.sb_competitor_apr),
        "competitor_monthly_payment": float(st.session_state.sb_competitor_monthly_payment),
        "competitor_cashback": float(st.session_state.sb_competitor_cashback),
        "competitor_offer_aggressiveness_index": score_1_10_to_model(
            int(st.session_state.sb_competitor_aggr_ui)
        ),
        "competitor_sales_volume_index": score_1_10_to_model(
            int(st.session_state.sb_competitor_sales_ui)
        ),
        "fed_rate": float(st.session_state.sb_fed_rate),
        "ten_year_treasury_yield": float(st.session_state.sb_ten_year),
        "inflation_rate_cpi": float(st.session_state.sb_inflation_cpi),
        "base_auto_rate_index": float(st.session_state.sb_base_auto_rate_index),
        "market_rate_index": float(st.session_state.sb_market_rate_index),
        "month_of_quote": int(st.session_state.sb_month_of_quote),
        "day_of_week_quote": int(st.session_state.sb_day_of_week_quote),
        "quarter_end_flag": yes_no_to_bool(st.session_state.sb_quarter_end_yn),
        "sales_type": map_sales_ui_to_model(str(st.session_state.sb_sales_type)),
        "region": str(st.session_state.sb_region),
        "state": str(st.session_state.sb_state),
    }


def validate_business_inputs(business: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if float(business["vehicle_price"]) <= 0:
        errors.append("Vehicle price must be greater than zero.")

    if float(business["monthly_income"]) <= 0:
        errors.append("Monthly gross income must be greater than zero.")

    terms = _loan_terms_sorted_from_session(
        st.session_state.get("sb_allowed_loan_terms")
    )
    if not terms:
        errors.append("Select at least one allowed loan term under Vehicle / Deal structure.")

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


def render_hero() -> None:
    st.markdown(
        '<header class="demo-hero" role="banner">'
        '<h1 class="demo-hero-title">Auto Finance Subvention Optimization Simulator</h1>'
        "<p class=\"demo-hero-sub\">"
        "Guided input capture for conversion and support-cost optimization.</p>"
        "</header>",
        unsafe_allow_html=True,
    )


def render_step_card_header(step_index: int, sec: str) -> None:
    step_num = step_index + 1
    title = WIZARD_STEP_TITLE.get(sec, sec)
    st.markdown(
        f'<div id="wizard-scroll-anchor" class="wizard-step-scroll-target">'
        f'<p class="demo-step-meta">Step {step_num} of 6</p>'
        f'<h2 class="demo-step-title">{html.escape(title)}</h2>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_section_header(title: str) -> None:
    st.markdown(
        f'<p class="demo-section-title">{html.escape(title)}</p>',
        unsafe_allow_html=True,
    )


def render_metric_pill(label: str, value: str, help_text: str) -> None:
    st.markdown(
        f'<div class="demo-metric-pill">'
        f'<span class="demo-metric-pill-label">{html.escape(label)}{_help_icon_html(help_text)}</span>'
        f'<span class="demo-metric-pill-value">{html.escape(value)}</span></div>'
        f'<p class="demo-metric-pill-help">{html.escape(help_text)}</p>',
        unsafe_allow_html=True,
    )


def render_slider_1_10(
    label: str,
    state_key: str,
    *,
    help_text: str,
    fb: dict[str, Any] | None = None,
) -> None:
    fd = fb if fb is not None else _widget_fb()
    _field_label(label, help_text, wizard=True)
    _slider_int_with_exact(
        fd,
        state_key,
        label,
        min_value=1,
        max_value=10,
        help_text=help_text,
    )
    _slider_scale_caption(state_key, wizard=True)


def render_customer_profile_wizard() -> None:
    _fb = _widget_fb()
    _normalize_scalar_widget_session(fb=_fb)

    render_section_header("Credit & Affordability")
    cr_a, cr_b = _wizard_pair_columns()
    with cr_a:
        _field_label(
            "Credit score",
            "Approximate bureau-style score used with income and debt to reflect financing fit.",
            wizard=True,
        )
        _slider_int_with_exact(
            _fb,
            "sb_fico_score",
            "Credit score",
            min_value=300,
            max_value=850,
            help_text=(
                "Approximate bureau-style score used with income and debt to reflect financing fit."
            ),
        )
        _slider_range_caption("sb_fico_score", wizard=True)
        _field_label(
            "Monthly debt payments ($)",
            "Total minimum required monthly payments on reported debts (cards, loans, "
            "housing per your credit policy).",
            wizard=True,
        )
        _slider_int_with_exact(
            _fb,
            "sb_monthly_debt_payments",
            "Monthly debt payments ($)",
            min_value=0,
            max_value=20000,
            step=50,
            help_text=(
                "Total minimum required monthly payments on reported debts (cards, loans, "
                "housing per your credit policy)."
            ),
        )
        _slider_range_caption("sb_monthly_debt_payments", wizard=True)
    with cr_b:
        _field_label(
            "Monthly gross income ($)",
            "Customer gross income before taxes, per month.",
            wizard=True,
        )
        _slider_int_with_exact(
            _fb,
            "sb_monthly_income",
            "Monthly gross income ($)",
            min_value=2000,
            max_value=35000,
            step=100,
            help_text="Customer gross income before taxes, per month.",
        )
        _slider_range_caption("sb_monthly_income", wizard=True)
        render_metric_pill(
            "Computed debt-to-income",
            _computed_dti_ratio_display(),
            "Calculated from monthly debt payments ÷ monthly gross income.",
        )

    render_section_header("Intent & Preference")
    in_a, in_b = _wizard_pair_columns()
    with in_a:
        render_slider_1_10(
            "Price sensitivity",
            "sb_price_sensitivity_ui",
            help_text="How strongly the customer reacts to APR, payment, or rebate differences.",
            fb=_fb,
        )
        render_slider_1_10(
            "Purchase urgency",
            "sb_purchase_urgency_ui",
            help_text="How soon the customer needs to complete the purchase.",
            fb=_fb,
        )
        render_slider_1_10(
            "Purchase intent",
            "sb_purchase_intent_ui",
            help_text="Strength of intent from visits, paperwork, financing steps, and follow-through.",
            fb=_fb,
        )
    with in_b:
        render_slider_1_10(
            "Brand preference / loyalty",
            "sb_brand_preference_ui",
            help_text="Attachment to the selling brand versus openness to alternatives.",
            fb=_fb,
        )
        _field_label(
            "Customer sentiment",
            "Overall impression of the offer or experience. Neutral is **5**; the model uses "
            "(score − 5) ÷ 5.",
            wizard=True,
        )
        _slider_int_with_exact(
            _fb,
            "sb_sentiment_ui",
            "Customer sentiment",
            min_value=1,
            max_value=10,
            help_text=(
                "Overall impression of the offer or experience. Neutral is **5**; the model uses "
                "(score − 5) ÷ 5."
            ),
        )
        _slider_scale_caption("sb_sentiment_ui", wizard=True)
        _field_label(
            "Customer segment",
            "Archetype that anchors behavioral modifiers (value, premium, conquest, etc.).",
            wizard=True,
        )
        st.selectbox(
            "Customer segment",
            CUSTOMER_SEGMENTS,
            key="sb_customer_segment",
            format_func=format_customer_segment_option,
            label_visibility="collapsed",
            **_input_help(
                "Archetype that anchors behavioral modifiers (value, premium, conquest, etc.)."
            ),
        )

    render_section_header("Lifestyle Fit")
    lf_a, lf_b = _wizard_pair_columns()
    with lf_a:
        render_slider_1_10(
            "EV interest",
            "sb_ev_affinity_ui",
            help_text="Interest in electric or plug-in vehicles when a viable option exists.",
            fb=_fb,
        )
        render_slider_1_10(
            "Family / utility need",
            "sb_family_utility_ui",
            help_text="Passenger, cargo, and practicality needs for household use.",
            fb=_fb,
        )
    with lf_b:
        render_slider_1_10(
            "Truck interest",
            "sb_truck_affinity_ui",
            help_text="Interest in trucks versus cars or SUVs for this purchase.",
            fb=_fb,
        )
        render_slider_1_10(
            "Conquest likelihood",
            "sb_conquest_likelihood_ui",
            help_text="Likelihood the shopper will switch from another brand if the offer wins.",
            fb=_fb,
        )


def _wizard_footer_columns(spec: list[float]):
    """Wizard footer columns with the smallest valid gap (some versions only allow small/medium/large)."""
    try:
        return st.columns(spec, gap="small")
    except TypeError:
        return st.columns(spec)


def _wizard_pair_columns():
    """Two columns for wizard body rows; compact gap when supported."""
    try:
        return st.columns(2, gap="small")
    except TypeError:
        return st.columns(2)
    except Exception as e:
        if type(e).__name__ == "StreamlitAPIException" or "gap" in str(e).lower():
            return st.columns(2)
        raise


def _wizard_request_scroll_top(*, injections: int = 1) -> None:
    """Queue scroll alignment (`injections` HTML fragments). Wizard uses 2: header + full step DOM."""
    st.session_state[_WIZARD_SCROLL_PENDING_KEY] = True
    st.session_state[_WIZARD_SCROLL_INJECTIONS_LEFT_KEY] = max(1, int(injections))


def _wizard_flush_scroll_top() -> None:
    """Emit scroll alignment script while injections remain. Place calls high + late in wizard."""
    if not st.session_state.get(_WIZARD_SCROLL_PENDING_KEY):
        return
    left = int(st.session_state.get(_WIZARD_SCROLL_INJECTIONS_LEFT_KEY, 0))
    if left <= 0:
        st.session_state[_WIZARD_SCROLL_PENDING_KEY] = False
        return
    st.session_state[_WIZARD_SCROLL_INJECTIONS_LEFT_KEY] = left - 1
    if int(st.session_state.get(_WIZARD_SCROLL_INJECTIONS_LEFT_KEY, 0)) <= 0:
        st.session_state[_WIZARD_SCROLL_PENDING_KEY] = False
    components.html(
        """
<script>
(function () {
  function hostDoc() {
    try {
      if (window.parent && window.parent.document) {
        return window.parent.document;
      }
    } catch (e0) {}
    return document;
  }
  function anchorEl(d) {
    return d.getElementById("wizard-scroll-anchor")
      || d.getElementById("results-scroll-anchor")
      || d.querySelector(".wizard-step-scroll-target")
      || d.querySelector(".results-view-scroll-target");
  }
  function collectScrollContainers(anchor) {
    var out = [];
    var d = anchor.ownerDocument;
    var win = d.defaultView || window;
    var p = anchor.parentElement;
    while (p && p !== d.documentElement && p !== d.body) {
      try {
        var st = win.getComputedStyle(p);
        var oy = st.overflowY;
        var scrollableY =
          (oy === "auto" || oy === "scroll" || oy === "overlay") &&
          p.scrollHeight > p.clientHeight + 2;
        if (scrollableY) {
          out.push(p);
        }
      } catch (e1) {}
      p = p.parentElement;
    }
    return out;
  }
  /**
   * Streamlit nests overflow:auto regions. scrollIntoView on the anchor often adjusts only one
   * layer, so mid-wizard steps still land partway down the page.
   */
  function alignAnchorToTop() {
    var d = hostDoc();
    var anchor = anchorEl(d);
    if (!anchor || !anchor.getBoundingClientRect) {
      return;
    }
    var win = d.defaultView || window;
    try {
      if ("scrollRestoration" in win.history) {
        win.history.scrollRestoration = "manual";
      }
    } catch (e2) {}
    var pad = 14;
    var containers = collectScrollContainers(anchor);
    var i;
    for (i = 0; i < containers.length; i++) {
      var box = containers[i];
      var ar = anchor.getBoundingClientRect();
      var br = box.getBoundingClientRect();
      var delta = ar.top - br.top - pad;
      if (Math.abs(delta) > 1) {
        box.scrollTop += delta;
      }
    }
    var ar2 = anchor.getBoundingClientRect();
    if (Math.abs(ar2.top - pad) > 3) {
      try {
        win.scrollBy(0, ar2.top - pad);
      } catch (e3) {}
    }
    try {
      anchor.scrollIntoView({ block: "start", behavior: "auto" });
    } catch (e4) {}
  }
  function run() {
    try {
      alignAnchorToTop();
    } catch (e5) {}
  }
  run();
  requestAnimationFrame(run);
  [0, 50, 120, 280, 600, 1200].forEach(function (ms) {
    setTimeout(run, ms);
  });
  try {
    var d = hostDoc();
    var bc = d.querySelector(".main .block-container") || d.querySelector('[data-testid="stMain"]');
    if (bc && typeof MutationObserver !== "undefined") {
      var deb = null;
      var fired = 0;
      var obs = new MutationObserver(function () {
        clearTimeout(deb);
        deb = setTimeout(function () {
          if (fired >= 10) {
            try {
              obs.disconnect();
            } catch (e6) {}
            return;
          }
          fired += 1;
          run();
        }, 60);
      });
      obs.observe(bc, { childList: true, subtree: true });
      setTimeout(function () {
        try {
          obs.disconnect();
        } catch (e7) {}
      }, 2400);
    }
  } catch (e8) {}
})();
</script>
""",
        height=0,
    )


def render_navigation(step_index: int) -> None:
    """Wizard footer: tight columns, no framed boxes — CSS scoped to this strip only."""
    order = SIDEBAR_SECTION_ORDER
    n = len(order)
    sec = order[step_index]

    def _validate_and_advance() -> None:
        errs = _validate_wizard_section(sec)
        if errs:
            for msg in errs:
                st.error(msg)
        else:
            st.session_state.current_step = step_index + 1
            _wizard_request_scroll_top(injections=2)
            st.rerun()

    def _run_analysis() -> None:
        errs = _validate_wizard_section(sec)
        if errs:
            for msg in errs:
                st.error(msg)
        else:
            st.session_state.analysis_submitted = True
            st.session_state.quote_submitted = True
            st.session_state.analysis_compute_requested = True
            _wizard_request_scroll_top(injections=2)
            st.rerun()

    if step_index == 0:
        _left_pad, _mid, _nav_r = _wizard_footer_columns([2, 9, 2])
        with _nav_r:
            if st.button("Next →", type="primary", key="wiz_main_next"):
                _validate_and_advance()
    else:
        _back_col, _spacer, _fwd_col = _wizard_footer_columns([2, 12, 2])
        with _back_col:
            if st.button("← Back", key="wiz_main_back"):
                st.session_state.current_step = step_index - 1
                _wizard_request_scroll_top(injections=2)
                st.rerun()
        with _fwd_col:
            if step_index < n - 1:
                if st.button("Next →", type="primary", key="wiz_main_next"):
                    _validate_and_advance()
            else:
                if st.button("Run analysis", type="primary", key="wiz_main_run"):
                    _run_analysis()


def render_quote_section_fields(sec: str, *, wizard: bool) -> None:
    """Render inputs for one wizard step or one edit-panel section (same keys)."""
    _fb = _widget_fb()
    _normalize_scalar_widget_session(fb=_fb)
    gv = lambda k: _gv(_fb, k)

    if sec == "customer":
        if wizard:
            render_customer_profile_wizard()
        else:
            _c_lo, _c_hi = _two_cols(wizard)
            with _c_lo:
                _field_label(
                    "Credit score",
                    "Typical bureau-style score used with income and monthly debt to approximate financing fit.",
                    wizard=wizard,
                    root=_c_lo,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_fico_score",
                    "Credit score",
                    min_value=300,
                    max_value=850,
                    help_text=(
                        "Typical bureau-style score used with income and monthly debt to approximate financing fit."
                    ),
                    wizard=wizard,
                )
                _slider_range_caption("sb_fico_score", wizard=wizard)
                _field_label(
                    "Monthly gross income ($)",
                    "Customer’s gross income **before taxes**, per month.",
                    wizard=wizard,
                    root=_c_lo,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_monthly_income",
                    "Monthly gross income",
                    min_value=2000,
                    max_value=35000,
                    step=100,
                    help_text="Customer gross income before taxes, per month.", wizard=wizard)
                _slider_range_caption("sb_monthly_income", wizard=wizard)
                _field_label(
                    "Monthly debt payments ($)",
                    "Total **minimum required** monthly payments on all debts (cards, loans, rent/mortgage if counted by your policy, etc.). "
                    "We compute debt-to-income automatically.",
                    wizard=wizard,
                    root=_c_lo,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_monthly_debt_payments",
                    "Monthly debt payments",
                    min_value=0,
                    max_value=20000,
                    step=50,
                    help_text=(
                        "Total minimum required monthly payments on all debts (cards, loans, "
                        "rent/mortgage if counted by your policy)."
                    ),
                    wizard=wizard,
                )
                _slider_range_caption("sb_monthly_debt_payments", wizard=wizard)
                if wizard:
                    st.caption(
                        f"**Debt-to-income (computed):** {_computed_dti_ratio_display()} "
                        "(monthly debt ÷ monthly gross income)"
                    )
                _field_label(
                    "Price sensitivity",
                    _help_scale(
                        "Price sensitivity",
                        "Barely notices APR, payment, or rebate differences.",
                        "Balanced — compares offers when the gap is meaningful.",
                        "Strongly compares pricing; small differences influence choice.",
                        "Extremely sensitive — tiny pricing gaps can win or lose the deal.",
                    ),
                    wizard=wizard,
                    root=_c_lo,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_price_sensitivity_ui",
                    "Price sensitivity",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "How strongly APR, payment, or rebate differences influence the deal (1–10)."
                    ),
                    wizard=wizard,
                )
                _slider_scale_caption("sb_price_sensitivity_ui", wizard=wizard)
                _field_label(
                    "Purchase urgency",
                    _help_scale(
                        "Purchase urgency",
                        "Casually browsing; no near-term timeline.",
                        "Planning to buy within a few months if terms are fair.",
                        "Actively shopping and narrowing choices within weeks.",
                        "Must purchase immediately (replacement, lease end, urgent need).",
                    ),
                    wizard=wizard,
                    root=_c_lo,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_purchase_urgency_ui",
                    "Purchase urgency",
                    min_value=1,
                    max_value=10,
                    help_text="Timeline pressure from browsing to immediate need (1–10).", wizard=wizard)
                _slider_scale_caption("sb_purchase_urgency_ui", wizard=wizard)
                _field_label(
                    "Brand preference / loyalty",
                    _help_scale(
                        "Brand preference / loyalty",
                        "No loyalty — open to any make or dealer.",
                        "Mild preference — could switch for the right deal.",
                        "Strong preference — needs a compelling reason to leave the brand.",
                        "Extremely loyal — unlikely to consider alternatives.",
                    ),
                    wizard=wizard,
                    root=_c_lo,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_brand_preference_ui",
                    "Brand preference",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "Loyalty to the selling brand versus openness to alternatives (1–10)."
                    ),
                    wizard=wizard,
                )
                _slider_scale_caption("sb_brand_preference_ui", wizard=wizard)
            with _c_hi:
                _field_label(
                    "Purchase intent",
                    _help_scale(
                        "Purchase intent",
                        "Very low intent / tire-kicker.",
                        "Moderate — interested but not committed.",
                        "High intent — serious buyer signals (repeat visits, docs, etc.).",
                        "Ready to buy now if terms are acceptable.",
                    ),
                    wizard=wizard,
                    root=_c_hi,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_purchase_intent_ui",
                    "Purchase intent",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "Strength of buying intent from visits, paperwork, and follow-through (1–10)."
                    ),
                    wizard=wizard,
                )
                _slider_scale_caption("sb_purchase_intent_ui", wizard=wizard)
                _field_label(
                    "Customer sentiment",
                    "**Neutral is 5** — this field uses a **different** conversion than other 1–10 sliders "
                    "(the model uses **(score − 5) ÷ 5**, so **5 ≈ neutral**, **1 ≈ very negative**, "
                    "**10 ≈ very positive**).\n\n"
                    + _help_scale(
                        "Customer sentiment",
                        "Very negative toward the offer, vehicle, or dealer experience.",
                        "Neutral or mixed feelings.",
                        "Clearly positive overall impression.",
                        "Extremely positive — enthusiastic advocate.",
                    ),
                    wizard=wizard,
                    root=_c_hi,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_sentiment_ui",
                    "Customer sentiment",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "Overall impression (1–10). Neutral is 5; the model uses (score − 5) ÷ 5."
                    ),
                    wizard=wizard,
                )
                _slider_scale_caption("sb_sentiment_ui", wizard=wizard)
                _field_label(
                    "Customer segment",
                    "Archetype used to anchor behavioral modifiers (value vs premium vs conquest, etc.).",
                    wizard=wizard,
                    root=_c_hi,
                )
                st.selectbox(
                    "Customer segment",
                    CUSTOMER_SEGMENTS,
                    key="sb_customer_segment",
                    label_visibility="collapsed",
                    format_func=format_customer_segment_option,
                    **_input_help("Archetype for behavioral modifiers (value vs premium vs conquest, etc.).", wizard=wizard),
                )
                _field_label(
                    "EV interest",
                    _help_scale(
                        "EV interest",
                        "No interest in electric vehicles.",
                        "Open to EV if range, price, and charging work.",
                        "Strong preference for EV when a viable option exists.",
                        "Wants an EV / strongly prefers plug-in or battery electric.",
                    ),
                    wizard=wizard,
                    root=_c_hi,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_ev_affinity_ui",
                    "EV interest",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "Interest in electric or plug-in vehicles when a viable option exists (1–10)."
                    ),
                    wizard=wizard,
                )
                _slider_scale_caption("sb_ev_affinity_ui", wizard=wizard)
                _field_label(
                    "Family / utility need",
                    _help_scale(
                        "Family / utility need",
                        "Minimal passenger or cargo requirements (solo or couples).",
                        "Typical household needs (school runs, occasional hauling).",
                        "Strong need for seating, safety, and practicality.",
                        "Vehicle must maximize family utility (third row, space, versatility).",
                    ),
                    wizard=wizard,
                    root=_c_hi,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_family_utility_ui",
                    "Family utility need",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "Passenger, cargo, and practicality needs for household use (1–10)."
                    ),
                    wizard=wizard,
                )
                _slider_scale_caption("sb_family_utility_ui", wizard=wizard)
                _field_label(
                    "Truck interest",
                    _help_scale(
                        "Truck interest",
                        "No interest in trucks.",
                        "Would consider a truck if deal and capability fit.",
                        "Strong truck preference when mission fits.",
                        "Primarily wants a truck / truck-first shopper.",
                    ),
                    wizard=wizard,
                    root=_c_hi,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_truck_affinity_ui",
                    "Truck interest",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "Interest in trucks versus cars or SUVs for this purchase (1–10)."
                    ),
                    wizard=wizard,
                )
                _slider_scale_caption("sb_truck_affinity_ui", wizard=wizard)
                _field_label(
                    "Conquest likelihood",
                    _help_scale(
                        "Conquest likelihood",
                        "Likely repeat / captive buyer to current brand.",
                        "Could be swayed by a competitive offer.",
                        "Strong conquest candidate if execution and pricing align.",
                        "Actively cross-shopping — prime conquest opportunity.",
                    ),
                    wizard=wizard,
                    root=_c_hi,
                )
                _slider_int_with_exact(
                    _fb,
                    "sb_conquest_likelihood_ui",
                    "Conquest likelihood",
                    min_value=1,
                    max_value=10,
                    help_text=(
                        "Likelihood the shopper switches from another brand if your offer wins (1–10)."
                    ),
                    wizard=wizard,
                )

                _slider_scale_caption("sb_conquest_likelihood_ui", wizard=wizard)
    elif sec == "vehicle":
        mk_cur = str(st.session_state.get("sb_make") or MAKES[0])
        if mk_cur not in MODEL_BY_MAKE:
            mk_cur = MAKES[0]
            st.session_state.sb_make = mk_cur
        model_opts = MODEL_BY_MAKE[mk_cur]
        if str(st.session_state.get("sb_model_name") or "") not in model_opts:
            st.session_state.sb_model_name = model_opts[0]

        _vl, _vr = _two_cols(wizard)
        with _vl:
            _field_label(
                "Make",
                "Vehicle brand for this quote; the model list updates based on make.",
                wizard=wizard,
                root=_vl,
            )
            st.selectbox(
                "Make",
                MAKES,
                key="sb_make",
                label_visibility="collapsed",
                format_func=format_make_option,
                **_input_help("Vehicle brand for this quote; the model list updates based on make.", wizard=wizard),
            )
            _field_label(
                "Model",
                "Vehicle model for the selected make.",
                wizard=wizard,
                root=_vl,
            )
            st.selectbox(
                "Model",
                MODEL_BY_MAKE.get(
                    str(st.session_state.sb_make),
                    MODEL_BY_MAKE[MAKES[0]],
                ),
                key="sb_model_name",
                label_visibility="collapsed",
                format_func=format_model_option,
                **_input_help("Vehicle model for the selected make.", wizard=wizard),
            )
            _field_label(
                "Model year",
                "Vehicle model year for the unit being quoted.",
                wizard=wizard,
                root=_vl,
            )
            st.number_input(
                "Model year",
                min_value=2015,
                max_value=2030,
                value=int(gv("sb_model_year")),
                step=1,
                key="sb_model_year",
                label_visibility="collapsed",
                **_input_help("Vehicle model year for the unit being quoted.", wizard=wizard),
            )
            _slider_range_caption("sb_model_year", wizard=wizard)
            _field_label(
                "Trim",
                "Trim or equipment package (Base through Platinum).",
                wizard=wizard,
                root=_vl,
            )
            st.selectbox(
                "Trim",
                TRIM_LEVELS,
                key="sb_trim",
                label_visibility="collapsed",
                format_func=format_trim_option,
                **_input_help("Trim or equipment package (Base through Platinum).", wizard=wizard),
            )
            _field_label(
                "Body style",
                "High-level body style shown to customers.",
                wizard=wizard,
                root=_vl,
            )
            st.selectbox(
                "Body style",
                BODY_STYLES_UI,
                key="sb_body_style",
                label_visibility="collapsed",
                format_func=format_body_style_option,
                **_input_help("High-level body style shown to customers.", wizard=wizard),
            )
            _field_label(
                "Fuel type",
                "Powertrain category for this unit.",
                wizard=wizard,
                root=_vl,
            )
            st.selectbox(
                "Fuel type",
                FUEL_TYPES_UI,
                key="sb_fuel_type",
                label_visibility="collapsed",
                format_func=format_fuel_type_option,
                **_input_help("Powertrain category for this unit.", wizard=wizard),
            )
        with _vr:
            _field_label(
                "Vehicle type (segment)",
                "Retail segment bucket (economy, SUV, luxury, etc.).",
                wizard=wizard,
                root=_vr,
            )
            st.selectbox(
                "Vehicle type",
                VEHICLE_SEGMENTS,
                key="sb_vehicle_segment",
                label_visibility="collapsed",
                format_func=format_vehicle_segment_option,
                **_input_help("Retail segment bucket (economy, SUV, luxury, etc.).", wizard=wizard),
            )
            _field_label(
                "Vehicle price ($)",
                "Transaction price or MSRP basis used for the scenario (before incentives unless your process rolls them in elsewhere).",
                wizard=wizard,
                root=_vr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_vehicle_price",
                "Vehicle price",
                min_value=12000,
                max_value=120000,
                step=500,
                help_text=(
                    "Transaction price or MSRP basis for the scenario (before incentives unless rolled in elsewhere)."
                ),
                wizard=wizard,
            )
            _slider_range_caption("sb_vehicle_price", wizard=wizard)
            _field_label(
                "Vehicle age (years)",
                "Age of the unit (new = 0).",
                wizard=wizard,
                root=_vr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_vehicle_age",
                "Vehicle age",
                min_value=0,
                max_value=12,
                help_text="Age of the unit (new = 0).", wizard=wizard)
            _slider_range_caption("sb_vehicle_age", wizard=wizard)
            _field_label(
                "Residual value strength",
                _help_scale(
                    "Residual value strength",
                    "Weak expected resale / residual versus peers.",
                    "Average residual expectations for the segment.",
                    "Strong residual reputation — favorable lease/finance optics.",
                    "Top-tier residual strength (leader in class)."
                ),
                wizard=wizard,
                root=_vr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_rv_strength_ui",
                "Residual value strength",
                min_value=1,
                max_value=10,
                help_text=(
                    "Expected residual strength vs peers (1–10). Higher favors lease/finance optics."
                ),
                wizard=wizard,
            )
            _slider_scale_caption("sb_rv_strength_ui", wizard=wizard)
            _field_label(
                "Residual support %",
                "Manufacturer residual assistance as a percent of vehicle price.",
                wizard=wizard,
                root=_vr,
            )
            _slider_float_with_exact(
                _fb,
                "sb_residual_support_pct_display",
                "Residual support pct",
                min_value=0.0,
                max_value=25.0,
                step=0.25,
                fmt="%.2f",
                help_text="Manufacturer residual assistance as a percent of vehicle price.", wizard=wizard)
            _slider_range_caption("sb_residual_support_pct_display", wizard=wizard)
            _field_label(
                "Residual push brand program",
                "Whether a manufacturer push program applies residual support for this brand line.",
                wizard=wizard,
                root=_vr,
            )
            st.selectbox(
                "Residual push brand program",
                list(YES_NO),
                key="sb_rv_push_yn",
                label_visibility="collapsed",
                format_func=lambda v: format_yes_no_option("sb_rv_push_yn", v),
                **_input_help("Whether an OEM push program applies residual support for this brand line.", wizard=wizard),
            )

        if wizard:
            render_section_header("Deal structure")
        _dfa, _dfb = _two_cols(wizard)
        with _dfa:
            _field_label(
                "Standard APR (%)",
                "Retail finance rate **before** manufacturer or dealer APR buy-down; "
                "scenarios derive customer APR from this minus rate support.",
                wizard=wizard,
                root=_dfa,
            )
            _slider_float_with_exact(
                _fb,
                "sb_standard_apr",
                "Standard APR",
                min_value=0.5,
                max_value=18.0,
                step=0.001,
                fmt="%.3f",
                help_text=(
                    "Baseline retail APR before support; every scenario subtracts chosen rate buy-down "
                    "from this level."
                ),
                wizard=wizard,
            )
            _slider_range_caption("sb_standard_apr", wizard=wizard)
            _field_label(
                "Primary loan term — baseline context (months)",
                "Term paired with **baseline dealer APR/payment** for the current-offer story; "
                "optimization still considers allowed terms below.",
                wizard=wizard,
                root=_dfa,
            )
            st.selectbox(
                "Primary loan term baseline",
                LOAN_TERMS,
                format_func=lambda m: LOAN_TERM_OPTION_LABELS.get(int(m), f"{int(m)} mo"),
                key="sb_primary_loan_term",
                label_visibility="collapsed",
                **_input_help("Loan term assumed for baseline dealer payment context (must align with quotes).", wizard=wizard),
            )
            _field_label(
                "Baseline dealer APR (%) — current offer",
                "Desk APR **before** additional optimizer-supported buy-down (may differ from standard APR).",
                wizard=wizard,
                root=_dfa,
            )
            _slider_float_with_exact(
                _fb,
                "sb_baseline_dealer_apr",
                "Baseline dealer APR",
                min_value=0.5,
                max_value=18.0,
                step=0.001,
                fmt="%.3f",
                help_text=(
                    "Customer-facing APR quoted today on this finance structure "
                    "(optimizer scenarios subtract further buy-down from standard APR)."
                ),
                wizard=wizard,
            )
            _field_label(
                "Baseline dealer monthly payment ($) — current offer",
                "Monthly payment matching baseline APR on the primary loan term.",
                wizard=wizard,
                root=_dfa,
            )
            _slider_int_with_exact(
                _fb,
                "sb_baseline_dealer_monthly_payment",
                "Baseline dealer monthly payment",
                min_value=150,
                max_value=2200,
                step=5,
                help_text="Desk payment on the baseline APR for the primary loan term.", wizard=wizard)
            _field_label(
                "Vehicle loan amount ($)",
                "Amount financed at the outset of optimization (scenario cash adjusts effective principal).",
                wizard=wizard,
                root=_dfa,
            )
            _slider_int_with_exact(
                _fb,
                "sb_loan_amount",
                "Loan amount",
                min_value=5000,
                max_value=120000,
                step=500,
                help_text=(
                    "Base amount financed — candidate OEM/customer rebates reduce financed balance."
                ),
                wizard=wizard,
            )
            _slider_range_caption("sb_loan_amount", wizard=wizard)
            _field_label(
                "Down payment ($)",
                "Cash from the buyer excluded from financing.",
                wizard=wizard,
                root=_dfa,
            )
            _slider_int_with_exact(
                _fb,
                "sb_down_payment",
                "Down payment",
                min_value=0,
                max_value=60000,
                step=500,
                help_text="Customer cash applied upfront.", wizard=wizard)
            _slider_range_caption("sb_down_payment", wizard=wizard)
        with _dfb:
            _field_label(
                "Allowed loan terms (months)",
                "Optimization will consider every selected term; unchecked terms are omitted from search.",
                wizard=wizard,
                root=_dfb,
            )
            st.multiselect(
                "Loan terms considered",
                LOAN_TERMS,
                default=gv("sb_allowed_loan_terms"),
                format_func=lambda m: LOAN_TERM_OPTION_LABELS.get(
                    int(m), f"{int(m)} mo"
                ),
                key="sb_allowed_loan_terms",
                label_visibility="collapsed",
                **_input_help("Which retail finance terms may appear in the recommended package.", wizard=wizard),
            )
            _field_label(
                "Expected unit margin ($)",
                "Expected rooftop gross per retail unit — used with predicted conversion "
                "and support cost for expected-value ranking.",
                wizard=wizard,
                root=_dfb,
            )
            _slider_int_with_exact(
                _fb,
                "sb_expected_unit_margin",
                "Expected unit margin",
                min_value=500,
                max_value=15000,
                step=50,
                help_text="Frontier gross expectation before counting support economics.", wizard=wizard)
            _slider_range_caption("sb_expected_unit_margin", wizard=wizard)

    elif sec == "dealer_inv":
        _dl, _dr = _two_cols(wizard)
        with _dl:
            _field_label(
                "Dealer size",
                "Relative rooftop scale band used as a coarse capacity signal.",
                wizard=wizard,
                root=_dl,
            )
            st.selectbox(
                "Dealer size",
                DEALER_SIZE_TIERS,
                key="sb_dealer_size_tier",
                label_visibility="collapsed",
                format_func=format_dealer_size_option,
                **_input_help("Relative rooftop scale band used as a coarse capacity signal.", wizard=wizard),
            )
            _field_label(
                "Metro market dealer",
                "Yes if the dealership serves a dense metropolitan market.",
                wizard=wizard,
                root=_dl,
            )
            st.selectbox(
                "Metro market dealer",
                list(YES_NO),
                key="sb_metro_yn",
                label_visibility="collapsed",
                format_func=lambda v: format_yes_no_option("sb_metro_yn", v),
                **_input_help("Yes if the dealership serves a dense metropolitan market.", wizard=wizard),
            )
            _field_label(
                "Average monthly retail units",
                "Rough throughput — retail units sold per month.",
                wizard=wizard,
                root=_dl,
            )
            _slider_int_with_exact(
                _fb,
                "sb_avg_monthly_retail_units",
                "Avg monthly retail units",
                min_value=5,
                max_value=500,
                step=1,
                help_text="Rough throughput — retail units sold per month.", wizard=wizard)
            _slider_range_caption("sb_avg_monthly_retail_units", wizard=wizard)
            _field_label(
                "Dealer margin %",
                "Front-end margin as a percent of revenue — internal economics-style signal.",
                wizard=wizard,
                root=_dl,
            )
            _slider_float_with_exact(
                _fb,
                "sb_dealer_margin_pct_display",
                "Dealer margin pct",
                min_value=0.0,
                max_value=25.0,
                step=0.05,
                fmt="%.2f",
                help_text=(
                    "Front-end margin as a percent of revenue — internal economics-style signal."
                ),
                wizard=wizard,
            )
            _slider_range_caption("sb_dealer_margin_pct_display", wizard=wizard)
            _field_label(
                "Days in inventory",
                "Age of this unit or cohort in inventory days.",
                wizard=wizard,
                root=_dl,
            )
            _slider_int_with_exact(
                _fb,
                "sb_days_in_inventory",
                "Days in inventory",
                min_value=0,
                max_value=250,
                help_text="Age of this unit or cohort in inventory days.", wizard=wizard)
            _slider_range_caption("sb_days_in_inventory", wizard=wizard)
        with _dr:
            _field_label(
                "Units on hand",
                "Physical units available at the dealer for this model line.",
                wizard=wizard,
                root=_dr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_on_hand_units",
                "Units on hand",
                min_value=0,
                max_value=200,
                step=1,
                help_text="Physical units available at the dealer for this model line.", wizard=wizard)
            _slider_range_caption("sb_on_hand_units", wizard=wizard)
            _field_label(
                "Units in transit",
                "Incoming pipeline units not yet ground stock.",
                wizard=wizard,
                root=_dr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_in_transit_units",
                "Units in transit",
                min_value=0,
                max_value=200,
                step=1,
                help_text="Incoming pipeline units not yet ground stock.", wizard=wizard)
            _slider_range_caption("sb_in_transit_units", wizard=wizard)
            _field_label(
                "Aged inventory share %",
                "Share of inventory past your aging threshold — supply pressure signal.",
                wizard=wizard,
                root=_dr,
            )
            _slider_float_with_exact(
                _fb,
                "sb_aging_inventory_pct_display",
                "Aged inventory share",
                min_value=0.0,
                max_value=50.0,
                step=0.05,
                fmt="%.2f",
                help_text="Share of inventory past your aging threshold — supply pressure signal.", wizard=wizard)
            _slider_range_caption("sb_aging_inventory_pct_display", wizard=wizard)
            _field_label(
                "Stockout risk",
                "Yes if you risk running out of popular trims versus demand.",
                wizard=wizard,
                root=_dr,
            )
            st.selectbox(
                "Stockout risk",
                list(YES_NO),
                key="sb_stockout_yn",
                label_visibility="collapsed",
                format_func=lambda v: format_yes_no_option("sb_stockout_yn", v),
                **_input_help("Yes if you risk running out of popular trims versus demand.", wizard=wizard),
            )
            _field_label(
                "Overstock situation",
                "Yes if inventory is heavy versus recent sell-through.",
                wizard=wizard,
                root=_dr,
            )
            st.selectbox(
                "Overstock situation",
                list(YES_NO),
                key="sb_overstock_yn",
                label_visibility="collapsed",
                format_func=lambda v: format_yes_no_option("sb_overstock_yn", v),
                **_input_help("Yes if inventory is heavy versus recent sell-through.", wizard=wizard),
            )
            _field_label(
                "Inventory pressure",
                _help_scale(
                    "Inventory pressure",
                    "Little urgency to move the unit.",
                    "Normal stocking discipline.",
                    "Elevated pressure to retail units.",
                    "Critical — must move vehicles urgently.",
                ),
                wizard=wizard,
                root=_dr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_inventory_pressure_ui",
                "Inventory pressure",
                min_value=1,
                max_value=10,
                help_text="Urgency to retail units given stocking levels and aging (1–10).", wizard=wizard)

            _slider_scale_caption("sb_inventory_pressure_ui", wizard=wizard)
    elif sec == "financing":
        _fl, _fr = _two_cols(wizard)
        with _fl:
            _field_label(
                "Max OEM/customer cash in search ($)",
                "Upper bound scanned in **$500** steps from **$0** (includes OEM rebates shown to shopper).",
                wizard=wizard,
                root=_fl,
            )
            _slider_int_with_exact(
                _fb,
                "sb_max_oem_customer_cash",
                "Max OEM customer cash",
                min_value=0,
                max_value=15000,
                step=500,
                help_text=(
                    "Maximum customer-visible cash the optimizer may consider "
                    "(scenario grid stops at this cap)."
                ),
                wizard=wizard,
            )
            _field_label(
                "Max dealer cash in search ($)",
                "Upper bound for rooftop discretionary cash in **$500** increments.",
                wizard=wizard,
                root=_fl,
            )
            _slider_int_with_exact(
                _fb,
                "sb_max_dealer_cash_support",
                "Max dealer cash support",
                min_value=0,
                max_value=15000,
                step=500,
                help_text="Maximum dealer cash contribution included in Cartesian search.", wizard=wizard)
            _field_label(
                "Max APR / rate support",
                "Ceiling buy-down modeled as **basis points × 100** internal index "
                "(grid steps of **25** from **0**).",
                wizard=wizard,
                root=_fl,
            )
            _sync_slider_session_int(_fb, "sb_max_apr_rate_support")
            st.select_slider(
                "Max APR rate support",
                options=[x for x in SCENARIO_SUBVENTION_BPS if x <= 300],
                format_func=format_dealer_rate_support_bps,
                key="sb_max_apr_rate_support",
                label_visibility="collapsed",
                **_input_help(
                    "Highest rate-buy-down tier allowed; scenarios test every "
                    "25 bp step through this ceiling.",
                    wizard=wizard,
                ),
            )
            _field_label(
                "Allow loyalty incentive",
                "If No, loyalty cash is fixed at zero for every scenario.",
                wizard=wizard,
                root=_fl,
            )
            st.selectbox(
                "Allow loyalty incentive",
                list(YES_NO),
                key="sb_allow_loyalty_incentive",
                label_visibility="collapsed",
                **_input_help("Whether search may allocate OEM/dealer loyalty dollars.", wizard=wizard),
            )
            _field_label(
                "Max loyalty incentive ($)",
                "Honored only when allowance is Yes; swept in **$500** steps.",
                wizard=wizard,
                root=_fl,
            )
            _slider_int_with_exact(
                _fb,
                "sb_max_loyalty_incentive",
                "Max loyalty incentive",
                min_value=0,
                max_value=10000,
                step=500,
                help_text="Cap on loyalty/stackable owner retention incentives.", wizard=wizard)
        with _fr:
            _field_label(
                "Allow conquest incentive",
                "If No, conquest dollars stay at zero everywhere in the grid.",
                wizard=wizard,
                root=_fr,
            )
            st.selectbox(
                "Allow conquest incentive",
                list(YES_NO),
                key="sb_allow_conquest_incentive",
                label_visibility="collapsed",
                **_input_help("Allow switch-in bounty in the optimizer search.", wizard=wizard),
            )
            _field_label(
                "Max conquest incentive ($)",
                "Upper bound scanned in **$500** increments when allowance is Yes.",
                wizard=wizard,
                root=_fr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_max_conquest_incentive",
                "Max conquest incentive",
                min_value=0,
                max_value=10000,
                step=500,
                help_text="Maximum conquest rebate considered.", wizard=wizard)
            _field_label(
                "Max total support budget ($)",
                "Hard ceiling on estimated support economics (APR cost + stacked cash); "
                "scenarios exceeding this fail feasibility for recommendation.",
                wizard=wizard,
                root=_fr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_max_total_support_budget",
                "Max total support budget",
                min_value=1000,
                max_value=50000,
                step=500,
                help_text="Filter for recommendation — rejects packages above this modeled cost.", wizard=wizard)
            _field_label(
                "Minimum acceptable remaining margin ($)",
                "Recommendation requires "
                "**expected_unit_margin − support_cost** ≥ this floor.",
                wizard=wizard,
                root=_fr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_min_acceptable_remaining_margin",
                "Min acceptable remaining margin",
                min_value=0,
                max_value=5000,
                step=50,
                help_text="Protects frontier gross after fully loading support.", wizard=wizard)
            _field_label(
                "Minimum meaningful conversion lift (% points)",
                "Minimum **lift versus no-rate-support** baseline (percentage points); "
                "default **2** filters weak ROI packages.",
                wizard=wizard,
                root=_fr,
            )
            _slider_float_with_exact(
                _fb,
                "sb_min_meaningful_lift_pp",
                "Min meaningful lift pp",
                min_value=0.0,
                max_value=8.0,
                step=0.5,
                fmt="%.2f",
                help_text=(
                    "Feasibility filter on incremental conversion probability "
                    "(vs matched zero-support scenario)."
                ),
                wizard=wizard,
            )

    elif sec == "competitor":
        _cl, _cr = _two_cols(wizard)
        with _cl:
            _field_label(
                "Primary competitor",
                "Benchmark competitor brand you face most often on this deal.",
                wizard=wizard,
                root=_cl,
            )
            st.selectbox(
                "Primary competitor",
                PRIMARY_COMPETITORS,
                key="sb_primary_competitor",
                label_visibility="collapsed",
                format_func=format_primary_competitor_option,
                **_input_help("Benchmark competitor brand you face most often on this deal.", wizard=wizard),
            )
            _field_label(
                "Competing offer APR (%)",
                "Best-estimate APR from the competing store or OEM.",
                wizard=wizard,
                root=_cl,
            )
            _slider_float_with_exact(
                _fb,
                "sb_competitor_apr",
                "Competitor APR",
                min_value=0.5,
                max_value=18.0,
                step=0.001,
                fmt="%.3f",
                help_text="Best-estimate APR from the competing store or OEM.", wizard=wizard)
            _slider_range_caption("sb_competitor_apr", wizard=wizard)
            _field_label(
                "Competing offer monthly payment ($)",
                "Monthly payment on the competitive quote (matching term assumptions as closely as possible).",
                wizard=wizard,
                root=_cl,
            )
            _slider_int_with_exact(
                _fb,
                "sb_competitor_monthly_payment",
                "Competitor monthly payment",
                min_value=150,
                max_value=2200,
                step=5,
                help_text=(
                    "Monthly payment on the competitive quote (match term assumptions where possible)."
                ),
                wizard=wizard,
            )
            _slider_range_caption("sb_competitor_monthly_payment", wizard=wizard)
            _field_label(
                "Competing offer cashback ($)",
                "Cash incentive on the competing offer.",
                wizard=wizard,
                root=_cl,
            )
            _slider_int_with_exact(
                _fb,
                "sb_competitor_cashback",
                "Competitor cashback",
                min_value=0,
                max_value=15000,
                step=100,
                help_text="Cash incentive on the competing offer.", wizard=wizard)
            _slider_range_caption("sb_competitor_cashback", wizard=wizard)
        with _cr:
            _field_label(
                "Competitor offer aggressiveness",
                _help_scale(
                    "Competitor offer aggressiveness",
                    "Competitor offer seems weak or uncompetitive.",
                    "Moderately competitive versus market.",
                    "Aggressive promotion — hard to ignore.",
                    "Extremely aggressive — difficult to match without support.",
                ),
                wizard=wizard,
                root=_cr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_competitor_aggr_ui",
                "Competitor aggressiveness",
                min_value=1,
                max_value=10,
                help_text="How aggressive the competing offer feels versus market (1–10).", wizard=wizard)
            _slider_scale_caption("sb_competitor_aggr_ui", wizard=wizard)
            _field_label(
                "Competitor sales momentum",
                _help_scale(
                    "Competitor sales momentum",
                    "Competitor appears weak or quiet in market.",
                    "Average competitive presence.",
                    "Strong momentum / share gains in your market.",
                    "Dominant momentum — perceived market leader.",
                ),
                wizard=wizard,
                root=_cr,
            )
            _slider_int_with_exact(
                _fb,
                "sb_competitor_sales_ui",
                "Competitor sales momentum",
                min_value=1,
                max_value=10,
                help_text="Perceived competitive strength and momentum in your market (1–10).", wizard=wizard)

            _slider_scale_caption("sb_competitor_sales_ui", wizard=wizard)
    elif sec == "macro":
        _ml, _mr = _two_cols(wizard)
        with _ml:
            _field_label(
                "Fed / benchmark rate (%)",
                "Policy or benchmark short rate — macro financing backdrop.",
                wizard=wizard,
                root=_ml,
            )
            _slider_float_with_exact(
                _fb,
                "sb_fed_rate",
                "Fed rate",
                min_value=0.0,
                max_value=12.0,
                step=0.01,
                fmt="%.2f",
                help_text="Policy or benchmark short rate — macro financing backdrop.", wizard=wizard)
            _slider_range_caption("sb_fed_rate", wizard=wizard)
            _field_label(
                "10-Year Treasury yield (%)",
                "Long-rate anchor often correlated with auto finance curves.",
                wizard=wizard,
                root=_ml,
            )
            _slider_float_with_exact(
                _fb,
                "sb_ten_year",
                "10 year treasury",
                min_value=0.0,
                max_value=12.0,
                step=0.01,
                fmt="%.2f",
                help_text="Long-rate anchor often correlated with auto finance curves.", wizard=wizard)
            _slider_range_caption("sb_ten_year", wizard=wizard)
            _field_label(
                "Inflation rate (CPI %)",
                "Recent CPI-style inflation reading for macro demand/pricing context.",
                wizard=wizard,
                root=_ml,
            )
            _slider_float_with_exact(
                _fb,
                "sb_inflation_cpi",
                "Inflation CPI",
                min_value=0.0,
                max_value=15.0,
                step=0.01,
                fmt="%.2f",
                help_text="Recent CPI-style inflation reading for macro demand/pricing context.", wizard=wizard)
            _slider_range_caption("sb_inflation_cpi", wizard=wizard)
            _field_label(
                "Base auto rate index (%)",
                "Internal or industry base auto finance index.",
                wizard=wizard,
                root=_ml,
            )
            _slider_float_with_exact(
                _fb,
                "sb_base_auto_rate_index",
                "Base auto rate index",
                min_value=0.5,
                max_value=18.0,
                step=0.001,
                fmt="%.3f",
                help_text="Internal or industry base auto finance index.", wizard=wizard)
            _slider_range_caption("sb_base_auto_rate_index", wizard=wizard)
            _field_label(
                "Market auto rate index (%)",
                "Observed market auto rate index for your lane.",
                wizard=wizard,
                root=_ml,
            )
            _slider_float_with_exact(
                _fb,
                "sb_market_rate_index",
                "Market auto rate index",
                min_value=0.5,
                max_value=18.0,
                step=0.001,
                fmt="%.3f",
                help_text="Observed market auto rate index for your lane.", wizard=wizard)
            _slider_range_caption("sb_market_rate_index", wizard=wizard)
        with _mr:
            _field_label(
                "Quote month",
                "Calendar month of the quote — seasonality signal.",
                wizard=wizard,
                root=_mr,
            )
            st.selectbox(
                "Quote month",
                MONTH_OPTIONS,
                format_func=format_quote_month_option,
                key="sb_month_of_quote",
                label_visibility="collapsed",
                **_input_help("Calendar month of the quote — seasonality signal.", wizard=wizard),
            )
            _field_label(
                "Quote day of week",
                "Weekday timing — intra-week retail patterns.",
                wizard=wizard,
                root=_mr,
            )
            st.selectbox(
                "Quote day of week",
                list(range(7)),
                format_func=format_dow_option,
                key="sb_day_of_week_quote",
                label_visibility="collapsed",
                **_input_help("Weekday timing — intra-week retail patterns.", wizard=wizard),
            )
            _field_label(
                "Quarter-end sales push",
                "Yes if OEM or dealer lift is elevated near fiscal quarter end.",
                wizard=wizard,
                root=_mr,
            )
            st.selectbox(
                "Quarter end push",
                list(YES_NO),
                key="sb_quarter_end_yn",
                label_visibility="collapsed",
                format_func=lambda v: format_yes_no_option("sb_quarter_end_yn", v),
                **_input_help("Yes if OEM or dealer lift is elevated near fiscal quarter end.", wizard=wizard),
            )
            _field_label(
                "Sales type",
                "**Retail** — typical showroom sale; **Finance** — installment emphasis; "
                "**Lease** — lease transaction; **Cash** — cash-style structure.",
                wizard=wizard,
                root=_mr,
            )
            st.selectbox(
                "Sales type",
                SALES_TYPES_UI,
                key="sb_sales_type",
                label_visibility="collapsed",
                format_func=format_sales_type_option,
                **_input_help("Retail vs finance vs lease vs cash-style structure.", wizard=wizard),
            )
            _field_label(
                "Region",
                "U.S. sales region for pricing and competitive context.",
                wizard=wizard,
                root=_mr,
            )
            st.selectbox(
                "Region",
                REGIONS,
                key="sb_region",
                label_visibility="collapsed",
                format_func=format_region_option,
                **_input_help("U.S. sales region for pricing and competitive context.", wizard=wizard),
            )
            _field_label(
                "State",
                "State for this quote (subset aligned with synthetic reference data).",
                wizard=wizard,
                root=_mr,
            )
            st.selectbox(
                "State",
                STATES,
                key="sb_state",
                label_visibility="collapsed",
                format_func=format_state_option,
                **_input_help(
                    "State for this quote (subset aligned with synthetic reference data).",
                    wizard=wizard,
                ),
            )

        _exp_adv = st.expander if wizard else st.sidebar.expander
        with _exp_adv("Advanced calibration"):
            _adv_mult_help = (
                "Scales estimated dollar cost of APR and rate support in total support economics "
                "(relative to internal calibration)."
            )
            if wizard:
                st.markdown(
                    '<p style="margin:0 0 0.25rem 0;font-weight:600;font-size:0.9375rem;'
                    'color:#18181b;display:flex;align-items:center;flex-wrap:wrap;gap:0.35rem;">'
                    "Support cost multiplier"
                    f"{_hint(_adv_mult_help)}</p>",
                    unsafe_allow_html=True,
                )
            else:
                _sb_row_label_help(
                    "Support cost multiplier",
                    _adv_mult_help,
                    compact=True,
                )
            _slider_float_with_exact(
                _fb,
                "sb_cost_multiplier",
                "Support cost multiplier",
                min_value=0.25,
                max_value=1.25,
                step=0.05,
                fmt="%.2f",
                help_text=(
                    "Scales estimated dollar cost of APR/rate support in total support economics."
                ),
                wizard=wizard,
            )
            _slider_range_caption("sb_cost_multiplier", wizard=wizard)


def schema_column_diagnostics(
    schema: dict[str, Any],
    row_model: dict[str, Any] | None,
    model_df: pd.DataFrame | None,
) -> tuple[list[str], list[str]]:
    req = set(schema["required_columns"])
    if model_df is not None:
        cols = set(model_df.columns)
        return sorted(req - cols), sorted(cols - req)
    if row_model is not None:
        rk = set(row_model.keys())
        return sorted(req - rk), sorted(rk - req)
    return [], []


def render_prediction_error(
    exc: Exception,
    schema: dict[str, Any],
    row_model: dict[str, Any] | None,
    model_df: pd.DataFrame | None,
) -> None:
    miss, extra = schema_column_diagnostics(schema, row_model, model_df)
    st.error(f"**Prediction failed:** {exc}")
    st.subheader("Exception message")
    st.code(str(exc))
    if model_df is not None:
        st.subheader("Final model dataframe")
        st.dataframe(model_df, use_container_width=True)
    st.subheader("Column diagnostics")
    st.markdown("**Missing columns (vs schema):**")
    st.write(miss if miss else "— none —")
    st.markdown("**Extra columns (vs schema):**")
    st.write(extra if extra else "— none —")
    with st.expander("Full traceback"):
        st.exception(exc)


def format_offer_simulator_display(enriched: pd.DataFrame) -> pd.DataFrame:
    """Business-facing columns only (scenario comparison table)."""
    out = enriched.copy()
    out = out.rename(
        columns={
            "dealer_rate_support_level": "Dealer Rate Support Level",
            "scenario_dealer_apr": "Dealer APR",
            "scenario_dealer_monthly_payment": "Dealer Monthly Payment",
            "conversion_probability": "Predicted Conversion Probability",
            "conversion_lift_vs_no_support": "Conversion Lift vs No Support",
            "estimated_support_cost": "Estimated Support Cost",
            "incremental_conversion_gain": "Incremental Conversion Gain",
            "incremental_support_cost": "Incremental Support Cost",
            "support_cost_per_conversion_point": "Cost per Conversion Point",
            "efficiency_score": "Efficiency Score",
        }
    )
    drop_cols = [
        c
        for c in (
            "rate_support_tier",
            "apr_gap_bps",
        )
        if c in out.columns
    ]
    out = out.drop(columns=drop_cols, errors="ignore")
    return out


SIMULATOR_CHART_AXIS_HELP = {
    "conversion": """### What this chart answers
“If we only move **dealer rate support** up or down—holding your other inputs fixed—what happens to **predicted close rate**?”

---

### Term glossary (single-lever sweep)

| Term | Meaning |
|------|---------|
| **Dealer rate support level** | Simulator index for APR buy-down / rate subsidy on this sweep (same ladder on all three charts). Higher = stronger rate support in the quote. |
| **Predicted conversion** | Modeled probability (0–100%) that the shopper accepts **this** financing offer—not a guarantee. |

---

### Axes
**Across** — Dealer rate support level (the knob we’re sweeping).

**Up** — Predicted conversion probability.

### Tip
Compare slopes: where does conversion rise fastest as support increases?

---

### Note
This is the **legacy single-lever** view (rate support only). Your **Offer recommendation** tab uses the full multi-lever search.""",
    "support_cost": """### What this chart answers
“At each **rate-support step**, what are the **total modeled incentive dollars** for that scenario?”

---

### Costs: total vs monthly (read this first)

**Estimated support cost is NOT a monthly payment.** It is **one modeled snapshot of total incentive economics for that scenario**, in **dollars**, before you interpret ROI:

1. **Rate-buy-down piece** — `loan amount × (support level ÷ 10,000) × calibration multiplier` — a **directional** dollar estimate of financing the APR subsidy (not GAAP interest expense).
2. **Cash stack** — OEM/customer-visible cash + dealer + loyalty + conquest rebates included in that scenario (dollars).

So the **Y-axis is total modeled deal support ($)** for that grid point—**not** “per month,” **not** customer payment, **not** accounting-grade cost.

Tune calibration via **Advanced calibration → Support cost multiplier** if spreads don’t match your desk.

---

### Term glossary

| Term | Meaning |
|------|---------|
| **Estimated total support ($)** | Sum of the modeled rate-buy-down cost component **plus** stacked cash rebates for that scenario—**one total snapshot**, not recurring monthly. |
| **Dealer rate support level** | Same horizontal axis as the other two charts—position on the APR subsidy ladder. |

---

### Axes
**Across** — Dealer rate support level.

**Up** — Estimated **total** modeled support ($), single snapshot—**not monthly**.

### Tip
Use with the **conversion** chart: if dollars climb fast but conversion barely moves, you’re past diminishing returns.""",
    "efficiency": """### What this chart answers
“Where along the ladder do we get the **most conversion lift per dollar** of **estimated total support**?”

---

### Term glossary

| Term | Meaning |
|------|---------|
| **Efficiency score** | **(conversion lift vs. zero rate support × 100) ÷ max(estimated total support ÷ 1,000, 0.01)**. **Lift** here is extra predicted conversion versus **no** APR subsidy at the **same cash stack** on this sweep—higher score = more uplift per modeled dollar of **total** support (again: **not** a monthly figure). |
| **Estimated total support** | Same dollar definition as the middle chart—one modeled snapshot combining rate-buy-down estimate + cash (see that chart’s guide). |
| **Dealer rate support level** | Same horizontal ladder as the other charts. |

---

### Axes
**Across** — Dealer rate support level.

**Up** — Efficiency score (unitless index—use for **relative** comparison along the ladder).

### Tip
Spikes can reflect math sensitivity when support dollars are tiny—cross-check the middle chart’s **dollar scale** and the left chart’s **conversion**.""",
}

SIMULATOR_CHART_BLURBS = {
    "conversion": (
        "**Predicted close rate (up)** vs **rate-support step (across)** — cash stack fixed for this legacy sweep."
    ),
    "support_cost": (
        "**Total modeled incentive dollars per scenario (up)** — **not** monthly payment; "
        "open the title **?** for the dollar formula."
    ),
    "efficiency": (
        "**Lift per thousand dollars of modeled total support** — relative score along the ladder; "
        "open the title **?** for the efficiency definition."
    ),
}

SIMULATOR_CHART_TITLE_HINT = {
    "conversion": (
        "**Across:** dealer rate support level (single knob swept). **Up:** predicted conversion (`predict_proba`). "
        "**How:** only rate support moves—cash and other inputs fixed at your quote. **Why:** legacy single-lever "
        "sanity check before trusting the multi-lever optimizer."
    ),
    "support_cost": (
        "**Across:** dealer rate support level. **Up:** estimated total modeled support (USD). "
        "**How:** `loan × (support ÷ 10,000) × calibration multiplier` **+** stacked OEM/dealer/loyalty/conquest cash "
        "for that grid point. **Why:** dollars drive budget and net-deal math—not customer monthly payment."
    ),
    "efficiency": (
        "**Across:** dealer rate support level. **Up:** efficiency score from this sweep. "
        "**How:** `(conversion lift vs zero rate support × 100) ÷ max(estimated support ÷ 1,000, 0.01)` — "
        "same lift definition as enrichment on the single-lever ladder. **Why:** spot where lift per modeled dollar peaks."
    ),
}

OFFER_ANALYTICS_TITLE_HINT = {
    "incentive_ladder": (
        "**Across:** total modeled support per scenario (APR buy-down estimate + cash). **Up:** predicted conversion. "
        "**How:** points sorted by support; smoothed line shows trajectory; green = recommended package. **Why:** see "
        "where extra subsidy stops buying meaningful close rate."
    ),
    "diminishing_returns": (
        "**Across:** total support cost. **Up:** incremental conversion vs the **next-cheaper** scenario (percentage points). "
        "**How:** sorted ladder diffs; shaded bands flag efficient vs overspending zones. **Why:** locate diminishing returns on spend."
    ),
    "support_breakdown": (
        "**Bars:** share of total modeled support for the **recommended** package—APR buy-down vs each cash stack. "
        "**How:** same cost split logic as total support (multiplier on rate piece). **Why:** see whether the desk is APR-led vs cash-led."
    ),
}


OFFER_ANALYTICS_CHART_HELP = {
    "incentive_ladder": """### Incentive ladder (primary chart)

**Across** — Total modeled support for each searched package (**not** the customer’s monthly payment): APR buy-down estimate plus OEM/customer, dealer, loyalty, and conquest cash.

**Up** — Predicted conversion probability for that package.

**Curve** — Points sorted by support cost; the line uses a **smoothed** conversion track so you can see the overall **shape** (steep gains vs flattening).

**Green highlight** — The **recommended efficient offer** after your feasibility filters.

**Use it to decide** where extra dollars stop buying meaningful close-rate improvement.""",
    "support_breakdown": """### Support allocation

Shows **how dollars split** between APR subsidy vs stacked cash components for the **recommended** package.

Percentages are **shares of total modeled support** for that scenario.""",
    "diminishing_returns": """### Diminishing returns

**Across** — Total modeled support ($).

**Up** — **Incremental** predicted conversion vs the **previous cheaper** scenario along the sorted ladder (percentage points).

**Bands** — **Efficient** (green) through recommended spend; **moderate** diminishing returns (amber); **overspending** (red) where extra dollars buy little extra conversion.

Early steep gains and later flattening indicate where to stop subsidizing.""",
}


def render_exploration_chart_card(
    title: str,
    guide_one_liner: str,
    detail_markdown: str,
    chart: alt.Chart,
    *,
    analytics_key: str,
) -> None:
    """Bordered card: title + inline **?** (axes / how calculated) + Quick read with rendered bold."""
    try:
        shell = st.container(border=True)
    except TypeError:
        shell = st.container()
    with shell:
        title_hint = OFFER_ANALYTICS_TITLE_HINT.get(analytics_key, "")
        title_html = (
            f'<p class="exec-chart-title-main" style="display:flex;align-items:center;gap:0.35rem;'
            f'flex-wrap:wrap;margin:0 0 0.35rem 0;">'
            f"{html.escape(title)}{_hint(title_hint) if title_hint else ''}</p>"
        )
        st.markdown(title_html, unsafe_allow_html=True)
        # Popover (not expander): charts may render inside another expander — Streamlit forbids nested expanders.
        with st.popover("Full chart guide — axes, glossary & tips"):
            st.markdown(detail_markdown)
        qr = _inline_md_bold_to_html(guide_one_liner)
        st.markdown(
            f'<p class="exec-chart-guide"><strong>Quick read:</strong> {qr}</p>',
            unsafe_allow_html=True,
        )
        st.altair_chart(chart, use_container_width=True)


def render_simulator_chart_with_axis_help(
    title: str,
    help_key: str,
    chart: alt.Chart,
) -> None:
    """Chart title + inline **?**; Quick read renders **bold**; full axis guide in expander."""
    try:
        outer = st.container(border=True)
    except TypeError:
        outer = st.container()
    with outer:
        th = SIMULATOR_CHART_TITLE_HINT.get(help_key, "")
        st.markdown(
            f'<p class="exec-chart-title-main" style="font-size:0.98rem !important;display:flex;'
            f'align-items:center;gap:0.35rem;flex-wrap:wrap;margin:0 0 0.35rem 0;">'
            f"{html.escape(title)}{_hint(th) if th else ''}</p>",
            unsafe_allow_html=True,
        )
        # Popover (not expander): APR-only charts sit inside `APR-only sensitivity (reference)` expander.
        with st.popover("Full chart guide — axes, glossary & tips"):
            st.markdown(SIMULATOR_CHART_AXIS_HELP[help_key])
        qr = _inline_md_bold_to_html(SIMULATOR_CHART_BLURBS[help_key])
        st.markdown(
            f'<p class="exec-chart-guide"><strong>Quick read:</strong> {qr}</p>',
            unsafe_allow_html=True,
        )
        st.altair_chart(chart, use_container_width=False)


def chart_conversion_by_support(
    sim_df: pd.DataFrame,
    highlight_support_level: int | None = None,
) -> alt.Chart:
    df = sim_df.assign(
        support_level=sim_df["dealer_rate_support_level"].astype(int),
        tier=sim_df["rate_support_tier"],
    )
    x_enc = alt.X(
        "support_level:O",
        title="Dealer Rate Support Level",
        sort=list(SCENARIO_SUBVENTION_BPS),
        axis=alt.Axis(labelAngle=-45, labelColor="#52525b", titleColor="#3f3f46"),
    )
    y_enc = alt.Y(
        "conversion_probability:Q",
        title="Predicted Conversion Probability",
        axis=alt.Axis(format=".0%", labelColor="#52525b", titleColor="#3f3f46"),
        scale=alt.Scale(domain=[0, 1]),
    )
    tip = [
        alt.Tooltip("tier:N", title="Scenario"),
        alt.Tooltip("conversion_probability:Q", title="P(convert)", format=".1%"),
        alt.Tooltip("scenario_dealer_apr:Q", title="Dealer APR", format=".2f"),
    ]
    line = (
        alt.Chart(df)
        .mark_line(
            stroke=_EXEC_CHART_SERIES_LINE,
            strokeWidth=2.5,
            interpolate="monotone",
            strokeCap="round",
            strokeJoin="round",
        )
        .encode(x=x_enc, y=y_enc)
    )
    if highlight_support_level is not None:
        hl = int(highlight_support_level)
        hi = df[df["support_level"] == hl].assign(
            _highlight_note="Recommended efficient scenario"
        )
        lo = df[df["support_level"] != hl]
        pts_lo = (
            alt.Chart(lo)
            .mark_circle(
                size=58,
                color=_EXEC_CHART_POINT_MUTED,
                stroke=_EXEC_CHART_POINT_MUTED_STROKE,
                strokeWidth=1,
                opacity=0.92,
            )
            .encode(x=x_enc, y=y_enc, tooltip=tip)
        )
        tip_hi = tip + [
            alt.Tooltip("_highlight_note:N", title="Chart highlight"),
        ]
        pts_hi = (
            alt.Chart(hi)
            .mark_circle(
                size=132,
                color=_EXEC_CHART_REC_FILL,
                stroke=_EXEC_CHART_REC_STROKE,
                strokeWidth=2,
                opacity=0.97,
            )
            .encode(x=x_enc, y=y_enc, tooltip=tip_hi)
        )
        chart = line + pts_lo + pts_hi
    else:
        pts = (
            alt.Chart(df)
            .mark_circle(
                size=64,
                color=_EXEC_CHART_SINGLE_FALLBACK,
                stroke=_EXEC_CHART_POINT_MUTED_STROKE,
                strokeWidth=1,
                opacity=0.88,
            )
            .encode(x=x_enc, y=y_enc, tooltip=tip)
        )
        chart = line + pts

    return _finalize_exec_altair(
        chart.properties(
            width=_SIM_SINGLE_LEVER_CHART_W,
            height=_SIM_SINGLE_LEVER_CHART_H,
            background=_EXEC_CHART_PANEL_BG,
        )
    )


def chart_support_cost_by_support(
    sim_df: pd.DataFrame,
    highlight_support_level: int | None = None,
) -> alt.Chart:
    df = sim_df.assign(support_level=sim_df["dealer_rate_support_level"].astype(int))
    x_enc = alt.X(
        "support_level:O",
        title="Dealer Rate Support Level",
        sort=list(SCENARIO_SUBVENTION_BPS),
        axis=alt.Axis(labelAngle=-45, labelColor="#52525b", titleColor="#3f3f46"),
    )
    y_enc = alt.Y(
        "estimated_support_cost:Q",
        axis=alt.Axis(
            title=[
                "Est. total support ($)",
                "(modeled deal snapshot · not monthly)",
            ],
            format=",.0f",
            labelColor="#52525b",
            titleColor="#3f3f46",
        ),
    )
    tip = [
        alt.Tooltip("estimated_support_cost:Q", title="Est. support cost", format=",.0f"),
        alt.Tooltip("rate_support_tier:N", title="Scenario"),
    ]
    line = (
        alt.Chart(df)
        .mark_line(
            stroke=_EXEC_CHART_SERIES_LINE,
            strokeWidth=2.5,
            interpolate="monotone",
            strokeCap="round",
            strokeJoin="round",
        )
        .encode(x=x_enc, y=y_enc)
    )
    if highlight_support_level is not None:
        hl = int(highlight_support_level)
        hi = df[df["support_level"] == hl].assign(
            _highlight_note="Recommended efficient scenario"
        )
        lo = df[df["support_level"] != hl]
        pts_lo = (
            alt.Chart(lo)
            .mark_circle(
                size=58,
                color=_EXEC_CHART_POINT_MUTED,
                stroke=_EXEC_CHART_POINT_MUTED_STROKE,
                strokeWidth=1,
                opacity=0.92,
            )
            .encode(x=x_enc, y=y_enc, tooltip=tip)
        )
        pts_hi = (
            alt.Chart(hi)
            .mark_circle(
                size=132,
                color=_EXEC_CHART_REC_FILL,
                stroke=_EXEC_CHART_REC_STROKE,
                strokeWidth=2,
                opacity=0.97,
            )
            .encode(
                x=x_enc,
                y=y_enc,
                tooltip=tip + [alt.Tooltip("_highlight_note:N", title="Chart highlight")],
            )
        )
        chart = line + pts_lo + pts_hi
    else:
        pts = (
            alt.Chart(df)
            .mark_circle(
                size=64,
                color=_EXEC_CHART_SINGLE_FALLBACK,
                stroke=_EXEC_CHART_POINT_MUTED_STROKE,
                strokeWidth=1,
                opacity=0.88,
            )
            .encode(x=x_enc, y=y_enc, tooltip=tip)
        )
        chart = line + pts

    return _finalize_exec_altair(
        chart.properties(
            width=_SIM_SINGLE_LEVER_CHART_W,
            height=_SIM_SINGLE_LEVER_CHART_H,
            background=_EXEC_CHART_PANEL_BG,
        )
    )


def chart_efficiency_by_support(
    sim_df: pd.DataFrame,
    highlight_support_level: int | None = None,
) -> alt.Chart:
    df = sim_df.copy()
    if "efficiency_score" not in df.columns and "efficient_offer_score" in df.columns:
        df["efficiency_score"] = df["efficient_offer_score"]
    df = df.assign(support_level=df["dealer_rate_support_level"].astype(int))
    x_enc = alt.X(
        "support_level:O",
        title="Dealer Rate Support Level",
        sort=list(SCENARIO_SUBVENTION_BPS),
        axis=alt.Axis(labelAngle=-45, labelColor="#52525b", titleColor="#3f3f46"),
    )
    y_enc = alt.Y(
        "efficiency_score:Q",
        axis=alt.Axis(
            title=["Efficiency score", "(compare within this sweep only)"],
            format=".4f",
            labelColor="#52525b",
            titleColor="#3f3f46",
        ),
    )
    tip = [
        alt.Tooltip("efficiency_score:Q", title="Efficiency score", format=".6f"),
        alt.Tooltip("conversion_probability:Q", title="P(convert)", format=".1%"),
    ]
    line = (
        alt.Chart(df)
        .mark_line(
            stroke=_EXEC_CHART_SERIES_LINE,
            strokeWidth=2.5,
            interpolate="monotone",
            strokeCap="round",
            strokeJoin="round",
        )
        .encode(x=x_enc, y=y_enc)
    )
    if highlight_support_level is not None:
        hl = int(highlight_support_level)
        hi = df[df["support_level"] == hl].assign(
            _highlight_note="Recommended efficient scenario"
        )
        lo = df[df["support_level"] != hl]
        pts_lo = (
            alt.Chart(lo)
            .mark_circle(
                size=58,
                color=_EXEC_CHART_POINT_MUTED,
                stroke=_EXEC_CHART_POINT_MUTED_STROKE,
                strokeWidth=1,
                opacity=0.92,
            )
            .encode(x=x_enc, y=y_enc, tooltip=tip)
        )
        pts_hi = (
            alt.Chart(hi)
            .mark_circle(
                size=132,
                color=_EXEC_CHART_REC_FILL,
                stroke=_EXEC_CHART_REC_STROKE,
                strokeWidth=2,
                opacity=0.97,
            )
            .encode(
                x=x_enc,
                y=y_enc,
                tooltip=tip + [alt.Tooltip("_highlight_note:N", title="Chart highlight")],
            )
        )
        chart = line + pts_lo + pts_hi
    else:
        pts = (
            alt.Chart(df)
            .mark_circle(
                size=64,
                color=_EXEC_CHART_SINGLE_FALLBACK,
                stroke=_EXEC_CHART_POINT_MUTED_STROKE,
                strokeWidth=1,
                opacity=0.88,
            )
            .encode(x=x_enc, y=y_enc, tooltip=tip)
        )
        chart = line + pts

    return _finalize_exec_altair(
        chart.properties(
            width=_SIM_SINGLE_LEVER_CHART_W,
            height=_SIM_SINGLE_LEVER_CHART_H,
            background=_EXEC_CHART_PANEL_BG,
        )
    )


def apr_support_cost_component(row: pd.Series, cost_multiplier: float) -> float:
    la = float(row["scenario_loan_amount"])
    sup = float(row["dealer_rate_support_level"])
    return la * (sup / 10000.0) * float(cost_multiplier)


def support_package_label(row: pd.Series) -> str:
    bps = int(row["dealer_rate_support_level"])
    parts: list[str] = [f"{bps} bps APR"]
    cc = float(row["customer_cash"])
    dc = float(row["dealer_cash"])
    lc = float(row["loyalty_cash"])
    cq = float(row["conquest_cash"])
    if cc >= 1.0:
        parts.append(f"OEM ${cc:,.0f}")
    if dc >= 1.0:
        parts.append(f"Dealer ${dc:,.0f}")
    if lc >= 1.0:
        parts.append(f"Loyalty ${lc:,.0f}")
    if cq >= 1.0:
        parts.append(f"Conquest ${cq:,.0f}")
    parts.append(f"{int(row['loan_term'])} mo")
    return " · ".join(parts)


def overspend_support_hint_cost(df: pd.DataFrame, rec_cost: float) -> float | None:
    """Support $ where marginal conversion gains along the cost ladder first taper (exec narrative)."""
    d = df.sort_values("estimated_support_cost").reset_index(drop=True)
    if len(d) < 6:
        return None
    d["marginal_pp"] = d["conversion_probability"].astype(float).diff() * 100.0
    post = d[d["estimated_support_cost"].astype(float) > float(rec_cost) + 1e-6]
    if post.empty:
        return None
    for _, r in post.iterrows():
        mp = r["marginal_pp"]
        if pd.notna(mp) and float(mp) < 0.12:
            return float(r["estimated_support_cost"])
    return float(d["estimated_support_cost"].quantile(0.82))


def prepare_incentive_ladder_data(df: pd.DataFrame, rec: pd.Series) -> pd.DataFrame:
    d = df.copy()
    d["_is_rec"] = scenario_rows_match(rec, d).values
    d = d.sort_values("estimated_support_cost").reset_index(drop=True)
    d["conversion_pct"] = d["conversion_probability"].astype(float) * 100.0
    n = len(d)
    w = max(3, min(21, max(n // 25, 3)))
    d["conversion_pct_smooth"] = d["conversion_pct"].rolling(
        window=w, center=True, min_periods=1
    ).mean()
    d["rebate_package"] = d.apply(support_package_label, axis=1)
    return d


def chart_incentive_ladder(
    df: pd.DataFrame,
    rec: pd.Series,
    cost_multiplier: float,
) -> alt.Chart:
    _ = cost_multiplier  # reserved if future tooltip adds APR cost split
    d = prepare_incentive_ladder_data(df, rec)
    rec_df = d[d["_is_rec"]].head(1)
    if rec_df.empty:
        idx = (d["estimated_support_cost"] - float(rec["estimated_support_cost"])).abs().idxmin()
        rec_df = d.loc[[idx]].assign(_is_rec=True)
    line = (
        alt.Chart(d)
        .mark_line(
            stroke=_EXEC_CHART_SERIES_LINE,
            strokeWidth=3,
            interpolate="monotone",
            strokeCap="round",
        )
        .encode(
            x=alt.X(
                "estimated_support_cost:Q",
                title="Total support cost ($)",
                axis=alt.Axis(format=",.0f"),
            ),
            y=alt.Y(
                "conversion_pct_smooth:Q",
                title="Predicted conversion (%)",
                scale=alt.Scale(domain=[0, 100]),
            ),
        )
    )
    pts_rec = (
        alt.Chart(rec_df)
        .mark_circle(
            size=160,
            color=_EXEC_CHART_REC_FILL,
            stroke=_EXEC_CHART_REC_STROKE,
            strokeWidth=2.5,
            opacity=0.95,
        )
        .encode(
            x="estimated_support_cost:Q",
            y="conversion_pct:Q",
            tooltip=[
                alt.Tooltip("estimated_support_cost:Q", title="Total support ($)", format=",.0f"),
                alt.Tooltip("conversion_pct:Q", title="Predicted conversion (%)", format=".1f"),
                alt.Tooltip("scenario_dealer_apr:Q", title="Dealer APR (%)", format=".3f"),
                alt.Tooltip(
                    "scenario_dealer_monthly_payment:Q",
                    title="Monthly payment ($)",
                    format=",.0f",
                ),
                alt.Tooltip("rebate_package:N", title="Rebate package"),
            ],
        )
    )
    lbl = (
        alt.Chart(rec_df)
        .mark_text(
            align="left",
            dx=10,
            dy=-12,
            fontSize=11,
            fontWeight=600,
            color="#0f766e",
        )
        .encode(
            x="estimated_support_cost:Q",
            y="conversion_pct:Q",
            text=alt.value("Recommended efficient offer"),
        )
    )
    rest_df = d[~d["_is_rec"]]
    if len(rest_df) > 0:
        pts_muted = (
            alt.Chart(rest_df)
            .mark_circle(
                size=36,
                color=_EXEC_CHART_POINT_MUTED,
                stroke=_EXEC_CHART_POINT_MUTED_STROKE,
                strokeWidth=0.6,
                opacity=0.45,
            )
            .encode(
                x="estimated_support_cost:Q",
                y="conversion_pct:Q",
                tooltip=[
                    alt.Tooltip("estimated_support_cost:Q", title="Total support ($)", format=",.0f"),
                    alt.Tooltip("conversion_pct:Q", title="Predicted conversion (%)", format=".1f"),
                    alt.Tooltip("scenario_dealer_apr:Q", title="Dealer APR (%)", format=".3f"),
                    alt.Tooltip(
                        "scenario_dealer_monthly_payment:Q",
                        title="Monthly payment ($)",
                        format=",.0f",
                    ),
                    alt.Tooltip("rebate_package:N", title="Rebate package"),
                ],
            )
        )
        chart_body = line + pts_muted + pts_rec + lbl
    else:
        chart_body = line + pts_rec + lbl
    return _finalize_exec_altair(
        chart_body.properties(
            height=380,
            width=760,
            background=_EXEC_CHART_PANEL_BG,
            title=alt.TitleParams(
                text="Incentive ladder — conversion vs total support",
                subtitle=[
                    "Smoothed curve shows overall trajectory; green point = recommended package "
                    "(total modeled support is not monthly payment)"
                ],
                fontSize=15,
                subtitleFontSize=11,
                subtitleColor="#64748b",
            ),
        )
    )


def chart_support_breakdown_recommended(rec: pd.Series, cost_multiplier: float) -> alt.Chart:
    apr_c = apr_support_cost_component(rec, cost_multiplier)
    rows = [
        {"component": "APR support", "dollars": apr_c},
        {"component": "OEM / customer cash", "dollars": float(rec["customer_cash"])},
        {"component": "Dealer cash", "dollars": float(rec["dealer_cash"])},
        {"component": "Loyalty incentive", "dollars": float(rec["loyalty_cash"])},
        {"component": "Conquest incentive", "dollars": float(rec["conquest_cash"])},
    ]
    plot_df = pd.DataFrame([r for r in rows if float(r["dollars"]) >= 0.5])
    if plot_df.empty:
        plot_df = pd.DataFrame([{"component": "APR support", "dollars": 0.0}])
    total = float(plot_df["dollars"].sum())
    plot_df["pct"] = plot_df["dollars"] / max(total, 1.0) * 100.0
    plot_df = plot_df.iloc[::-1].reset_index(drop=True)
    order = plot_df["component"].tolist()
    tip = [
        alt.Tooltip("component:N", title="Component"),
        alt.Tooltip("dollars:Q", title="Amount ($)", format=",.0f"),
        alt.Tooltip("pct:Q", title="Share of total (%)", format=".1f"),
    ]
    return _finalize_exec_altair(
        alt.Chart(plot_df)
        .mark_bar()
        .encode(
            x=alt.X("dollars:Q", title="Dollars ($)", axis=alt.Axis(format=",.0f")),
            y=alt.Y("component:N", sort=order, title=""),
            color=alt.Color("component:N", legend=None),
            tooltip=tip,
        )
        .properties(
            height=max(160, 38 * len(plot_df)),
            width=720,
            background=_EXEC_CHART_PANEL_BG,
            title=alt.TitleParams(
                text="Support allocation — recommended package",
                subtitle=["Share of total modeled support for the recommended scenario"],
                fontSize=14,
                subtitleFontSize=11,
                subtitleColor="#64748b",
            ),
        )
    )


def chart_diminishing_returns(
    df: pd.DataFrame,
    rec: pd.Series,
) -> alt.Chart:
    d = df.sort_values("estimated_support_cost").reset_index(drop=True)
    d["incremental_conv_pp"] = d["conversion_probability"].astype(float).diff() * 100.0
    plot_pts = d.iloc[1:].copy()
    rec_cost = float(rec["estimated_support_cost"])
    c_max = float(d["estimated_support_cost"].max())
    c_tail = overspend_support_hint_cost(df, rec_cost)
    c2 = float(c_tail) if c_tail is not None else min(rec_cost * 1.4, c_max)
    c2 = min(max(c2, rec_cost + 1.0), c_max)
    bands = pd.DataFrame(
        [
            {"x1": 0.0, "x2": rec_cost, "zone": "Efficient support"},
            {"x1": rec_cost, "x2": c2, "zone": "Moderate diminishing returns"},
            {"x1": c2, "x2": c_max, "zone": "Overspending / low efficiency"},
        ]
    )
    rect = (
        alt.Chart(bands)
        .mark_rect(opacity=0.18)
        .encode(
            x=alt.X("x1:Q", title="Total support cost ($)"),
            x2="x2:Q",
            color=alt.Color(
                "zone:N",
                legend=alt.Legend(title=None, orient="bottom"),
                scale=alt.Scale(
                    domain=[
                        "Efficient support",
                        "Moderate diminishing returns",
                        "Overspending / low efficiency",
                    ],
                    range=["#bbf7d0", "#fef08a", "#fecaca"],
                ),
            ),
        )
    )
    line = (
        alt.Chart(plot_pts)
        .mark_line(
            color="#475569",
            strokeWidth=2,
            interpolate="monotone",
        )
        .encode(
            x=alt.X("estimated_support_cost:Q", axis=alt.Axis(format=",.0f")),
            y=alt.Y(
                "incremental_conv_pp:Q",
                title="Incremental conversion (pp vs prior step)",
            ),
        )
    )
    pts = (
        alt.Chart(plot_pts)
        .mark_circle(size=45, color="#64748b", stroke="#fff", strokeWidth=0.5, opacity=0.75)
        .encode(
            x="estimated_support_cost:Q",
            y="incremental_conv_pp:Q",
            tooltip=[
                alt.Tooltip("estimated_support_cost:Q", title="Support ($)", format=",.0f"),
                alt.Tooltip(
                    "incremental_conv_pp:Q",
                    title="Incremental conversion (pp)",
                    format=".2f",
                ),
            ],
        )
    )
    rec_line = alt.Chart(pd.DataFrame({"x": [rec_cost]})).mark_rule(
        color=_EXEC_CHART_REC_STROKE, strokeWidth=2, strokeDash=[4, 3]
    ).encode(x="x:Q")
    chart = rect + line + pts + rec_line
    return _finalize_exec_altair(
        chart.properties(
            height=340,
            width=760,
            background=_EXEC_CHART_PANEL_BG,
            title=alt.TitleParams(
                text="Diminishing returns — incremental lift along the ladder",
                subtitle=[
                    "Sorted scenarios: each point is lift vs the next-cheaper package in the search"
                ],
                fontSize=14,
                subtitleFontSize=11,
                subtitleColor="#64748b",
            ),
        )
    )


# Tooltips for “Top scenarios by net deal outcome” — Streamlit column header (?) popovers.
_NET_DEAL_SCENARIO_COLUMN_HELP: dict[str, str] = {
    "Support Package": (
        "**How:** Built from this row’s **bps buy-down**, each **cash stack** piece shown only if ≥ $1, "
        "and **loan term** (`support_package_label`). **Why:** gives a scannable handle for a grid row "
        "without opening raw lever columns."
    ),
    "Dealer APR": (
        "**How:** `max(0.5%, standard_apr − dealer_rate_support_level/100)` after applying that row’s "
        "buy-down. **Why:** customer-facing rate drives payment and model features for that scenario."
    ),
    "Monthly Payment": (
        "**How:** Standard amortization on this row’s **scenario loan amount**, **Dealer APR**, and "
        "**Loan Term**. **Why:** matches what appears on a desk quote for that structure."
    ),
    "Loan Term": (
        "**How:** Taken from the multi-lever grid / optimizer for that scenario. **Why:** term changes "
        "payment, baseline conversion at zero incentive, and feasibility checks."
    ),
    "OEM Cash": (
        "**How:** Optimizer-selected OEM/customer rebate dollars on this row (input lever). **Why:** cash "
        "is additive to total modeled support and reduces financed principal vs baseline when applicable."
    ),
    "Dealer Contribution": (
        "**How:** Dealer cash component for this row. **Why:** counts toward total support and model cash "
        "features."
    ),
    "Loyalty Incentive": (
        "**How:** Loyalty rebate dollars for this row. **Why:** same as other cash levers—stacked into "
        "total support."
    ),
    "Conquest Incentive": (
        "**How:** Conquest rebate dollars for this row. **Why:** same—full incentive snapshot for the "
        "scenario."
    ),
    "Total Support Cost": (
        "**How:** `loan_amount × (support_level ÷ 10,000) × support_cost_multiplier` **+** OEM + dealer + "
        "loyalty + conquest cash for this row (`estimate_support_cost` path). **Why:** single dollar score "
        "for incentive load vs budget and margin floors—not monthly payment."
    ),
    "Predicted Conversion": (
        "**How:** Classifier `predict_proba` positive class after `calculate_model_features` → "
        "`align_to_schema`. **Why:** drives ranking with economics—same definition across dashboard."
    ),
    "Remaining Margin": (
        "**How:** Your **expected unit margin** input **minus** **Total Support Cost** for this row. "
        "**Why:** quick directional gross after incentives for desk trade-offs (not GAAP)."
    ),
    "Net Deal Outcome ($)": (
        "**How:** `expected_value` = **Predicted Conversion × expected unit margin − Total Support Cost**. "
        "**Why:** expected-value style ranking—weights margin by chance to close and subtracts all modeled "
        "incentive dollars; primary objective for the recommended package."
    ),
    "Support Efficiency": (
        "**How:** `(conversion probability lift vs no-incentive baseline at same term) ÷ max(total "
        "support cost, 1 USD)` — `efficiency_score` in code. **Why:** highlights lift bought per dollar "
        "of modeled support."
    ),
    "Recommendation Status": (
        "**How:** Row matches the **constrained** optimizer’s chosen package → “Recommended efficient "
        "offer”; else “Alternative package.” **Why:** tells which row is the official recommendation "
        "from the same search."
    ),
}


def _net_deal_scenarios_column_config() -> dict[str, Any]:
    """Column headers + ? help for the net-deal-outcome scenario table."""
    cc = st.column_config
    out: dict[str, Any] = {}
    for name, help_md in _NET_DEAL_SCENARIO_COLUMN_HELP.items():
        if name in ("Support Package", "Recommendation Status"):
            out[name] = cc.TextColumn(help=help_md)
        else:
            out[name] = cc.NumberColumn(help=help_md)
    return out


def format_multi_lever_display(
    df: pd.DataFrame,
    rec: pd.Series | None = None,
) -> pd.DataFrame:
    """Business-facing columns for executive scenario tables."""
    out = df.copy()
    out["Support Package"] = out.apply(support_package_label, axis=1)
    if rec is not None:
        m = scenario_rows_match(rec, out)
        out["Recommendation Status"] = np.where(
            m,
            "Recommended efficient offer",
            "Alternative package",
        )
    else:
        out["Recommendation Status"] = "—"

    rename_map: dict[str, str] = {
        "scenario_dealer_apr": "Dealer APR",
        "scenario_dealer_monthly_payment": "Monthly Payment",
        "loan_term": "Loan Term",
        "customer_cash": "OEM Cash",
        "dealer_cash": "Dealer Contribution",
        "loyalty_cash": "Loyalty Incentive",
        "conquest_cash": "Conquest Incentive",
        "estimated_support_cost": "Total Support Cost",
        "conversion_probability": "Predicted Conversion",
        "remaining_margin_estimate": "Remaining Margin",
        "expected_value": "Net Deal Outcome ($)",
        "efficiency_score": "Support Efficiency",
    }
    ordered_keys = [
        "Support Package",
        "scenario_dealer_apr",
        "scenario_dealer_monthly_payment",
        "loan_term",
        "customer_cash",
        "dealer_cash",
        "loyalty_cash",
        "conquest_cash",
        "estimated_support_cost",
        "conversion_probability",
        "remaining_margin_estimate",
        "expected_value",
        "efficiency_score",
        "Recommendation Status",
    ]
    present = [k for k in ordered_keys if k in out.columns]
    chunk = out[present].rename(columns={k: rename_map[k] for k in present if k in rename_map})
    return chunk


def build_executive_summary_html(
    prob_current: float,
    recommended: pd.Series,
    enriched_multi: pd.DataFrame,
) -> str:
    p0 = prob_current
    p1 = float(recommended["conversion_probability"])
    lift_pp = (p1 - p0) * 100.0
    sup = float(recommended["estimated_support_cost"])
    hint = overspend_support_hint_cost(enriched_multi, sup)
    extra = ""
    if hint is not None and hint > sup + 50:
        extra = (
            f" Additional modeled spend beyond approximately <b>${hint:,.0f}</b> shows "
            "materially lower incremental conversion gains along the searched ladder."
        )
    return (
        f'<div class="exec-summary-callout"><p>'
        f"The <b>recommended efficient offer</b> moves predicted conversion from "
        f"<b>{p0:.0%}</b> to <b>{p1:.0%}</b> "
        f"(<b>{lift_pp:+.1f}</b> percentage points vs your submitted desk quote) "
        f"with approximately <b>${sup:,.0f}</b> in total modeled support.{extra}"
        f"</p></div>"
    )


def render_three_scenario_comparison_html(
    *,
    label_current: str,
    prob_c: float,
    sup_c: float,
    pay_c: float,
    apr_c: float,
    rem_c: float,
    label_rec: str,
    prob_r: float,
    sup_r: float,
    pay_r: float,
    apr_r: float,
    rem_r: float,
    label_agg: str,
    prob_a: float,
    sup_a: float,
    pay_a: float,
    apr_a: float,
    rem_a: float,
) -> str:
    _h_prob = (
        "**How:** Classifier `predict_proba` on features built for each scenario row. "
        "**Why:** Comparable close odds across Current / Recommended / Aggressive."
    )
    _h_sup = (
        "**How:** `loan_amount × (support_level ÷ 10,000) × multiplier +` stacked cash components "
        "(`estimate_support_cost` path for desk inputs; optimizer row uses scenario loan/cash). "
        "**Why:** One incentive-dollar figure for comparing packages."
    )
    _h_pay = (
        "**How:** Amortization from scenario **loan amount**, **Dealer APR**, and **term**. "
        "**Why:** Desk-visible monthly payment for that structure."
    )
    _h_apr = (
        "**How:** `max(0.5%, standard_apr − support_level/100)` after applying scenario levers. "
        "**Why:** Customer-facing annual rate driving payment and model inputs."
    )
    _h_rem = (
        "**How:** Your **expected unit margin** input minus **total support cost** for that column’s "
        "scenario. **Why:** Directional gross after incentives—not GAAP."
    )

    def card(
        title: str,
        title_help: str,
        highlight: bool,
        prob: float,
        sup: float,
        pay: float,
        apr: float,
        rem: float,
    ) -> str:
        cls = "exec-scenario-compare-card exec-scen-rec" if highlight else "exec-scenario-compare-card"
        title_row = (
            f'<div class="esc-title" style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">'
            f"{html.escape(title)}{_hint(title_help)}</div>"
        )
        return (
            f'<div class="{cls}">'
            f"{title_row}"
            + _comparison_metric_row("Predicted conversion", f"{prob:.1%}", _h_prob)
            + _comparison_metric_row("Total support cost", f"${sup:,.0f}", _h_sup)
            + _comparison_metric_row("Monthly payment", f"${pay:,.0f}", _h_pay)
            + _comparison_metric_row("Dealer APR", f"{apr:.3f}%", _h_apr)
            + _comparison_metric_row("Remaining margin", f"${rem:,.0f}", _h_rem)
            + "</div>"
        )

    return (
        '<div class="exec-scenario-compare-grid">'
        + card(
            label_current,
            "Your **submitted desk quote** before optimizer changes — baseline for lift and comparison.",
            False,
            prob_c,
            sup_c,
            pay_c,
            apr_c,
            rem_c,
        )
        + card(
            label_rec,
            "**Recommended efficient offer** — best feasible package from the optimizer search under "
            "your constraints and ranking rule (default: net deal outcome).",
            True,
            prob_r,
            sup_r,
            pay_r,
            apr_r,
            rem_r,
        )
        + card(
            label_agg,
            "**Aggressive** scenario — highest modeled conversion among searched packages; often "
            "more support than the efficient recommendation.",
            False,
            prob_a,
            sup_a,
            pay_a,
            apr_a,
            rem_a,
        )
        + "</div>"
    )


def collect_inputs_from_session_state() -> dict[str, Any]:
    """Business dict from current widget session keys."""
    return build_business_inputs()


def render_full_page_wizard() -> None:
    now = datetime.now()
    _sidebar_migrate_phase2_ui()
    _sidebar_init_defaults(now)

    order = SIDEBAR_SECTION_ORDER
    step = int(st.session_state.current_step)
    step = max(0, min(step, len(order) - 1))
    st.session_state.current_step = step
    sec = order[step]

    render_hero()
    render_step_card_header(step, sec)
    _wizard_flush_scroll_top()
    render_quote_section_fields(sec, wizard=True)
    render_navigation(step)
    _wizard_flush_scroll_top()


def render_left_edit_panel() -> None:
    now = datetime.now()
    _sidebar_migrate_phase2_ui()
    _sidebar_init_defaults(now)

    order = SIDEBAR_SECTION_ORDER
    opts = [WIZARD_STEP_TITLE[s] for s in order]
    st.sidebar.markdown("### Scenario inputs")
    choice = st.sidebar.radio(
        "Section",
        options=opts,
        horizontal=True,
        key="edit_panel_section_radio",
        label_visibility="collapsed",
        help=(
            "Pick which inputs to edit (customer through macro). Changes apply when you click "
            "**Re-run analysis** — switching sections alone does not refresh the model."
        ),
    )
    sec = order[opts.index(choice)]
    st.session_state.edit_panel_section = sec

    render_quote_section_fields(sec, wizard=False)

    st.sidebar.divider()
    if st.sidebar.button(
        "Re-run analysis",
        type="primary",
        use_container_width=True,
        key="sidebar_rerun_analysis",
    ):
        st.session_state.analysis_submitted = True
        st.session_state.quote_submitted = True
        st.session_state.analysis_compute_requested = True
        _wizard_request_scroll_top()
        st.rerun()

    if st.sidebar.button(
        "Clear results",
        use_container_width=True,
        key="sidebar_clear_analysis",
    ):
        st.session_state.analysis_submitted = False
        st.session_state.quote_submitted = False
        st.session_state.analysis_compute_requested = False
        st.session_state.pop("analysis_run_cache", None)
        st.session_state.current_step = 0
        _wizard_request_scroll_top()
        st.rerun()


def main():
    st.set_page_config(
        page_title="Auto Finance Subvention Optimization Simulator",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()
    # Wizard-only paths call this inside render_full_page_wizard; analysis runs skip the wizard,
    # so we must seed missing sb_* keys every run (Streamlit may drop keys for unmounted widgets).
    _sidebar_init_defaults(datetime.now())

    st.markdown(EXEC_FONT_LINKS(), unsafe_allow_html=True)
    st.markdown(EXEC_THEME_CSS(), unsafe_allow_html=True)

    _deployment_startup_gate()

    if not st.session_state.analysis_submitted:
        st.markdown(EXEC_WIZARD_DEMO_UI_CSS(), unsafe_allow_html=True)
        render_full_page_wizard()
        st.stop()

    try:
        schema = get_feature_schema()
    except ValueError as e:
        st.error(str(e))
        st.stop()

    sample_defaults = get_sample_defaults()

    business = collect_inputs_from_session_state()

    submitted = bool(st.session_state.analysis_submitted)
    st.session_state.quote_submitted = submitted

    errs, warns = validate_business_inputs(business)

    blocking_overlay = st.empty()
    blocking_overlay.markdown(
        MODEL_LOADING_PANEL_HTML(
            title="Loading analytical model",
            subtitle="Restoring the finance conversion pipeline from disk — please wait.",
            fullscreen=True,
        ),
        unsafe_allow_html=True,
    )

    pipeline = None
    try:
        pipeline = load_model()
    except FileNotFoundError as e:
        blocking_overlay.empty()
        st.error(
            f"**Model not found.** Place `model_pipeline.pkl` in the app directory.\n\n{e}"
        )
        st.stop()
    except Exception as e:
        blocking_overlay.empty()
        st.error(f"Failed to load model: {e}")
        with st.expander("Model load traceback"):
            st.code(traceback.format_exc())
        st.stop()

    cm = float(st.session_state.sb_cost_multiplier)
    prob_current: float | None = None
    current_support_cost = estimate_support_cost(business, 0.0, cm)
    desk_support_cost = estimate_support_cost(
        business,
        float(business.get("dealer_rate_support_level") or 0),
        cm,
    )
    optimization_constraints = build_optimization_constraints_from_session()

    sim_err: str | None = None
    sim_err_single: str | None = None
    optimization_meta: dict[str, Any] | None = None
    enriched_multi: pd.DataFrame | None = None
    enriched_single: pd.DataFrame | None = None

    row_model: dict[str, Any] | None = None
    model_df: pd.DataFrame | None = None
    align_err: str | None = None
    align_missing: list[str] = []
    align_extra: list[str] = []

    if errs:
        blocking_overlay.empty()
    elif submitted:
        cache = st.session_state.get("analysis_run_cache")
        need_compute = bool(st.session_state.analysis_compute_requested) or cache is None

        def _cache_df(d: pd.DataFrame | None) -> pd.DataFrame | None:
            return None if d is None else d.copy()

        if need_compute:
            blocking_overlay.markdown(
                MODEL_LOADING_PANEL_HTML(
                    title="Running analysis",
                    subtitle=(
                        "Searching incentive packages inside your feasibility bounds "
                        "and valuation filters."
                    ),
                    fullscreen=True,
                ),
                unsafe_allow_html=True,
            )
            row_model = build_model_features(business)
            model_df, align_err, align_missing, align_extra = align_to_schema(
                row_model, schema, sample_defaults
            )
            try:
                if align_err is None and model_df is not None:
                    try:
                        prob_current = predict_conversion(pipeline, model_df)
                    except Exception:
                        prob_current = None
                    em, sim_err, opt_meta = run_constraint_based_offer_scenarios(
                        business,
                        optimization_constraints,
                        pipeline,
                        schema,
                        sample_defaults,
                        cm,
                    )
                    if sim_err is None and em is not None and not em.empty:
                        enriched_multi = em
                        optimization_meta = opt_meta

                    sim_single_df, sim_err_single = run_support_scenarios(
                        business,
                        pipeline,
                        schema,
                        sample_defaults,
                        SCENARIO_SUBVENTION_BPS,
                    )
                    if sim_err_single is None and sim_single_df is not None and not sim_single_df.empty:
                        enriched_single = enrich_offer_simulator_metrics(
                            sim_single_df, business, cm
                        )
            finally:
                blocking_overlay.empty()

            st.session_state.analysis_run_cache = {
                "prob_current": prob_current,
                "enriched_multi": _cache_df(enriched_multi),
                "enriched_single": _cache_df(enriched_single),
                "sim_err": sim_err,
                "sim_err_single": sim_err_single,
                "optimization_meta": optimization_meta,
                "row_model": copy.deepcopy(row_model) if row_model else None,
                "model_df": _cache_df(model_df),
                "align_err": align_err,
                "align_missing": list(align_missing),
                "align_extra": list(align_extra),
            }
            st.session_state.analysis_compute_requested = False
        else:
            blocking_overlay.empty()
            c = cache or {}
            prob_current = c.get("prob_current")
            enriched_multi = c.get("enriched_multi")
            enriched_single = c.get("enriched_single")
            sim_err = c.get("sim_err")
            sim_err_single = c.get("sim_err_single")
            optimization_meta = c.get("optimization_meta")
            row_model = c.get("row_model")
            model_df = c.get("model_df")
            align_err = c.get("align_err")
            align_missing = list(c.get("align_missing") or [])
            align_extra = list(c.get("align_extra") or [])

    st.markdown(
        '<div id="results-scroll-anchor" class="results-view-scroll-target" '
        'aria-hidden="true" style="height:0;margin:0;padding:0;"></div>',
        unsafe_allow_html=True,
    )
    _wizard_flush_scroll_top()
    st.title("Auto Finance Subvention Optimization Simulator")
    st.markdown(
        '<p class="exec-muted" style="margin-top:-0.5rem;margin-bottom:1.25rem;">'
        "Identify the lowest-cost dealer support strategy that improves customer conversion "
        "under current market conditions.</p>",
        unsafe_allow_html=True,
    )

    render_left_edit_panel()

    for w in warns:
        st.warning(w)

    if submitted and errs:
        for emsg in errs:
            st.error(emsg)

    recommended_pkg: pd.Series | None = None
    recommendation_relaxed_flag = False
    feasible_df_result: pd.DataFrame | None = None
    feasible_scenario_count = 0
    recommended_rank: int | None = None
    if (
        enriched_multi is not None
        and not enriched_multi.empty
        and submitted
        and not errs
        and align_err is None
    ):
        recommended_pkg, feasible_df_result, recommendation_relaxed_flag = (
            select_recommended_constrained(
                enriched_multi,
                float(business["expected_unit_margin"]),
                optimization_constraints,
            )
        )
        if recommended_pkg is not None:
            if (
                not recommendation_relaxed_flag
                and feasible_df_result is not None
                and not feasible_df_result.empty
            ):
                feasible_scenario_count = len(feasible_df_result)
                fsort = feasible_df_result.sort_values(
                    "expected_value", ascending=False
                ).reset_index(drop=True)
                mk = scenario_rows_match(recommended_pkg, fsort)
                if mk.any():
                    recommended_rank = int(fsort.index[mk][0]) + 1
            else:
                fsort = enriched_multi.sort_values(
                    "expected_value", ascending=False
                ).reset_index(drop=True)
                mk = scenario_rows_match(recommended_pkg, fsort)
                if mk.any():
                    recommended_rank = int(fsort.index[mk][0]) + 1

    tab_rec, tab_cmp, tab_md = st.tabs(
        [
            "Offer recommendation",
            "Offer analytics",
            "Model Details",
        ]
    )

    with tab_rec:
        st.markdown(
            '<p class="exec-muted">Define <b>market context</b> and <b>optimization constraints</b>. '
            "The engine searches APR buy-down plus OEM/customer, dealer, loyalty, and conquest cash "
            "across allowed loan terms. The <b>recommended efficient offer</b> maximizes "
            "<b>net deal outcome</b> (predicted conversion × expected unit margin − modeled support) "
            "within your feasibility filters; ties within <b>5%</b> of the best score defer to "
            "lower support spend.</p>",
            unsafe_allow_html=True,
        )
        if not submitted:
            st.info("Run **Run analysis** from the guided setup to see recommendations.")
        elif errs:
            st.warning("Fix the validation issues above, then click **Re-run analysis**.")
        elif align_err or model_df is None:
            st.error(align_err or "Could not build model input.")
            if align_missing:
                st.write("**Missing columns:**", align_missing)
            if align_extra:
                st.write("**Unused computed keys:**", align_extra)
        elif prob_current is None:
            st.error("Prediction failed for the current inputs.")
        elif enriched_multi is None:
            st.warning(sim_err or "Could not complete incentive search.")
        elif recommended_pkg is None:
            st.error("Could not derive a recommended package.")
        else:
            if optimization_meta is not None:
                om = optimization_meta
                sm = str(om.get("search_mode", "—"))
                total_g = int(om.get("total_grid_scenarios", 0))
                ev_n = int(om.get("scenarios_evaluated", 0))
                rt = float(om.get("runtime_seconds", 0.0))
                rnk = recommended_rank
                rnk_s = "—" if rnk is None else str(int(rnk))
                feas_n = int(feasible_scenario_count)
                if sm == "Full grid search":
                    cred = (
                        "Because the scenario count is within the configured threshold, the optimizer "
                        "evaluated <b>every</b> offer package in the configured grid. The recommendation "
                        "is the best package found across that full grid — <b>not</b> a random sample."
                    )
                else:
                    cred = (
                        "<b>Large scenario space detected.</b> Coarse-to-fine optimization was used: "
                        "a deterministic coarse grid (50 bps rate steps, $1,000 cash steps) was fully "
                        "scored, then the top packages were refined with local neighbors "
                        "(±25 bps, ±$500 cash, adjacent loan terms)."
                    )
                    if om.get("coarse_grid_truncated"):
                        cred += (
                            " The coarse grid was <b>deterministically thinned</b> so evaluation stays "
                            f"within {MAX_FULL_ENUMERATION:,} coarse scenarios."
                        )
                cref = ""
                if sm == "Coarse-to-fine search":
                    cref = (
                        f"<p class=\"exec-muted-small\" style=\"margin:0.35rem 0 0 0;\">"
                        f"Coarse phase scored <b>{int(om.get('coarse_evaluated', 0)):,}</b> scenarios; "
                        f"refinement scored <b>{int(om.get('refined_evaluated', 0)):,}</b> additional "
                        f"neighbor packages.</p>"
                    )
                _hint_opt_title = (
                    "Counts and mode for how offer packages were searched and scored. "
                    "**Full grid** enumerates (within limits); **coarse-to-fine** scores a deterministic coarse pass "
                    "then refines neighbors when the grid is too large."
                )
                _hint_search_method = (
                    "**Full grid search** evaluates every combination in the configured grid (when within limits). "
                    "**Coarse-to-fine** uses a deterministic coarse grid plus local refinement when enumeration "
                    "would be too large."
                )
                _hint_total_gen = (
                    "Unique APR buy-down × cash × term combinations implied by your supported grids **before** "
                    "feasibility filters."
                )
                _hint_evaluated = (
                    "Packages actually scored with the conversion model (may be fewer than generated when "
                    "coarse-to-fine skips exhaustive enumeration)."
                )
                _hint_feasible = (
                    "Packages passing your configured rules (budget, margin floor, lift vs baseline, etc.)."
                )
                _hint_rank = (
                    "Where the **recommended efficient** package lands when feasible scenarios are sorted by "
                    "the default **net deal outcome** ranking (rank **1** = best under that rule)."
                )
                _hint_runtime = (
                    "Wall-clock seconds for searching and scoring scenarios on this run (model calls plus "
                    "bookkeeping)."
                )
                st.markdown(
                    f'<div class="exec-subcard" style="margin-bottom:1rem;">'
                    f'<div class="esl" style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">'
                    f"Optimization Search Summary{_hint(_hint_opt_title)}"
                    f"</div>"
                    f'<p class="exec-muted-small" style="margin:0 0 0.5rem 0;display:flex;align-items:flex-start;'
                    f'gap:0.35rem;flex-wrap:wrap;"><span style="display:inline-flex;align-items:center;'
                    f'gap:0.28rem;flex-wrap:wrap;">{_labeled_hint("Search method", _hint_search_method)}</span>'
                    f"<span>{html.escape(sm)}</span></p>"
                    f'<p class="exec-muted-small" style="margin:0 0 0.35rem 0;"><span style="display:inline-flex;'
                    f'align-items:center;gap:0.28rem;flex-wrap:wrap;">'
                    f'{_labeled_hint("Total generated scenarios (configured grid)", _hint_total_gen)}</span> '
                    f"<span>{total_g:,}</span></p>"
                    f'<p class="exec-muted-small" style="margin:0 0 0.35rem 0;"><span style="display:inline-flex;'
                    f'align-items:center;gap:0.28rem;flex-wrap:wrap;">'
                    f'{_labeled_hint("Scenarios evaluated", _hint_evaluated)}</span> '
                    f"<span>{ev_n:,} of {total_g:,}</span></p>"
                    f'<p class="exec-muted-small" style="margin:0 0 0.35rem 0;"><span style="display:inline-flex;'
                    f'align-items:center;gap:0.28rem;flex-wrap:wrap;">'
                    f'{_labeled_hint("Feasible scenarios (after constraints)", _hint_feasible)}</span> '
                    f"<span>{feas_n:,}</span></p>"
                    f'<p class="exec-muted-small" style="margin:0 0 0.35rem 0;"><span style="display:inline-flex;'
                    f'align-items:center;gap:0.28rem;flex-wrap:wrap;">'
                    f'{_labeled_hint("Recommended scenario rank (among feasible by net deal outcome)", _hint_rank)}</span> '
                    f"<span>{rnk_s}</span></p>"
                    f'<p class="exec-muted-small" style="margin:0 0 0.35rem 0;"><span style="display:inline-flex;'
                    f'align-items:center;gap:0.28rem;flex-wrap:wrap;">'
                    f'{_labeled_hint("Optimizer runtime", _hint_runtime)}</span> <span>{rt:.2f}s</span></p>'
                    f"{cref}"
                    f"<p class=\"exec-muted-small\" style=\"margin:0.65rem 0 0 0;line-height:1.45;\">{cred}</p>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            recommended = recommended_pkg
            highest = select_highest_conversion_scenario(enriched_multi)
            sup_lbl = rate_support_tier_label(int(recommended["dealer_rate_support_level"]))
            rem_m = float(recommended.get("remaining_margin_estimate", 0))
            lift_vs_desk_pp = (
                float(recommended["conversion_probability"]) - float(prob_current)
            ) * 100.0
            eu_margin = float(business["expected_unit_margin"])
            cur_apr = (
                float(row_model["dealer_apr"])
                if row_model is not None
                else float(business["baseline_dealer_apr"])
            )
            cur_pay = (
                float(row_model["dealer_monthly_payment"])
                if row_model is not None
                else float(business["baseline_dealer_monthly_payment"])
            )
            rem_cur = eu_margin - desk_support_cost

            if recommendation_relaxed_flag:
                st.warning(
                    "No scenarios satisfied **all** feasibility filters simultaneously "
                    "(budget, residual margin floor, lift vs **no-incentive baseline** at the "
                    "scenario term). Showing the best **net deal outcome** unconstrained fallback — "
                    "relax constraints or raise budget caps to surface compliant packages."
                )

            if row_model is not None:
                apr_gap = float(row_model["apr_gap_bps"])
                apr_pts = apr_gap / 100.0
                payment_adv = float(row_model["payment_gap"])
                rebate_adv = float(row_model["cashback_gap"])
                headline, plain = competitive_position_detail(apr_gap)
                st.markdown(
                    '<p class="exec-section-title" style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">'
                    "Your submitted quote vs. competitor"
                    f"{_hint('Uses your current desk inputs (APR, payment, stacked rebates) vs the modeled competitor.')}"
                    "</p>",
                    unsafe_allow_html=True,
                )
                snap_a, snap_b, snap_c = st.columns(3)
                with snap_a:
                    st.metric(
                        "Predicted conversion (current offer)",
                        f"{prob_current:.1%}",
                        help=(
                            "**How:** Classifier `predict_proba` after aligning **your current desk** inputs. "
                            "**Why:** Baseline close probability before comparing optimizer packages."
                        ),
                    )
                with snap_b:
                    st.metric(
                        "Likelihood band",
                        likelihood_band(prob_current),
                        help=(
                            "**How:** Maps modeled probability to **Low / Moderate / High** using fixed "
                            "cutoffs (`likelihood_band`: below 35%, 35–65%, above 65%). **Why:** Fast read "
                            "without interpreting decimals."
                        ),
                    )
                with snap_c:
                    st.metric(
                        "Competitive position",
                        headline,
                        help=(
                            "**How:** Buckets modeled **APR gap vs competitor** (`apr_gap_bps`) into Dealer "
                            "Advantage / Neutral / Competitor Advantage. **Why:** One-line headline before "
                            "you inspect payment and cash deltas."
                        ),
                    )
                st.markdown(
                    f'<p class="exec-muted-small">{html.escape(plain)}</p>',
                    unsafe_allow_html=True,
                )
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric(
                        "Rate position vs. competitor",
                        f"{apr_pts:+.2f} pts",
                        help=(
                            "**How:** `(your dealer APR − competitor APR)` expressed as **percentage points** "
                            "(implementation: `apr_gap_bps / 100`). **Why:** Same APR units as the desk; "
                            "**negative** usually means your rate is lower."
                        ),
                    )
                with m2:
                    st.metric(
                        "Monthly payment difference",
                        f"${payment_adv:+,.0f}",
                        help=(
                            "**How:** Your modeled payment minus competitor payment (`payment_gap`). "
                            "**Why:** Shows monthly cash-flow delta on the comparable structure."
                        ),
                    )
                with m3:
                    st.metric(
                        "Cash incentive difference",
                        f"${rebate_adv:+,.0f}",
                        help=(
                            "**How:** Your total modeled visible cash stack minus competitor cashback "
                            "(`cashback_gap`). **Why:** Captures rebate competitiveness alongside rate/payment."
                        ),
                    )
                st.metric(
                    "Estimated total support (current desk inputs)",
                    f"${desk_support_cost:,.0f}",
                    help=(
                        "**How:** `loan_amount × (your support_level ÷ 10,000) × support_cost_multiplier` "
                        "**+** OEM + dealer + loyalty + conquest cash from **submitted** desk inputs "
                        "(`estimate_support_cost`). **Why:** Dollar load of incentives before optimization."
                    ),
                )
                st.metric(
                    "Zero‑incentive reference (model anchor)",
                    f"${current_support_cost:,.0f}",
                    help=(
                        "**How:** Same support-cost formula with **rate support level forced to 0** "
                        "(cash unchanged). **Why:** Anchor for how much spend sits in APR buy-down vs a "
                        "no-buy-down baseline."
                    ),
                )
                st.divider()

            st.markdown(
                build_executive_summary_html(
                    float(prob_current), recommended, enriched_multi
                ),
                unsafe_allow_html=True,
            )

            hero_html = (
                '<div class="exec-hero-metrics-grid">'
                '<div class="exec-hero-metric-tile exec-hero-metric-rec">'
                + _hero_metric_label(
                    "Recommended conversion",
                    "**How:** `predict_proba` on aligned features for the **recommended efficient** package. "
                    "**Why:** Primary success metric for that structure vs your baseline.",
                )
                + f'<p class="ehm-value">{recommended["conversion_probability"]:.1%}</p>'
                + '<p class="ehm-sub">Share of deals modeled to close at this offer.</p></div>'
                '<div class="exec-hero-metric-tile exec-hero-metric-rec">'
                + _hero_metric_label(
                    "Lift vs current offer",
                    "**How:** Recommended conversion probability **minus** probability on **submitted** desk "
                    "inputs, ×100 → **percentage points** (subtract probabilities as numbers, not percent "
                    "change). **Why:** Shows incremental close odds from moving to the recommended package.",
                )
                + f'<p class="ehm-value">{lift_vs_desk_pp:+.1f} pp</p>'
                + "<p class=\"ehm-sub\">Points added to close rate vs current-offer estimate.</p></div>"
                '<div class="exec-hero-metric-tile exec-hero-metric-rec">'
                + _hero_metric_label(
                    "Estimated support cost",
                    "**How:** `scenario loan × (support_level ÷ 10,000) × calibration multiplier +` all "
                    "stacked cash on the recommended row. **Why:** Full-dollar incentive load used in budget "
                    "and net-deal math—not monthly payment.",
                )
                + f'<p class="ehm-value">${recommended["estimated_support_cost"]:,.0f}</p>'
                + '<p class="ehm-sub">Full-package incentive economics.</p></div>'
                '<div class="exec-hero-metric-tile exec-hero-metric-rec">'
                + _hero_metric_label(
                    "Estimated remaining margin",
                    "**How:** **Expected unit margin** (your input) **−** **estimated support cost** for the "
                    "recommended scenario. **Why:** Quick gross-after-incentive sanity check on the desk.",
                )
                + f'<p class="ehm-value">${rem_m:,.0f}</p>'
                + '<p class="ehm-sub">Rough gross after incentives.</p></div>'
                '<div class="exec-hero-metric-tile exec-hero-metric-rec">'
                + _hero_metric_label(
                    "Recommended dealer APR",
                    "**How:** Standard APR minus buy-down (`support_level / 100` percentage points), "
                    "floored at **0.5%**. **Why:** Rate shown to the customer for the recommended structure.",
                )
                + f'<p class="ehm-value">{recommended["scenario_dealer_apr"]:.3f}%</p>'
                + '<p class="ehm-sub">Subvented APR on the quote.</p></div>'
                '<div class="exec-hero-metric-tile exec-hero-metric-rec">'
                + _hero_metric_label(
                    "Estimated monthly payment",
                    "**How:** Payment from amortizing **scenario loan amount** at **recommended APR** over "
                    "**loan term**. **Why:** Desk payment for that quote.",
                )
                + f'<p class="ehm-value">${recommended["scenario_dealer_monthly_payment"]:,.0f}</p>'
                + '<p class="ehm-sub">Desk payment for this structure.</p></div>'
                '<div class="exec-hero-metric-tile exec-hero-metric-rec">'
                + _hero_metric_label(
                    "Recommended loan term",
                    "**How:** Term from the optimizer’s chosen package within your allowed term grid. "
                    "**Why:** Drives payment, baseline conversion at zero incentive, and feasibility.",
                )
                + f'<p class="ehm-value">{int(recommended["loan_term"])} mo</p>'
                + '<p class="ehm-sub">Contract length.</p></div>'
                "</div>"
            )
            st.markdown(hero_html, unsafe_allow_html=True)

            rec_cash_total = (
                float(recommended.get("customer_cash", 0))
                + float(recommended.get("dealer_cash", 0))
                + float(recommended.get("loyalty_cash", 0))
                + float(recommended.get("conquest_cash", 0))
            )
            rate_only_callout = ""
            if rec_cash_total < 0.5:
                rate_only_callout = (
                    '<p class="exec-muted-small" style="margin:0.45rem 0 0.65rem 0;padding:0.55rem 0.85rem;'
                    'background:#f8fafc;border-radius:10px;border-left:4px solid #64748b;line-height:1.5;">'
                    "<b>APR-led package:</b> Within your caps, OEM/customer, dealer, loyalty, and conquest "
                    "cash are <b>$0</b> on this row — the optimizer favored "
                    f"<b>{int(recommended['dealer_rate_support_level'])}</b> bps buy-down "
                    f'({html.escape(sup_lbl)}). See <b>Offer analytics</b> for other mixes.</p>'
                )

            st.markdown(
                '<p class="exec-section-title" style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">'
                "Compare scenarios"
                f"{_hint('Current desk inputs vs the recommended efficient offer vs maximum modeled conversion.')}"
                "</p>",
                unsafe_allow_html=True,
            )
            st.markdown(
                render_three_scenario_comparison_html(
                    label_current="Current offer",
                    prob_c=float(prob_current),
                    sup_c=float(desk_support_cost),
                    pay_c=cur_pay,
                    apr_c=cur_apr,
                    rem_c=float(rem_cur),
                    label_rec="Recommended efficient offer",
                    prob_r=float(recommended["conversion_probability"]),
                    sup_r=float(recommended["estimated_support_cost"]),
                    pay_r=float(recommended["scenario_dealer_monthly_payment"]),
                    apr_r=float(recommended["scenario_dealer_apr"]),
                    rem_r=float(rem_m),
                    label_agg="Aggressive offer",
                    prob_a=float(highest["conversion_probability"]),
                    sup_a=float(highest["estimated_support_cost"]),
                    pay_a=float(highest["scenario_dealer_monthly_payment"]),
                    apr_a=float(highest["scenario_dealer_apr"]),
                    rem_a=float(highest.get("remaining_margin_estimate", 0)),
                ),
                unsafe_allow_html=True,
            )

            st.markdown(
                '<p class="exec-section-title" style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">'
                "Support allocation (recommended)"
                f"{_hint('Split of modeled dollars between APR subsidy and stacked cash for the recommended package.')}"
                "</p>",
                unsafe_allow_html=True,
            )
            st.markdown(rate_only_callout, unsafe_allow_html=True)
            st.altair_chart(
                chart_support_breakdown_recommended(recommended, cm),
                use_container_width=True,
            )

            with st.expander("Technical lift detail (optional)", expanded=False):
                st.markdown(_technical_lift_detail_html(recommended), unsafe_allow_html=True)

            st.caption(
                "Recommendation maximizes constrained **net deal outcome** — not raw conversion alone."
            )

    with tab_cmp:
        st.markdown(
            '<p class="exec-muted"><b>Offer analytics</b> — decision-support views over every incentive '
            "package the engine evaluated. **Green** highlights the feasibility-aware **recommended** "
            "scenario. Dollar figures are **total modeled support per scenario**, not monthly payment.</p>",
            unsafe_allow_html=True,
        )
        if (
            optimization_meta is not None
            and submitted
            and not errs
            and align_err is None
        ):
            om = optimization_meta
            st.caption(
                f"**Optimizer:** {om.get('search_mode', '—')} · "
                f"**Scenarios evaluated:** {int(om.get('scenarios_evaluated', 0)):,} "
                f"of {int(om.get('total_grid_scenarios', 0)):,} possible in the configured grid."
            )
        if not submitted:
            st.info("Run analysis from the guided setup to load charts and tables.")
        elif errs or align_err or enriched_multi is None:
            st.warning(sim_err or "Complete inputs to view offer analytics.")
        else:
            recommended_cmp = (
                recommended_pkg
                if recommended_pkg is not None
                else select_recommended_expected_value(enriched_multi)
            )

            render_exploration_chart_card(
                "Incentive ladder (primary)",
                "Conversion (vertical) rises as total modeled support (horizontal) increases — "
                "green marks the recommended efficient offer.",
                OFFER_ANALYTICS_CHART_HELP["incentive_ladder"],
                chart_incentive_ladder(enriched_multi, recommended_cmp, cm),
                analytics_key="incentive_ladder",
            )

            dc1, dc2 = st.columns(2)
            with dc1:
                st.markdown(
                    '<span class="exec-chart-pair-anchor" aria-hidden="true"></span>',
                    unsafe_allow_html=True,
                )
                render_exploration_chart_card(
                    "Diminishing returns",
                    "Incremental conversion vs prior step — steep early gains; shaded zones flag overspending.",
                    OFFER_ANALYTICS_CHART_HELP["diminishing_returns"],
                    chart_diminishing_returns(enriched_multi, recommended_cmp),
                    analytics_key="diminishing_returns",
                )
            with dc2:
                render_exploration_chart_card(
                    "Support allocation (recommended)",
                    "Where incentive dollars go for the recommended package — APR vs stacked cash.",
                    OFFER_ANALYTICS_CHART_HELP["support_breakdown"],
                    chart_support_breakdown_recommended(recommended_cmp, cm),
                    analytics_key="support_breakdown",
                )

            st.markdown(
                '<p class="exec-section-title" style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;">'
                "Top scenarios by net deal outcome"
                f"{_hint('Ranked by net deal outcome ($) within your search; muted green row = recommended package.')}"
                "</p>",
                unsafe_allow_html=True,
            )
            top25 = enriched_multi.nlargest(25, "expected_value").copy()
            disp25 = format_multi_lever_display(top25, recommended_cmp)

            def _highlight_exec_table(row: pd.Series) -> list[str]:
                if row.get("Recommendation Status") == "Recommended efficient offer":
                    return ["background-color: #ecfdf5; font-weight: 600"] * len(row)
                return [""] * len(row)

            fmt_ml: dict[str, str] = {
                "Dealer APR": "{:.3f}",
                "Monthly Payment": "{:.0f}",
                "Loan Term": "{:.0f}",
                "OEM Cash": "${:,.0f}",
                "Dealer Contribution": "${:,.0f}",
                "Loyalty Incentive": "${:,.0f}",
                "Conquest Incentive": "${:,.0f}",
                "Total Support Cost": "${:,.0f}",
                "Predicted Conversion": "{:.1%}",
                "Remaining Margin": "${:,.0f}",
                "Net Deal Outcome ($)": "${:,.0f}",
                "Support Efficiency": "{:.4f}",
            }

            _nd_cfg = {
                k: v
                for k, v in _net_deal_scenarios_column_config().items()
                if k in disp25.columns
            }
            st.dataframe(
                disp25.style.format(fmt_ml, na_rep="—").apply(_highlight_exec_table, axis=1),
                use_container_width=True,
                hide_index=True,
                column_config=_nd_cfg,
            )

            st.markdown(
                '<p class="exec-note"><i>Support cost uses loan × (support level ÷ 10,000) × '
                "calibration multiplier plus cash components. Tune multiplier under "
                "<b>Advanced calibration</b>.</i></p>",
                unsafe_allow_html=True,
            )

            with st.expander(
                "APR-only sensitivity (reference)",
                expanded=False,
            ):
                st.caption(
                    "Single-knob sweep on **dealer rate support** only — useful sanity check. "
                    "Primary recommendations use the **multi-lever** search above."
                )
                st.caption(
                    "**Dollar figures:** **Estimated support cost** is a **total modeled snapshot per scenario** "
                    "(rate-buy-down estimate + stacked cash rebates)—**not** the customer’s monthly payment, "
                    "**not** GAAP. Open **?** on each chart for full definitions."
                )
                if enriched_single is None:
                    st.info(sim_err_single or "Single-lever sensitivity sweep did not complete.")
                else:
                    rec_s = select_recommended_efficient_scenario(enriched_single)
                    hl = int(rec_s["dealer_rate_support_level"])
                    st.markdown(
                        """
<style>
section.main div[data-testid="stHorizontalBlock"]:has(.exec-sim-anchor)
  > div[data-testid="column"] {
  flex: 1 1 0% !important;
  min-width: 0 !important;
}
</style>
""",
                        unsafe_allow_html=True,
                    )
                    try:
                        ex1, ex2, ex3 = st.columns([1, 1, 1], gap="medium")
                    except TypeError:
                        ex1, ex2, ex3 = st.columns(3)
                    with ex1:
                        st.markdown(
                            '<span class="exec-sim-anchor" aria-hidden="true"></span>',
                            unsafe_allow_html=True,
                        )
                        render_simulator_chart_with_axis_help(
                            "Conversion probability vs. support level",
                            "conversion",
                            chart_conversion_by_support(enriched_single, hl),
                        )
                    with ex2:
                        render_simulator_chart_with_axis_help(
                            "Estimated support cost vs. support level",
                            "support_cost",
                            chart_support_cost_by_support(enriched_single, hl),
                        )
                    with ex3:
                        render_simulator_chart_with_axis_help(
                            "Efficiency score vs. support level",
                            "efficiency",
                            chart_efficiency_by_support(enriched_single, hl),
                        )

    with tab_md:
        st.caption(
            "The input panels use business labels only. Encoded column names, bands, ratios, and "
            "interaction terms (for example credit tier, loan-to-value, rate comparisons) are "
            "computed internally and appear **only** under **Model-ready features** below."
        )

        with st.expander("Behavioral scale reference", expanded=False):
            render_behavioral_scoring_guide_main()

        with st.expander("Model metadata", expanded=False):
            meta = load_json("model_metadata.json")
            if meta is None:
                st.info("`model_metadata.json` not found beside `app.py`.")
            else:
                st.json(meta)

        with st.expander("Feature schema", expanded=False):
            st.json(schema)

        with st.expander("Model-ready features (debug)", expanded=False):
            st.markdown(
                "Single-row preview aligned to the trained pipeline. Includes derived fields "
                "such as income bands, payment burden, and competitive gaps — **not** shown on "
                "the primary input labels."
            )
            if not submitted:
                st.info("Run analysis from the guided setup to preview the aligned model row.")
            elif model_df is not None:
                st.dataframe(model_df, use_container_width=True)
            else:
                st.info("Resolve validation issues to preview the aligned row.")

        with st.expander("Scenario sweep — derived dealer APR & payment", expanded=False):
            if not submitted:
                st.info("Run analysis from the guided setup to export scenario sweep details.")
            elif enriched_multi is not None:
                prev = enriched_multi[
                    [
                        "dealer_rate_support_level",
                        "scenario_dealer_apr",
                        "scenario_dealer_monthly_payment",
                        "conversion_probability",
                    ]
                ].rename(
                    columns={
                        "dealer_rate_support_level": "Support level index",
                        "scenario_dealer_apr": "Modeled dealer APR",
                        "scenario_dealer_monthly_payment": "Modeled dealer payment",
                        "conversion_probability": "Predicted conversion",
                    }
                )
                st.dataframe(prev, use_container_width=True, hide_index=True)
            else:
                st.info("Run a valid scenario sweep to preview derived scenario rows.")

    st.divider()
    st.markdown(
        '<p class="exec-note">Figures are directional for executive discussion—not accounting '
        "statements. Tune calibration with your finance and OEM partners.</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
