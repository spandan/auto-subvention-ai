"""Guided multi-step input wizard before the first optimization run."""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from services.constants import (
    BODY_STYLES_UI,
    CUSTOMER_SEGMENTS,
    DEALER_SIZE_TIERS,
    DOW_LABELS,
    FUEL_TYPES_UI,
    MAKES,
    MODEL_BY_MAKE,
    MONTH_LABELS,
    MONTH_OPTIONS,
    PRIMARY_COMPETITORS,
    REGIONS,
    SALES_TYPES_UI,
    SIDEBAR_SECTION_ORDER,
    STATES,
    VEHICLE_SEGMENTS,
    WIZARD_STEP_TITLE,
)
from services.feature_engineering import business_dti_ratio
from ui.components import (
    dti_kpi_card,
    help_tip,
    labeled_multiselect_terms,
    labeled_number,
    labeled_select,
    labeled_slider,
    micro_note,
    section_title,
    yes_no_select,
)

_STEPS = list(SIDEBAR_SECTION_ORDER)


def render_section_editor(
    state: dict[str, Any], section: str, redraw: Callable[[], None]
) -> None:
    """Compact re-entry of a single wizard section (dashboard left rail)."""
    if section == "customer":
        _step_customer(state, redraw)
    elif section == "vehicle":
        _step_vehicle(state, redraw)
    elif section == "dealer_inv":
        _step_dealer(state, redraw)
    elif section == "financing":
        _step_financing(state, redraw)
    elif section == "competitor":
        _step_competitor(state, redraw)
    elif section == "macro":
        _step_macro(state, redraw)


def render_market_section(
    state: dict[str, Any], redraw: Callable[[], None]
) -> None:
    """Competitor + macro — used when editing Market from results (single drawer)."""
    _step_competitor(state, redraw)
    ui.separator().style("margin: 14px 0; background: rgba(148,163,184,0.35); height: 1px;")
    _step_macro(state, redraw)


def render_section_for_edit(
    state: dict[str, Any], section: str, redraw: Callable[[], None]
) -> None:
    """Edit drawer: competitor+macro bundled as `market`; id otherwise matches wizard."""
    if section == "market":
        render_market_section(state, redraw)
    else:
        render_section_editor(state, section, redraw)


def _ensure_model_for_make(state: dict[str, Any]) -> None:
    mk = str(state.get("sb_make") or MAKES[0])
    opts = MODEL_BY_MAKE.get(mk, MODEL_BY_MAKE[MAKES[0]])
    if str(state.get("sb_model_name")) not in opts:
        state["sb_model_name"] = opts[0]


def render_wizard(
    *,
    state: dict[str, Any],
    redraw: Callable[[], None],
    run_analysis: Callable[..., Any],
    optimization_running: bool = False,
) -> None:
    step = int(state.get("wizard_step") or 0)
    step = max(0, min(step, len(_STEPS) - 1))
    state["wizard_step"] = step
    sec = _STEPS[step]

    with ui.column().classes("ds-card-step"):
        ui.label(f"Step {step + 1} of {len(_STEPS)}").classes("ds-step-meta")
        ui.label(WIZARD_STEP_TITLE.get(sec, sec)).classes("wizard-step-title")

        if sec == "customer":
            _step_customer(state, redraw)
        elif sec == "vehicle":
            _step_vehicle(state, redraw)
        elif sec == "dealer_inv":
            _step_dealer(state, redraw)
        elif sec == "financing":
            _step_financing(state, redraw)
        elif sec == "competitor":
            _step_competitor(state, redraw)
        elif sec == "macro":
            _step_macro(state, redraw)

        with ui.row().classes("ds-wizard-actions w-full justify-between items-center"):
            def back() -> None:
                state["wizard_step"] = max(0, int(state.get("wizard_step") or 0) - 1)
                redraw()

            def nxt() -> None:
                state["wizard_step"] = min(
                    len(_STEPS) - 1, int(state.get("wizard_step") or 0) + 1
                )
                redraw()

            b_back = ui.button("Back", on_click=back).props("flat dense no-caps")
            b_back.set_enabled(step > 0)
            if step < len(_STEPS) - 1:
                ui.button("Next", on_click=nxt).props("unelevated dense no-caps").classes(
                    "btn-cta btn-cta--slate"
                )
            else:
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    run_btn = ui.button("Run Optimization", on_click=run_analysis).props(
                        "unelevated dense no-caps"
                    ).classes("btn-cta btn-cta--dealer")
                    run_btn.set_enabled(not optimization_running)
                    if optimization_running:
                        ui.label("Optimization running…").classes("text-xs").style(
                            "color:#64748b;"
                        )


def _step_customer(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Credit & capacity")
            labeled_number(
                label="Representative FICO score",
                help_text="Credit score used for banding and tiering.",
                state=state,
                key="sb_fico_score",
                min_v=300,
                max_v=850,
            )
            labeled_number(
                label="Monthly gross income ($)",
                help_text="Pre-tax household income used for DTI and capacity.",
                state=state,
                key="sb_monthly_income",
                min_v=0,
                on_change=redraw,
            )
            labeled_number(
                label="Monthly debt payments ($)",
                help_text="Non-housing monthly obligations used for DTI.",
                state=state,
                key="sb_monthly_debt_payments",
                min_v=0,
                on_change=redraw,
            )
            dti = business_dti_ratio(state)
            dti_kpi_card(f"{100.0 * dti:.2f}%")
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Attitudes & intent")
            micro_note(
                "1–10 behavioral sliders — hover each field’s ? for scale detail."
            )
            labeled_slider(
                label="Price sensitivity",
                help_text="How strongly payment and APR differences influence choice.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_price_sensitivity_ui",
            )
            labeled_slider(
                label="Purchase urgency",
                help_text="How quickly the customer needs to transact.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_purchase_urgency_ui",
            )
            labeled_slider(
                label="Brand preference / loyalty",
                help_text="Attachment to this OEM/dealer relative to alternatives.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_brand_preference_ui",
            )
            labeled_slider(
                label="Purchase intent",
                help_text="Strength of intent to buy this class of vehicle soon.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_purchase_intent_ui",
            )
            labeled_slider(
                label="Customer sentiment",
                help_text=(
                    "How positive or negative the shopper feels right now about moving "
                    "forward with this deal—trust, optimism, urgency to leave, frustration "
                    "with terms, excitement about the vehicle, etc. "
                    "Unlike other 1–10 inputs (which scale as value ÷ 10), sentiment is "
                    "centered on neutral: the model uses (value − 5) ÷ 5, so 5 maps to 0 "
                    "(neutral mood), 1 maps to −1 (strongly negative), and 10 maps to "
                    "+1 (strongly positive). "
                    "Use lower half of the slider for doubtful or strained conversations; "
                    "upper half for cooperative, upbeat buyers."
                ),
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_sentiment_ui",
            )
            labeled_select(
                label="Customer segment",
                help_text="Behavioral segment label used in the model.",
                options=CUSTOMER_SEGMENTS,
                state=state,
                key="sb_customer_segment",
            )
            labeled_slider(
                label="EV affinity",
                help_text="Interest in electrified powertrains.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_ev_affinity_ui",
            )
            labeled_slider(
                label="Family / utility need",
                help_text="Importance of space, safety, and practicality.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_family_utility_ui",
            )
            labeled_slider(
                label="Truck affinity",
                help_text="Preference for truck/SUV capability.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_truck_affinity_ui",
            )
            labeled_slider(
                label="Conquest likelihood",
                help_text="Willingness to switch brands for the right offer.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_conquest_likelihood_ui",
            )


def _step_vehicle(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    _ensure_model_for_make(state)

    def on_make(_: Any = None) -> None:
        _ensure_model_for_make(state)
        redraw()

    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Vehicle identity")
            labeled_select(
                label="Make",
                help_text="OEM brand for the quoted vehicle.",
                options=MAKES,
                state=state,
                key="sb_make",
                on_change=on_make,
            )
            mk = str(state.get("sb_make") or MAKES[0])
            model_opts = MODEL_BY_MAKE.get(mk, MODEL_BY_MAKE[MAKES[0]])
            labeled_select(
                label="Model",
                help_text="Model line used for competitive positioning features.",
                options=model_opts,
                state=state,
                key="sb_model_name",
            )
            labeled_number(
                label="Model year",
                help_text="Vehicle model year (can include future model years).",
                state=state,
                key="sb_model_year",
                min_v=2000,
                max_v=2030,
            )
            labeled_select(
                label="Trim",
                help_text="Trim level / equipment group.",
                options=[
                    "Base",
                    "Sport",
                    "Premium",
                    "Limited",
                    "Touring",
                    "Platinum",
                ],
                state=state,
                key="sb_trim",
            )
            labeled_select(
                label="Body style",
                help_text="High-level body style for training alignment.",
                options=BODY_STYLES_UI,
                state=state,
                key="sb_body_style",
            )
            labeled_select(
                label="Fuel type",
                help_text="Maps to model fuel category tokens.",
                options=FUEL_TYPES_UI,
                state=state,
                key="sb_fuel_type",
            )
            labeled_select(
                label="Vehicle segment",
                help_text="Retail segment classification.",
                options=VEHICLE_SEGMENTS,
                state=state,
                key="sb_vehicle_segment",
            )
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Pricing & residual context")
            labeled_number(
                label="Vehicle price ($)",
                help_text="Transaction price / MSRP basis for the quote.",
                state=state,
                key="sb_vehicle_price",
                min_v=0,
            )
            labeled_number(
                label="Vehicle age (years)",
                help_text="Age of design cycle / inventory age proxy.",
                state=state,
                key="sb_vehicle_age",
                min_v=-5,
                max_v=30,
            )
            labeled_slider(
                label="Residual strength (look & demand)",
                help_text="How strong RV / demand is for this unit.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_rv_strength_ui",
            )
            labeled_number(
                label="Residual support display (%)",
                help_text="OEM residual subsidy / enhancement as a percent.",
                state=state,
                key="sb_residual_support_pct_display",
                min_v=0,
                max_v=25,
            )
            yes_no_select(
                label="RV push brand",
                help_text="Brand is actively pushing residual-supported payments.",
                state=state,
                key="sb_rv_push_yn",
            )


def _step_dealer(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Dealer profile")
            labeled_select(
                label="Dealer size tier",
                help_text="Rooftop scale proxy.",
                options=DEALER_SIZE_TIERS,
                state=state,
                key="sb_dealer_size_tier",
            )
            yes_no_select(
                label="Metro market",
                help_text="Large metro vs non-metro.",
                state=state,
                key="sb_metro_yn",
            )
            labeled_number(
                label="Avg monthly retail units",
                help_text="Throughput proxy for the store.",
                state=state,
                key="sb_avg_monthly_retail_units",
                min_v=0,
            )
            labeled_number(
                label="Dealer margin (% display)",
                help_text="Expected front-end margin percent (display).",
                state=state,
                key="sb_dealer_margin_pct_display",
                min_v=0,
                max_v=30,
            )
            labeled_number(
                label="Expected unit margin ($)",
                help_text="Expected gross before support — used in economics.",
                state=state,
                key="sb_expected_unit_margin",
                min_v=0,
            )
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Inventory posture")
            labeled_number(
                label="Days in inventory",
                help_text="Age of this unit on the lot.",
                state=state,
                key="sb_days_in_inventory",
                min_v=0,
            )
            labeled_number(
                label="On-hand units",
                help_text="Similar units in stock.",
                state=state,
                key="sb_on_hand_units",
                min_v=0,
            )
            labeled_number(
                label="In-transit units",
                help_text="Incoming pipeline units.",
                state=state,
                key="sb_in_transit_units",
                min_v=0,
            )
            labeled_number(
                label="Aging inventory (% display)",
                help_text="Share of inventory over aged threshold.",
                state=state,
                key="sb_aging_inventory_pct_display",
                min_v=0,
                max_v=100,
            )
            yes_no_select(
                label="Stockout risk",
                help_text="Risk of losing sale due to availability.",
                state=state,
                key="sb_stockout_yn",
            )
            yes_no_select(
                label="Overstock flag",
                help_text="Excess inventory pressure.",
                state=state,
                key="sb_overstock_yn",
            )
            labeled_slider(
                label="Inventory pressure",
                help_text="Urgency to move metal from aging/supply.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_inventory_pressure_ui",
            )


def _step_financing(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    from services.constants import LOAN_TERMS

    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Deal structure (baseline)")
            labeled_number(
                label="Loan amount ($)",
                help_text="Amount financed at baseline (before incremental incentives).",
                state=state,
                key="sb_loan_amount",
                min_v=0,
            )
            labeled_number(
                label="Down payment ($)",
                help_text="Customer cash down.",
                state=state,
                key="sb_down_payment",
                min_v=0,
            )
            labeled_number(
                label="Primary loan term (months)",
                help_text="Primary quote term; must be allowed for optimization.",
                state=state,
                key="sb_primary_loan_term",
                min_v=12,
                max_v=84,
            )
            labeled_number(
                label="Standard APR (%)",
                help_text="Unsubvented program APR anchor.",
                state=state,
                key="sb_standard_apr",
                min_v=0,
                max_v=25,
            )
            labeled_number(
                label="Baseline dealer APR (%)",
                help_text="Quoted customer APR before incremental rate support.",
                state=state,
                key="sb_baseline_dealer_apr",
                min_v=0,
                max_v=25,
            )
            labeled_number(
                label="Baseline monthly payment ($)",
                help_text="Baseline payment at dealer APR (optional override).",
                state=state,
                key="sb_baseline_dealer_monthly_payment",
                min_v=0,
            )
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Optimization constraints (search bounds)")
            labeled_number(
                label="Max OEM / customer cash ($)",
                help_text="Upper bound on OEM-to-customer cash in search.",
                state=state,
                key="sb_max_oem_customer_cash",
                min_v=0,
            )
            labeled_number(
                label="Max dealer cash support ($)",
                help_text="Upper bound on dealer-funded cash.",
                state=state,
                key="sb_max_dealer_cash_support",
                min_v=0,
            )
            labeled_number(
                label="Max APR / rate support (index)",
                help_text="Maximum dealer_rate_support_level to search (e.g. 200).",
                state=state,
                key="sb_max_apr_rate_support",
                min_v=0,
                max_v=400,
            )
            yes_no_select(
                label="Allow loyalty incentive",
                help_text="Search may include loyalty cash if enabled.",
                state=state,
                key="sb_allow_loyalty_incentive",
            )
            labeled_number(
                label="Max loyalty incentive ($)",
                help_text="Cap on loyalty cash if allowed.",
                state=state,
                key="sb_max_loyalty_incentive",
                min_v=0,
            )
            yes_no_select(
                label="Allow conquest incentive",
                help_text="Search may include conquest cash if enabled.",
                state=state,
                key="sb_allow_conquest_incentive",
            )
            labeled_number(
                label="Max conquest incentive ($)",
                help_text="Cap on conquest cash if allowed.",
                state=state,
                key="sb_max_conquest_incentive",
                min_v=0,
            )
            labeled_number(
                label="Max total support budget ($)",
                help_text="Hard cap on sum of estimated support components.",
                state=state,
                key="sb_max_total_support_budget",
                min_v=0,
            )
            labeled_number(
                label="Minimum acceptable remaining margin ($)",
                help_text="Feasibility floor on margin after support.",
                state=state,
                key="sb_min_acceptable_remaining_margin",
                min_v=0,
            )
            labeled_number(
                label="Minimum meaningful lift (percentage points)",
                help_text="Minimum conversion lift vs no-support package for feasibility.",
                state=state,
                key="sb_min_meaningful_lift_pp",
                min_v=0,
                max_v=20,
            )
            labeled_multiselect_terms(
                label="Allowed loan terms",
                help_text="Terms included in the optimization grid.",
                options=LOAN_TERMS,
                state=state,
                key="sb_allowed_loan_terms",
            )
            labeled_number(
                label="Rate support grid step",
                help_text="Step for fine-grid rate support enumeration.",
                state=state,
                key="sb_rate_support_step",
                min_v=1,
                max_v=100,
            )
            labeled_number(
                label="Cash grid step ($)",
                help_text="Step for fine-grid cash enumeration.",
                state=state,
                key="sb_cash_support_step",
                min_v=50,
                max_v=5000,
            )
            labeled_number(
                label="Support cost multiplier",
                help_text="Scales estimated rate-support cost for economics.",
                state=state,
                key="sb_cost_multiplier",
                min_v=0.1,
                max_v=2.0,
            )


def _step_competitor(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Competitive landscape")
            labeled_select(
                label="Primary competitor",
                help_text="Main alternative OEM considered by the shopper.",
                options=PRIMARY_COMPETITORS,
                state=state,
                key="sb_primary_competitor",
            )
            labeled_number(
                label="Competitor APR (%)",
                help_text="Benchmark alternative APR.",
                state=state,
                key="sb_competitor_apr",
                min_v=0,
                max_v=25,
            )
            labeled_number(
                label="Competitor monthly payment ($)",
                help_text="Benchmark alternative payment.",
                state=state,
                key="sb_competitor_monthly_payment",
                min_v=0,
            )
            labeled_number(
                label="Competitor cashback ($)",
                help_text="Benchmark stacked cash.",
                state=state,
                key="sb_competitor_cashback",
                min_v=0,
            )
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Competitor intensity")
            labeled_slider(
                label="Competitor offer aggressiveness",
                help_text="How sharp the rival offer appears.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_competitor_aggr_ui",
            )
            labeled_slider(
                label="Competitor sales momentum",
                help_text="Relative showroom/share momentum for the rival.",
                min_v=1,
                max_v=10,
                step=1,
                state=state,
                key="sb_competitor_sales_ui",
            )


def _step_macro(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    cur_m = max(1, min(12, int(state.get("sb_month_of_quote") or 1)))
    cur_dow = max(0, min(6, int(state.get("sb_day_of_week_quote") or 0)))

    with ui.element("div").classes("ds-row-two w-full"):
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Rates & macro")
            labeled_number(
                label="Fed funds effective / policy anchor (%)",
                help_text="Macro rate anchor.",
                state=state,
                key="sb_fed_rate",
                min_v=0,
                max_v=15,
            )
            labeled_number(
                label="10-year Treasury yield (%)",
                help_text="Rates backdrop.",
                state=state,
                key="sb_ten_year",
                min_v=0,
                max_v=15,
            )
            labeled_number(
                label="Inflation (CPI %) (display)",
                help_text="Macro inflation context.",
                state=state,
                key="sb_inflation_cpi",
                min_v=0,
                max_v=15,
            )
            labeled_number(
                label="Base auto rate index",
                help_text="Internal composite auto financing index.",
                state=state,
                key="sb_base_auto_rate_index",
                min_v=0,
                max_v=20,
            )
            labeled_number(
                label="Market rate index",
                help_text="Market financing conditions index.",
                state=state,
                key="sb_market_rate_index",
                min_v=0,
                max_v=20,
            )
        with ui.column().classes("ds-col-stack w-full"):
            section_title("Timing & geography")
            with ui.column().classes("ds-field w-full"):
                with ui.row().classes("ds-field-head w-full"):
                    ui.label("Month of quote").classes("ds-label")
                    help_tip("Seasonality feature.")
                sel_m = ui.select(MONTH_LABELS, value=MONTH_LABELS[cur_m - 1]).props(
                    "dense outlined rounded"
                )
                sel_m.classes("w-full")

                def _mon(e: Any) -> None:
                    state["sb_month_of_quote"] = MONTH_LABELS.index(str(e.value)) + 1
                    redraw()

                sel_m.on_value_change(_mon)

            with ui.column().classes("ds-field w-full"):
                with ui.row().classes("ds-field-head w-full"):
                    ui.label("Day of week").classes("ds-label")
                    help_tip("Quote weekday.")
                sel_d = ui.select(DOW_LABELS, value=DOW_LABELS[cur_dow]).props(
                    "dense outlined rounded"
                )
                sel_d.classes("w-full")

                def _dow(e: Any) -> None:
                    state["sb_day_of_week_quote"] = DOW_LABELS.index(str(e.value))
                    redraw()

                sel_d.on_value_change(_dow)

            yes_no_select(
                label="Quarter-end pressure",
                help_text="End-of-quarter retail intensity.",
                state=state,
                key="sb_quarter_end_yn",
            )
            labeled_select(
                label="Sales type",
                help_text="Maps to model sales_type tokens.",
                options=SALES_TYPES_UI,
                state=state,
                key="sb_sales_type",
            )
            labeled_select(
                label="Region",
                help_text="US region bucket.",
                options=REGIONS,
                state=state,
                key="sb_region",
            )
            labeled_select(
                label="State",
                help_text="State bucket.",
                options=STATES,
                state=state,
                key="sb_state",
            )


# --- OEM wizard re-use: same field renderers as dealer steps (no duplicate business logic) ---


def render_dealer_step_vehicle(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    _step_vehicle(state, redraw)


def render_dealer_step_dealer_inv(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    _step_dealer(state, redraw)


def render_dealer_step_financing(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    _step_financing(state, redraw)


def render_dealer_step_competitor(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    _step_competitor(state, redraw)


def render_dealer_step_macro(state: dict[str, Any], redraw: Callable[[], None]) -> None:
    _step_macro(state, redraw)
