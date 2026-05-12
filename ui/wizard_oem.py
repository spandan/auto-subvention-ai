"""OEM incentive planning wizard — shared ``sb_*`` state, synthetic buyer from archetypes."""

from __future__ import annotations

import json
from typing import Any, Callable

from nicegui import ui

from services.constants import OEM_WIZARD_STEPS, OEM_WIZARD_STEP_TITLE
from services.feature_engineering import yes_no_to_bool
from services.oem_synthetic_profile import compute_oem_customer_assumptions, oem_archetype_labels
from ui.components import (
    labeled_number,
    labeled_select,
    labeled_slider,
    section_title,
    yes_no_select,
)
from ui.wizard import (
    render_dealer_step_competitor,
    render_dealer_step_dealer_inv,
    render_dealer_step_financing,
    render_dealer_step_macro,
    render_dealer_step_vehicle,
)


def _step_oem_buyer(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Target Customer Archetype")
            labeled_select(
                label="Primary archetype",
                help_text="Representative buyer used internally for scoring (same model as dealer mode).",
                options=list(oem_archetype_labels()),
                state=state,
                key="oem_archetype",
                on_change=redraw,
            )
            yes_no_select(
                label="Use target customer mix (blend)",
                help_text="When enabled, Prime / Near prime / Subprime percentages replace the single archetype.",
                state=state,
                key="oem_use_mix",
                on_change=redraw,
            )
        with ui.column().classes("ds-col-stack w-full"):
            if yes_no_to_bool(state.get("oem_use_mix")):
                section_title("Target Customer Mix")
                labeled_number(
                    label="Prime %",
                    help_text="Weight for prime-family style assumptions.",
                    state=state,
                    key="oem_prime_pct",
                    min_v=0,
                    max_v=100,
                    on_change=redraw,
                )
                labeled_number(
                    label="Near prime %",
                    help_text="Weight for near-prime style assumptions.",
                    state=state,
                    key="oem_near_prime_pct",
                    min_v=0,
                    max_v=100,
                    on_change=redraw,
                )
                labeled_number(
                    label="Subprime %",
                    help_text="Weight for payment-sensitive / subprime style assumptions.",
                    state=state,
                    key="oem_subprime_pct",
                    min_v=0,
                    max_v=100,
                    on_change=redraw,
                )
            else:
                ui.label(
                    "Enable “Use target customer mix” to blend credit tiers for regional planning."
                ).classes("text-xs").style("color:#64748b;line-height:1.45;margin-top:8px;")

    snap = compute_oem_customer_assumptions(state)
    with ui.expansion("View Assumed Customer Parameters", value=False).classes(
        "w-full rounded-xl oem-assumed-expansion"
    ).style("border:1px solid #e5e7eb;margin-top:12px;background:#fafafa;"):
        ui.label(
            "These values feed the same conversion model as dealer mode; they update when you "
            "change archetype or mix."
        ).classes("text-xs").style("color:#64748b;padding:8px 0;")
        try:
            txt = json.dumps(snap, indent=2, default=str)
        except TypeError:
            txt = str(snap)
        ui.code(txt).classes("text-xs w-full max-h-64 overflow-auto")


def _step_oem_vehicle_extras(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    section_title("Program & volume targets")
    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            labeled_number(
                label="Target sales volume (units / month, regional proxy)",
                help_text="Used for planning KPIs after optimization (not a model input).",
                state=state,
                key="oem_target_sales_volume",
                min_v=1,
                max_v=5000,
                on_change=redraw,
            )
            labeled_number(
                label="Inventory reduction target (%)",
                help_text="Planning goal for aged inventory reduction.",
                state=state,
                key="oem_inventory_reduction_target_pct",
                min_v=0,
                max_v=50,
                on_change=redraw,
            )
        with ui.column().classes("ds-col-stack w-full"):
            labeled_number(
                label="Market share target (%)",
                help_text="Strategic share goal for the region / segment.",
                state=state,
                key="oem_market_share_target_pct",
                min_v=0,
                max_v=40,
                on_change=redraw,
            )


def _step_oem_market_bundle(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    render_dealer_step_macro(state, redraw)
    section_title("Regional demand conditions")
    labeled_slider(
        label="Regional demand intensity",
        help_text="Higher = stronger regional pull (displayed on OEM results; nudges planning narrative only).",
        min_v=1,
        max_v=10,
        step=1,
        state=state,
        key="oem_regional_demand_ui",
        on_change=redraw,
    )


def render_oem_wizard(
    *,
    state: dict[str, Any],
    redraw: Callable[[], None],
    run_analysis: Callable[..., Any],
    optimization_running: bool = False,
) -> None:
    step = int(state.get("oem_wizard_step") or 0)
    step = max(0, min(step, len(OEM_WIZARD_STEPS) - 1))
    state["oem_wizard_step"] = step
    sec = OEM_WIZARD_STEPS[step]

    with ui.column().classes("ds-card-step"):
        ui.label(f"Step {step + 1} of {len(OEM_WIZARD_STEPS)}").classes("ds-step-meta")
        ui.label(OEM_WIZARD_STEP_TITLE.get(sec, sec)).classes("wizard-step-title")

        if sec == "oem_buyer":
            _step_oem_buyer(state, redraw)
        elif sec == "oem_vehicle":
            render_dealer_step_vehicle(state, redraw)
            _step_oem_vehicle_extras(state, redraw)
        elif sec == "oem_dealer_inv":
            render_dealer_step_dealer_inv(state, redraw)
        elif sec == "oem_market":
            _step_oem_market_bundle(state, redraw)
        elif sec == "oem_competitor":
            render_dealer_step_competitor(state, redraw)
        elif sec == "oem_financing":
            render_dealer_step_financing(state, redraw)

        with ui.row().classes("ds-wizard-actions w-full justify-between items-center"):
            def back() -> None:
                state["oem_wizard_step"] = max(0, int(state.get("oem_wizard_step") or 0) - 1)
                redraw()

            def nxt() -> None:
                state["oem_wizard_step"] = min(
                    len(OEM_WIZARD_STEPS) - 1, int(state.get("oem_wizard_step") or 0) + 1
                )
                redraw()

            b_back = ui.button("Back", on_click=back).props("flat dense no-caps")
            b_back.set_enabled(step > 0)
            if step < len(OEM_WIZARD_STEPS) - 1:
                ui.button("Next", on_click=nxt).props("unelevated dense no-caps").classes(
                    "btn-cta btn-cta--slate"
                )
            else:
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    run_btn = ui.button("Run OEM Planning", on_click=run_analysis).props(
                        "unelevated dense no-caps"
                    ).classes("btn-cta btn-cta--oem")
                    run_btn.set_enabled(not optimization_running)
                    if optimization_running:
                        ui.label("Optimization running…").classes("text-xs").style(
                            "color:#64748b;"
                        )


def render_oem_section_for_edit(
    state: dict[str, Any], section: str, redraw: Callable[[], None]
) -> None:
    """Dashboard edit drawer for OEM sections."""
    if section == "oem_buyer":
        _step_oem_buyer(state, redraw)
    elif section == "oem_vehicle":
        render_dealer_step_vehicle(state, redraw)
        _step_oem_vehicle_extras(state, redraw)
    elif section == "oem_dealer_inv":
        render_dealer_step_dealer_inv(state, redraw)
    elif section == "oem_market":
        _step_oem_market_bundle(state, redraw)
    elif section == "oem_competitor":
        render_dealer_step_competitor(state, redraw)
    elif section == "oem_financing":
        render_dealer_step_financing(state, redraw)
    else:
        ui.label(f"Unknown section: {section}").classes("text-sm")
