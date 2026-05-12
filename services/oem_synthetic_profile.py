"""
OEM planning mode: map archetypes / mix to the same ``sb_*`` customer fields used in dealer mode.

The conversion model and ``build_business_inputs`` are unchanged; we only populate representative
values before business input assembly when ``optimization_mode == "oem"``.
"""

from __future__ import annotations

from typing import Any

from services.feature_engineering import yes_no_to_bool

# Keys written into ``state`` so ``build_business_inputs`` matches dealer path.
_CUSTOMER_STATE_KEYS: tuple[str, ...] = (
    "sb_fico_score",
    "sb_monthly_income",
    "sb_monthly_debt_payments",
    "sb_price_sensitivity_ui",
    "sb_purchase_urgency_ui",
    "sb_brand_preference_ui",
    "sb_purchase_intent_ui",
    "sb_sentiment_ui",
    "sb_customer_segment",
    "sb_ev_affinity_ui",
    "sb_family_utility_ui",
    "sb_truck_affinity_ui",
    "sb_conquest_likelihood_ui",
)

# Numeric archetype presets (sliders 1–10 unless noted).
_ARCH: dict[str, dict[str, Any]] = {
    "Prime Family Buyer": {
        "sb_fico_score": 740,
        "sb_monthly_income": 9500,
        "sb_monthly_debt_payments": 2200,
        "sb_price_sensitivity_ui": 5,
        "sb_purchase_urgency_ui": 6,
        "sb_brand_preference_ui": 7,
        "sb_purchase_intent_ui": 7,
        "sb_sentiment_ui": 6,
        "sb_customer_segment": "Utility Buyer",
        "sb_ev_affinity_ui": 4,
        "sb_family_utility_ui": 8,
        "sb_truck_affinity_ui": 5,
        "sb_conquest_likelihood_ui": 4,
    },
    "Payment Sensitive Buyer": {
        "sb_fico_score": 700,
        "sb_monthly_income": 6200,
        "sb_monthly_debt_payments": 2800,
        "sb_price_sensitivity_ui": 9,
        "sb_purchase_urgency_ui": 5,
        "sb_brand_preference_ui": 5,
        "sb_purchase_intent_ui": 6,
        "sb_sentiment_ui": 5,
        "sb_customer_segment": "Payment Sensitive",
        "sb_ev_affinity_ui": 3,
        "sb_family_utility_ui": 6,
        "sb_truck_affinity_ui": 4,
        "sb_conquest_likelihood_ui": 6,
    },
    "Near-Prime Buyer": {
        "sb_fico_score": 660,
        "sb_monthly_income": 5800,
        "sb_monthly_debt_payments": 3100,
        "sb_price_sensitivity_ui": 8,
        "sb_purchase_urgency_ui": 6,
        "sb_brand_preference_ui": 5,
        "sb_purchase_intent_ui": 6,
        "sb_sentiment_ui": 5,
        "sb_customer_segment": "Value Shopper",
        "sb_ev_affinity_ui": 3,
        "sb_family_utility_ui": 6,
        "sb_truck_affinity_ui": 5,
        "sb_conquest_likelihood_ui": 7,
    },
    "Truck Buyer": {
        "sb_fico_score": 720,
        "sb_monthly_income": 8800,
        "sb_monthly_debt_payments": 2600,
        "sb_price_sensitivity_ui": 5,
        "sb_purchase_urgency_ui": 7,
        "sb_brand_preference_ui": 7,
        "sb_purchase_intent_ui": 7,
        "sb_sentiment_ui": 6,
        "sb_customer_segment": "Utility Buyer",
        "sb_ev_affinity_ui": 3,
        "sb_family_utility_ui": 6,
        "sb_truck_affinity_ui": 9,
        "sb_conquest_likelihood_ui": 5,
    },
    "EV Early Adopter": {
        "sb_fico_score": 730,
        "sb_monthly_income": 9000,
        "sb_monthly_debt_payments": 2400,
        "sb_price_sensitivity_ui": 5,
        "sb_purchase_urgency_ui": 7,
        "sb_brand_preference_ui": 6,
        "sb_purchase_intent_ui": 8,
        "sb_sentiment_ui": 7,
        "sb_customer_segment": "EV Interested",
        "sb_ev_affinity_ui": 9,
        "sb_family_utility_ui": 5,
        "sb_truck_affinity_ui": 3,
        "sb_conquest_likelihood_ui": 6,
    },
    "Luxury Buyer": {
        "sb_fico_score": 760,
        "sb_monthly_income": 14000,
        "sb_monthly_debt_payments": 3500,
        "sb_price_sensitivity_ui": 3,
        "sb_purchase_urgency_ui": 6,
        "sb_brand_preference_ui": 8,
        "sb_purchase_intent_ui": 7,
        "sb_sentiment_ui": 7,
        "sb_customer_segment": "Premium Buyer",
        "sb_ev_affinity_ui": 5,
        "sb_family_utility_ui": 5,
        "sb_truck_affinity_ui": 4,
        "sb_conquest_likelihood_ui": 4,
    },
    "Value-Oriented Buyer": {
        "sb_fico_score": 690,
        "sb_monthly_income": 6000,
        "sb_monthly_debt_payments": 2600,
        "sb_price_sensitivity_ui": 9,
        "sb_purchase_urgency_ui": 5,
        "sb_brand_preference_ui": 4,
        "sb_purchase_intent_ui": 6,
        "sb_sentiment_ui": 5,
        "sb_customer_segment": "Value Shopper",
        "sb_ev_affinity_ui": 4,
        "sb_family_utility_ui": 6,
        "sb_truck_affinity_ui": 4,
        "sb_conquest_likelihood_ui": 7,
    },
}

_MIX_BASE = {
    "prime": "Prime Family Buyer",
    "near": "Near-Prime Buyer",
    "sub": "Payment Sensitive Buyer",
}


def _clamp_int(v: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, round(v))))


def compute_oem_customer_assumptions(state: dict[str, Any]) -> dict[str, Any]:
    """Return synthetic customer fields (does not mutate ``state``)."""
    use_mix = yes_no_to_bool(state.get("oem_use_mix"))
    if use_mix:
        p = float(state.get("oem_prime_pct") or 0)
        n = float(state.get("oem_near_prime_pct") or 0)
        s = float(state.get("oem_subprime_pct") or 0)
        tot = p + n + s
        if tot <= 0:
            arch = str(state.get("oem_archetype") or "Prime Family Buyer")
            base = dict(_ARCH.get(arch, _ARCH["Prime Family Buyer"]))
            return base
        wp, wn, ws = p / tot, n / tot, s / tot
        a_p = _ARCH[_MIX_BASE["prime"]]
        a_n = _ARCH[_MIX_BASE["near"]]
        a_s = _ARCH[_MIX_BASE["sub"]]
        out: dict[str, Any] = {}
        for k in _CUSTOMER_STATE_KEYS:
            if k == "sb_customer_segment":
                # Dominant tier wins segment label
                mx = max(wp, wn, ws)
                if mx == wp:
                    out[k] = a_p[k]
                elif mx == wn:
                    out[k] = a_n[k]
                else:
                    out[k] = a_s[k]
                continue
            if isinstance(a_p[k], (int, float)) and not isinstance(a_p[k], bool):
                out[k] = wp * float(a_p[k]) + wn * float(a_n[k]) + ws * float(a_s[k])
            else:
                out[k] = a_p[k]
        out["sb_fico_score"] = _clamp_int(float(out["sb_fico_score"]), 300, 850)
        out["sb_monthly_income"] = max(1000.0, float(out["sb_monthly_income"]))
        out["sb_monthly_debt_payments"] = max(0.0, float(out["sb_monthly_debt_payments"]))
        for sk in (
            "sb_price_sensitivity_ui",
            "sb_purchase_urgency_ui",
            "sb_brand_preference_ui",
            "sb_purchase_intent_ui",
            "sb_sentiment_ui",
            "sb_ev_affinity_ui",
            "sb_family_utility_ui",
            "sb_truck_affinity_ui",
            "sb_conquest_likelihood_ui",
        ):
            out[sk] = _clamp_int(float(out[sk]), 1, 10)
        return out

    arch = str(state.get("oem_archetype") or "Prime Family Buyer")
    return dict(_ARCH.get(arch, _ARCH["Prime Family Buyer"]))


def apply_oem_synthetic_profile(state: dict[str, Any]) -> None:
    """If OEM mode, merge synthetic customer assumptions into ``state`` for downstream pipeline."""
    if state.get("optimization_mode") != "oem":
        return
    merged = compute_oem_customer_assumptions(state)
    for k, v in merged.items():
        state[k] = v


def oem_archetype_labels() -> tuple[str, ...]:
    return tuple(_ARCH.keys())
