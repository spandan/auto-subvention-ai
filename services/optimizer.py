"""Scenario search, cost estimation, and recommendation selection."""

from __future__ import annotations

import copy
import itertools
import logging
import math
import time
from typing import Any, Callable

import numpy as np
import pandas as pd

from services.constants import MAX_FULL_ENUMERATION
from services.feature_engineering import (
    align_rows_for_batch_predict,
    align_to_schema,
    calculate_model_features,
    calculate_monthly_payment_if_needed,
    loan_terms_sorted,
    yes_no_to_bool,
)
from services.model_service import predict_conversion, predict_conversion_positive_column

_log = logging.getLogger(__name__)


def _emit_worker_progress(
    progress_sink: Callable[[float, str], None] | None,
    progress: float,
    message: str,
) -> None:
    if progress_sink is None:
        return
    try:
        progress_sink(float(progress), str(message))
    except Exception:
        pass


def rate_support_tier_label(level: int) -> str:
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


def estimate_support_cost(inputs_row: dict[str, Any], support_level: float, cm: float) -> float:
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


def build_optimization_constraints(state: dict[str, Any]) -> dict[str, Any]:
    """User-defined search bounds — not scenario values."""
    terms = loan_terms_sorted(state.get("sb_allowed_loan_terms"))
    return {
        "max_oem_customer_cash": float(state.get("sb_max_oem_customer_cash") or 0),
        "max_dealer_cash": float(state.get("sb_max_dealer_cash_support") or 0),
        "max_rate_support": max(0, int(state.get("sb_max_apr_rate_support") or 0)),
        "allow_loyalty": yes_no_to_bool(state.get("sb_allow_loyalty_incentive")),
        "max_loyalty_cash": float(state.get("sb_max_loyalty_incentive") or 0),
        "allow_conquest": yes_no_to_bool(state.get("sb_allow_conquest_incentive")),
        "max_conquest_cash": float(state.get("sb_max_conquest_incentive") or 0),
        "max_total_support_budget": float(
            state.get("sb_max_total_support_budget") or 1e12
        ),
        "min_acceptable_remaining_margin": float(
            state.get("sb_min_acceptable_remaining_margin") or 0
        ),
        "min_conversion_lift_vs_no_support": float(
            (state.get("sb_min_meaningful_lift_pp") or 2.0) / 100.0
        ),
        "allowed_loan_terms": terms,
    }


def _rate_support_grid(mx: int, state: dict[str, Any], demo: dict[str, Any]) -> list[int]:
    step = int(
        state.get("sb_rate_support_step") or demo.get("rate_support_step", 25)
    )
    step = max(1, step)
    return [r for r in range(0, max(0, int(mx)) + 1, step)]


def _cash_steps_500(max_usd: float, state: dict[str, Any], demo: dict[str, Any]) -> list[float]:
    step = float(
        state.get("sb_cash_support_step") or demo.get("cash_support_step", 500)
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


def _fine_optimization_grids(
    constraints: dict[str, Any],
    state: dict[str, Any],
    demo: dict[str, Any],
) -> tuple:
    return (
        _rate_support_grid(int(constraints["max_rate_support"]), state, demo),
        _cash_steps_500(float(constraints["max_oem_customer_cash"]), state, demo),
        _cash_steps_500(float(constraints["max_dealer_cash"]), state, demo),
        _cash_steps_500(float(constraints["max_loyalty_cash"]), state, demo)
        if constraints["allow_loyalty"]
        else [0.0],
        _cash_steps_500(float(constraints["max_conquest_cash"]), state, demo)
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
    progress_sink: Callable[[float, str], None] | None = None,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    t_all = time.perf_counter()
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

    margin = float(base_inputs["expected_unit_margin"])
    cm = float(cost_multiplier)

    t_build = time.perf_counter()
    scenarios: list[dict[str, Any]] = []
    row_models: list[dict[str, Any]] = []
    metas: list[tuple[Any, ...]] = []
    _emit_worker_progress(
        progress_sink,
        0.62,
        "Scoring scenarios with the conversion model…",
    )
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
        rm = calculate_model_features(scen)
        scenarios.append(scen)
        row_models.append(rm)
        metas.append((idx_offset + i, sup, cc, dc, lc, cq, term))
    t_pack = time.perf_counter()

    X, err_m = align_rows_for_batch_predict(row_models, schema, sample_defaults)
    t_align = time.perf_counter()
    if err_m or X is None:
        return None, err_m or "Alignment failed in multi-lever sweep."
    try:
        prob_col = predict_conversion_positive_column(pipeline, X)
    except Exception as e:
        return None, str(e)
    t_pred = time.perf_counter()
    _emit_worker_progress(progress_sink, 0.76, "Applying feasibility metrics and lifts…")
    probs = np.asarray(prob_col, dtype=np.float64).reshape(-1)
    if probs.shape[0] != len(scenarios):
        return None, "Prediction length mismatch in multi-lever sweep."

    rows: list[dict[str, Any]] = []
    for scen, rm, p, meta in zip(scenarios, row_models, probs, metas):
        idx_i, sup, cc, dc, lc, cq, term = meta
        p_f = float(p)
        p_pkg0 = get_p_no_incentive_package(int(term))
        p_rate0 = get_p_zero_rate_same_cash(
            float(cc), float(dc), float(lc), float(cq), int(term)
        )
        lift_vs_baseline = p_f - float(p_pkg0)
        lift_marginal_rate = p_f - float(p_rate0)
        la = float(scen["loan_amount"])
        esc = (
            la * (float(sup) / 10000.0) * cm
            + float(cc)
            + float(dc)
            + float(lc)
            + float(cq)
        )
        ev = p_f * margin - esc
        eff = lift_vs_baseline / max(esc, 1.0)
        rem_margin = margin - esc

        rows.append(
            {
                "scenario_idx": int(idx_i),
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
                "conversion_probability": p_f,
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
    t_done = time.perf_counter()
    _log.info(
        "[OPT_WORKER] score_list n=%d feature_engineering=%.3fs align_model_df=%.3fs "
        "predict_proba=%.3fs support_cost_and_lifts_assemble=%.3fs total=%.3fs",
        len(combos),
        t_pack - t_build,
        t_align - t_pack,
        t_pred - t_align,
        t_done - t_pred,
        t_done - t_all,
    )
    return rows, None


def select_recommended_expected_value(enriched_df: pd.DataFrame) -> pd.Series:
    max_ev = float(enriched_df["expected_value"].max())
    pool = enriched_df[enriched_df["expected_value"] >= max_ev * 0.95].copy()
    if pool.empty:
        pool = enriched_df.copy()
    return pool.sort_values(
        ["estimated_support_cost", "dealer_rate_support_level"],
        ascending=[True, True],
    ).iloc[0]


def select_recommended_constrained(
    enriched_df: pd.DataFrame,
    expected_unit_margin: float,
    constraints: dict[str, Any],
) -> tuple[pd.Series, pd.DataFrame, bool]:
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
    ui_state: dict[str, Any],
    demo_defaults: dict[str, Any],
    *,
    progress_sink: Callable[[float, str], None] | None = None,
) -> tuple[pd.DataFrame | None, str | None, dict[str, Any] | None]:
    t0 = time.perf_counter()
    t_grids = time.perf_counter()
    fine_grids = _fine_optimization_grids(
        optimization_constraints, ui_state, demo_defaults
    )
    fine_combos = list(itertools.product(*fine_grids))
    n_fine = len(fine_combos)
    t_after_grid = time.perf_counter()
    _log.info(
        "[OPT_WORKER] generate_scenarios rows=%d wall=%.3fs",
        n_fine,
        t_after_grid - t_grids,
    )
    _emit_worker_progress(progress_sink, 0.20, "Generating scenarios…")

    if n_fine <= MAX_FULL_ENUMERATION:
        _emit_worker_progress(progress_sink, 0.38, "Preparing model input…")
        t_score0 = time.perf_counter()
        rows, err = _score_offer_combination_list(
            base_inputs,
            fine_combos,
            pipeline,
            schema,
            sample_defaults,
            cost_multiplier,
            idx_offset=0,
            progress_sink=progress_sink,
        )
        t_score1 = time.perf_counter()
        if err or rows is None:
            return None, err or "Prediction failed in multi-lever sweep.", None
        t_df0 = time.perf_counter()
        df = pd.DataFrame(rows)
        t_df1 = time.perf_counter()
        elapsed = time.perf_counter() - t0
        _log.info(
            "[OPT_WORKER] full_grid score+assemble wall=%.3fs build_dataframe wall=%.3fs total=%.3fs",
            t_score1 - t_score0,
            t_df1 - t_df0,
            elapsed,
        )
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
    _emit_worker_progress(progress_sink, 0.20, "Generating scenarios (coarse grid)…")
    _emit_worker_progress(progress_sink, 0.38, "Preparing model input…")
    t_coarse0 = time.perf_counter()
    rows_c, err = _score_offer_combination_list(
        base_inputs,
        list(coarse_combos),
        pipeline,
        schema,
        sample_defaults,
        cost_multiplier,
        idx_offset=0,
        progress_sink=progress_sink,
    )
    t_coarse1 = time.perf_counter()
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
    t_ref0 = time.perf_counter()
    if refined_combos:
        _emit_worker_progress(progress_sink, 0.42, "Refining neighborhood scenarios…")
        rows_r, err_r = _score_offer_combination_list(
            base_inputs,
            refined_combos,
            pipeline,
            schema,
            sample_defaults,
            cost_multiplier,
            idx_offset=len(rows_c),
            progress_sink=progress_sink,
        )
        if err_r or rows_r is None:
            return None, err_r or "Prediction failed in refined optimization.", None
    t_ref1 = time.perf_counter()

    all_rows = rows_c + rows_r
    for i, row in enumerate(all_rows):
        row["scenario_idx"] = i

    t_df_all0 = time.perf_counter()
    df = pd.DataFrame(all_rows)
    t_df_all1 = time.perf_counter()
    elapsed = time.perf_counter() - t0
    _log.info(
        "[OPT_WORKER] coarse_to_fine coarse_score=%.3fs refine_score=%.3fs build_dataframe=%.3fs "
        "coarse_n=%d refine_n=%d total=%.3fs",
        t_coarse1 - t_coarse0,
        t_ref1 - t_ref0,
        t_df_all1 - t_df_all0,
        len(rows_c),
        len(rows_r),
        elapsed,
    )
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
    mx = float(enriched_df["conversion_probability"].max())
    ties = enriched_df[enriched_df["conversion_probability"] == mx]
    return ties.sort_values(
        ["estimated_support_cost", "dealer_rate_support_level"],
        ascending=[True, True],
    ).iloc[0]


def select_recommended_efficient_scenario(enriched_df: pd.DataFrame) -> pd.Series:
    d = enriched_df.sort_values("dealer_rate_support_level", ascending=True).reset_index(drop=True)
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
    if apr_gap_bps < -50:
        return ("Dealer Advantage", "Dealer offer is meaningfully better")
    if apr_gap_bps <= 50:
        return ("Neutral Position", "Offers are roughly comparable")
    return ("Competitor Advantage", "Competing offer appears stronger")
