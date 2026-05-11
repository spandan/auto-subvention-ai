"""Reusable form primitives — design-system aligned (dense, hierarchical)."""

from __future__ import annotations

import re
from typing import Any, Callable

from nicegui import ui

from ui.theme import SLIDER_SCALE_TOOLTIP


def _merge_slider_help(help_text: str) -> str:
    return f"{help_text.strip()}\n\n{SLIDER_SCALE_TOOLTIP}"


def format_help_tooltip(text: str) -> str:
    """
    Tooltip copy: preserve explicit newlines; otherwise one line per sentence when
    there are multiple period-separated clauses (readable on hover with white-space: pre-line).
    """
    t = text.strip()
    if not t:
        return t
    if "\n" in t:
        return re.sub(r"\n{3,}", "\n\n", t).strip()

    if ". " not in t:
        return t
    chunks = [c.strip() for c in t.split(". ") if c.strip()]
    if len(chunks) <= 1:
        return t
    lines: list[str] = []
    for chunk in chunks:
        if chunk.endswith((".", "!", "?")):
            lines.append(chunk)
        else:
            lines.append(f"{chunk}.")
    return "\n".join(lines)


_Q_FIELD_PROPS = "dense outlined rounded"


def section_heading(text: str, *, level: str = "h2") -> None:
    """LEVEL 2 — Section headers inside wizard steps."""
    cls = "ds-h2" if level == "h2" else "ds-dash-title"
    ui.label(text).classes(cls)


def micro_note(text: str) -> None:
    """LEVEL 5 — One-line micro guidance (e.g. once-per-column scale hint)."""
    ui.label(text).classes("ds-micro")


def help_tip(text: str) -> ui.icon:
    ic = ui.icon("help_outline", size="xs").classes("cursor-pointer shrink-0 ds-help-tip")
    ic.style("color: #9CA3AF; font-size: 16px; width:16px; height:16px;")
    ic.tooltip(format_help_tooltip(text))
    return ic


def dti_kpi_card(display_pct: str, *, subtitle: str | None = None) -> None:
    """Computed DTI as compact executive KPI."""
    with ui.element("div").classes("ds-kpi-chip w-full"):
        ui.label("Debt-to-income (computed)").classes("ds-kpi-chip-label")
        ui.label(display_pct).classes("ds-kpi-chip-value")
        hint = subtitle or "Monthly debt payments ÷ gross monthly income."
        ui.label(hint).classes("ds-kpi-chip-hint")


def labeled_slider(
    *,
    label: str,
    help_text: str,
    min_v: float,
    max_v: float,
    step: float,
    state: dict[str, Any],
    key: str,
    on_change: Callable[[], None] | None = None,
    is_int: bool = True,
    include_scale_in_tooltip: bool = True,
) -> None:
    """LEVEL 3–4: compact slider; scale lives in tooltip, not repeated body copy."""
    raw = (
        _merge_slider_help(help_text) if include_scale_in_tooltip else help_text.strip()
    )
    with ui.column().classes("ds-field w-full"):
        with ui.row().classes("ds-field-head w-full"):
            ui.label(label).classes("ds-label")
            help_tip(raw)
        v = state.get(key, min_v)
        sl = ui.slider(min=min_v, max=max_v, step=step, value=v)
        sl.classes("w-full")

        def _sync(e: Any) -> None:
            nv = int(round(e.value)) if is_int else float(e.value)
            state[key] = nv
            if on_change:
                on_change()

        sl.on_value_change(_sync)


def labeled_number(
    *,
    label: str,
    help_text: str,
    state: dict[str, Any],
    key: str,
    min_v: float | None = None,
    max_v: float | None = None,
    on_change: Callable[[], None] | None = None,
) -> None:
    with ui.column().classes("ds-field w-full"):
        with ui.row().classes("ds-field-head w-full"):
            ui.label(label).classes("ds-label")
            help_tip(help_text.strip())
        v = float(state.get(key) or 0)
        kw: dict[str, Any] = {"value": v}
        if min_v is not None:
            kw["min"] = min_v
        if max_v is not None:
            kw["max"] = max_v
        inp = ui.number(**kw).props(_Q_FIELD_PROPS)
        inp.classes("w-full")

        def _sync(e: Any) -> None:
            state[key] = float(e.value)
            if on_change:
                on_change()

        inp.on_value_change(_sync)


def labeled_select(
    *,
    label: str,
    help_text: str,
    options: list[str],
    state: dict[str, Any],
    key: str,
    on_change: Callable[[], None] | None = None,
) -> None:
    with ui.column().classes("ds-field w-full"):
        with ui.row().classes("ds-field-head w-full"):
            ui.label(label).classes("ds-label")
            help_tip(help_text.strip())
        sel = ui.select(options, value=str(state.get(key) or options[0])).props(
            _Q_FIELD_PROPS
        )
        sel.classes("w-full")

        def _sync(e: Any) -> None:
            state[key] = e.value
            if on_change:
                on_change()

        sel.on_value_change(_sync)


def labeled_multiselect_terms(
    *,
    label: str,
    help_text: str,
    options: list[int],
    state: dict[str, Any],
    key: str,
    on_change: Callable[[], None] | None = None,
) -> None:
    with ui.column().classes("ds-field w-full"):
        with ui.row().classes("ds-field-head w-full"):
            ui.label(label).classes("ds-label")
            help_tip(help_text.strip())
        cur = state.get(key) or [60]
        if not isinstance(cur, list):
            cur = [int(cur)]
        sel = ui.select(
            options=[str(x) for x in options],
            multiple=True,
            value=[str(x) for x in cur],
        ).props(_Q_FIELD_PROPS)
        sel.classes("w-full")

        def _sync(e: Any) -> None:
            vals = [int(x) for x in e.value]
            state[key] = vals
            if on_change:
                on_change()

        sel.on_value_change(_sync)


def yes_no_select(
    *,
    label: str,
    help_text: str,
    state: dict[str, Any],
    key: str,
    on_change: Callable[[], None] | None = None,
) -> None:
    opts = ["Yes", "No"]
    with ui.column().classes("ds-field w-full"):
        with ui.row().classes("ds-field-head w-full"):
            ui.label(label).classes("ds-label")
            help_tip(help_text.strip())
        sel = ui.select(opts, value=str(state.get(key) or "No")).props(_Q_FIELD_PROPS)
        sel.classes("w-full")

        def _sync(e: Any) -> None:
            state[key] = e.value
            if on_change:
                on_change()

        sel.on_value_change(_sync)


# Back-compat alias used by dashboard
def section_title(text: str) -> None:
    section_heading(text, level="h2")
