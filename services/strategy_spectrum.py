"""Select representative scenarios for executive strategy spectrum (no optimizer changes)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

_LEVER_KEYS: tuple[str, ...] = (
    "dealer_rate_support_level",
    "customer_cash",
    "dealer_cash",
    "loyalty_cash",
    "conquest_cash",
    "loan_term",
)


def _same_levers(a: pd.Series, b: pd.Series) -> bool:
    try:
        return bool(all(float(a[k]) == float(b[k]) for k in _LEVER_KEYS))
    except (KeyError, TypeError, ValueError):
        return False


def pick_conservative(df: pd.DataFrame, rec: pd.Series) -> pd.Series:
    """Lowest support cost among scenarios with meaningful lift; else global minimum cost."""
    d = df.copy()
    if d.empty:
        return rec
    target_lift = max(0.008, float(rec["conversion_lift_vs_baseline"]) * 0.2)
    pool = d[d["conversion_lift_vs_baseline"].astype(float) >= target_lift]
    if pool.empty:
        pool = d
    idx = pool["estimated_support_cost"].astype(float).idxmin()
    row = d.loc[idx]
    if _same_levers(row, rec) and len(pool) > 1:
        pool2 = pool[pool.index != idx]
        if not pool2.empty:
            idx2 = pool2["estimated_support_cost"].astype(float).idxmin()
            row = d.loc[idx2]
    return row


def pick_balanced_alternative(df: pd.DataFrame, rec: pd.Series, aggressive: pd.Series) -> pd.Series:
    """High economic score with a different lever mix than recommended or aggressive."""
    if df.empty:
        return rec
    d = df.sort_values("expected_value", ascending=False).reset_index(drop=True)
    for i in range(min(80, len(d))):
        row = d.iloc[i]
        if not _same_levers(row, rec) and not _same_levers(row, aggressive):
            return row
    return d.iloc[min(1, len(d) - 1)]


def pick_specialty_strategy(df: pd.DataFrame, rec: pd.Series) -> tuple[pd.Series | None, str]:
    """
    Pick a fifth card: loyalty-, APR-, or cash-skewed scenario from the strong-EV frontier.
    """
    if df.empty or len(df) < 5:
        return None, ""
    d = df.sort_values("expected_value", ascending=False).head(120).copy()
    if d.empty:
        return None, ""

    def try_pick(mask: pd.Series, label: str) -> tuple[pd.Series | None, str]:
        sub = d.loc[mask]
        if sub.empty:
            return None, ""
        # farthest from rec by simple lever distance
        best: tuple[float, pd.Series] | None = None
        for _, row in sub.iterrows():
            if _same_levers(row, rec):
                continue
            dist = sum(
                abs(float(row[k]) - float(rec[k]))
                for k in _LEVER_KEYS
            )
            if best is None or dist > best[0]:
                best = (dist, row)
        if best is None:
            return None, ""
        return best[1], label

    # Loyalty-skewed
    if (d["loyalty_cash"].astype(float) > 0).any():
        row, lab = try_pick(d["loyalty_cash"].astype(float) >= d["loyalty_cash"].astype(float).quantile(0.85), "Loyalty-focused strategy")
        if row is not None:
            return row, lab

    # APR-skewed (rate support index)
    row, lab = try_pick(
        d["dealer_rate_support_level"].astype(float) >= d["dealer_rate_support_level"].astype(float).quantile(0.8),
        "APR-forward strategy",
    )
    if row is not None:
        return row, lab

    # Cash-skewed
    cash = d["customer_cash"].astype(float) + d["dealer_cash"].astype(float)
    d = d.assign(_cash=cash)
    row, lab = try_pick(d["_cash"] >= d["_cash"].quantile(0.8), "Cash-forward strategy")
    if row is not None:
        return row, lab

    return None, ""


@dataclass
class StrategySpectrumPack:
    conservative: pd.Series
    balanced: pd.Series
    recommended: pd.Series
    aggressive: pd.Series
    optional: pd.Series | None
    optional_label: str


def build_strategy_spectrum_pack(
    df: pd.DataFrame,
    rec: pd.Series,
    aggressive: pd.Series,
) -> StrategySpectrumPack:
    cons = pick_conservative(df, rec)
    bal = pick_balanced_alternative(df, rec, aggressive)
    opt_row, opt_lab = pick_specialty_strategy(df, rec)
    return StrategySpectrumPack(
        conservative=cons,
        balanced=bal,
        recommended=rec,
        aggressive=aggressive,
        optional=opt_row,
        optional_label=opt_lab or "Alternative mix",
    )
