"""
Auto Finance Subvention Optimization Simulator — NiceGUI single-process app.

Run: python app.py
Railway: respects PORT environment variable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
import warnings
from typing import Any

import pandas as pd
from nicegui import Client, run, ui

from services.feature_engineering import (
    build_business_inputs,
    get_demo_defaults,
    session_defaults_from_demo,
    validate_business_inputs,
)
from services.model_service import (
    assert_artifacts_present,
    get_feature_schema,
    get_sample_defaults,
    load_model,
)
from services.optimizer import (
    apply_offer_scenario_levers,
    build_optimization_constraints,
    run_constraint_based_offer_scenarios,
    select_highest_conversion_scenario,
    select_recommended_constrained,
    _predict_scenario_row,
)
from ui.dashboard import render_dashboard
from ui.loading_overlay import OptimizationLoadingOverlay
from ui.theme import PAGE_MAX_W, PAGE_RESULTS_MAX_W, theme_css
from ui.wizard import render_section_for_edit, render_wizard

logger = logging.getLogger(__name__)


def _ensure_app_run_logger() -> None:
    """Emit INFO for run/optimize lifecycle even when the root logger is quiet (e.g. some uvicorn setups)."""
    if logger.handlers:
        return
    _h = logging.StreamHandler()
    _h.setLevel(logging.INFO)
    _h.setFormatter(logging.Formatter("%(levelname)s [subvention] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)
    logger.propagate = False


_ensure_app_run_logger()


class AppModel:
    """In-memory UI state + analysis outputs (single worker process)."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = session_defaults_from_demo()
        self.state["ui_mode"] = "wizard"
        self.state["wizard_step"] = 0
        self.state.setdefault("dashboard_edit_section", "customer")
        self.pipeline: Any = None
        self.schema: dict[str, Any] = {}
        self.sample_defaults: dict[str, Any] = {}
        self.demo_defaults: dict[str, Any] = get_demo_defaults()

        self.result_df: pd.DataFrame | None = None
        self.rec_row: pd.Series | None = None
        self.aggressive_row: pd.Series | None = None
        self.baseline_p: float = 0.0
        self.feasible_n: int = 0
        self.meta: dict[str, Any] = {}
        self.relaxed: bool = False
        self.last_error: str | None = None


MODEL = AppModel()


LOADING_OVERLAY = OptimizationLoadingOverlay()


class _EditDrawer:
    __slots__ = ("body_col", "dialog", "title")

    def __init__(self) -> None:
        self.dialog: ui.dialog | None = None
        self.title: ui.label | None = None
        self.body_col: ui.column | None = None


EDIT_DRAWER = _EditDrawer()


def _element_alive_for_current_client(el: Any) -> bool:
    """True if element exists, is not deleted, and belongs to the active browser session."""
    if el is None:
        return False
    try:
        if el.is_deleted:
            return False
    except Exception:
        return False
    try:
        return el.client.id == ui.context.client.id
    except RuntimeError:
        return False


def _edit_drawer_bound_to_current_client() -> bool:
    """Dialog + inner nodes must all be live; dialog alone can look OK while body_col is stale."""
    return all(
        _element_alive_for_current_client(x)
        for x in (EDIT_DRAWER.dialog, EDIT_DRAWER.title, EDIT_DRAWER.body_col)
    )


def _tear_down_edit_drawer() -> None:
    dlg = EDIT_DRAWER.dialog
    EDIT_DRAWER.dialog = None
    EDIT_DRAWER.title = None
    EDIT_DRAWER.body_col = None
    if dlg is None:
        return
    try:
        if not dlg.is_deleted:
            dlg.delete()
    except Exception:
        pass


EDIT_SECTION_LABELS: dict[str, str] = {
    "customer": "Customer profile",
    "vehicle": "Vehicle & financing inputs",
    "dealer_inv": "Dealer & inventory",
    "financing": "Optimization constraints",
    "market": "Market & competitor",
}


def ensure_edit_dialog() -> None:
    if _edit_drawer_bound_to_current_client():
        return
    _tear_down_edit_drawer()
    with ui.dialog() as dlg:
        EDIT_DRAWER.dialog = dlg
        with ui.card().classes("w-full").style(
            "min-width:440px;max-width:560px;padding:22px;background:#ffffff;"
            "border-radius:14px;border:1px solid #e5e7eb;"
        ):
            EDIT_DRAWER.title = ui.label("Edit").classes("text-lg font-bold").style(
                "color:#0f172a;letter-spacing:-0.02em;margin-bottom:4px;"
            )
            EDIT_DRAWER.body_col = ui.column().classes("w-full gap-1")
            with ui.row().classes("w-full justify-end gap-2 mt-6"):
                ui.button("Cancel", on_click=dlg.close).props("flat dense no-caps").style(
                    "color:#64748b;"
                )

                def apply_and_close() -> None:
                    """Persist edits to state and refresh the rail; optimization runs from sidebar only."""
                    dlg.close()
                    main_body.refresh()

                ui.button(
                    "Apply",
                    on_click=apply_and_close,
                ).props("unelevated dense no-caps").style(
                    "background:#166534;color:#ffffff;"
                )


def open_edit_section(section: str) -> None:
    """Open modal with a single wizard section for post-results edits."""
    MODEL.state["dashboard_edit_section"] = section
    for attempt in range(2):
        ensure_edit_dialog()
        assert EDIT_DRAWER.body_col is not None
        assert EDIT_DRAWER.title is not None
        assert EDIT_DRAWER.dialog is not None
        EDIT_DRAWER.title.text = EDIT_SECTION_LABELS.get(
            section, section.replace("_", " ").title()
        )
        try:
            EDIT_DRAWER.body_col.clear()
        except RuntimeError as e:
            if attempt == 0 and "deleted" in str(e).lower():
                _tear_down_edit_drawer()
                continue
            raise
        with EDIT_DRAWER.body_col:
            render_section_for_edit(MODEL.state, section, lambda: None)
        EDIT_DRAWER.dialog.open()
        return


def go_to_wizard() -> None:
    """Full session reset: demo defaults, wizard step 1, cleared results and UI chrome."""
    _tear_down_edit_drawer()
    LOADING_OVERLAY.close()
    fresh = session_defaults_from_demo()
    fresh["ui_mode"] = "wizard"
    fresh["wizard_step"] = 0
    fresh.setdefault("dashboard_edit_section", "customer")
    MODEL.state = fresh
    MODEL.demo_defaults = get_demo_defaults()
    MODEL.result_df = None
    MODEL.rec_row = None
    MODEL.aggressive_row = None
    MODEL.baseline_p = 0.0
    MODEL.feasible_n = 0
    MODEL.meta = {}
    MODEL.relaxed = False
    MODEL.last_error = None
    main_body.refresh()


def _load_artifacts() -> None:
    assert_artifacts_present()
    MODEL.pipeline = load_model()
    MODEL.schema = get_feature_schema()
    MODEL.sample_defaults = get_sample_defaults()


def _run_input_validation() -> tuple[list[str], list[str]]:
    business = build_business_inputs(MODEL.state)
    return validate_business_inputs(business, MODEL.state)


def _optimization_worker() -> dict[str, Any]:
    """
    Heavy work for thread pool (keeps UI event loop responsive).
    Reads latest inputs from MODEL.state.
    """
    _t0 = time.perf_counter()
    logger.info(
        "[OPT] optimization_worker: thread start (pipeline loaded=%s)",
        MODEL.pipeline is not None,
    )
    # sklearn 1.6 emits FutureWarnings on each predict (very noisy under large grids).
    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        module=r"sklearn\.utils\.deprecation",
    )
    business = build_business_inputs(MODEL.state)
    constraints = build_optimization_constraints(MODEL.state)
    cm = float(MODEL.state.get("sb_cost_multiplier") or 0.65)

    df, err, meta = run_constraint_based_offer_scenarios(
        business,
        constraints,
        MODEL.pipeline,
        MODEL.schema,
        MODEL.sample_defaults,
        cm,
        MODEL.state,
        MODEL.demo_defaults,
    )
    if err or df is None:
        logger.warning(
            "[OPT] optimization_worker: scenario search failed: %s (wall=%.3fs)",
            err,
            time.perf_counter() - _t0,
        )
        return {"ok": False, "error": err or "Optimization failed."}

    rec, feasible, relaxed = select_recommended_constrained(
        df, float(business["expected_unit_margin"]), constraints
    )
    aggressive = select_highest_conversion_scenario(df)

    term = int(rec["loan_term"])
    scen0 = apply_offer_scenario_levers(
        business,
        support_level=0.0,
        customer_cash=0.0,
        dealer_cash=0.0,
        loyalty_cash=0.0,
        conquest_cash=0.0,
        loan_term=term,
    )
    _rm, p0, p_err = _predict_scenario_row(
        scen0, MODEL.pipeline, MODEL.schema, MODEL.sample_defaults
    )
    if p_err or p0 is None:
        baseline_p = float(rec["conversion_probability"]) - float(
            rec["conversion_lift_vs_baseline"]
        )
    else:
        baseline_p = float(p0)

    logger.info(
        "[OPT] optimization_worker: finished rows=%d feasible=%d relaxed=%s wall=%.3fs",
        len(df),
        len(feasible),
        relaxed,
        time.perf_counter() - _t0,
    )
    return {
        "ok": True,
        "df": df,
        "rec": rec,
        "aggressive": aggressive,
        "baseline_p": baseline_p,
        "meta": meta or {},
        "relaxed": relaxed,
        "feasible_n": int(len(feasible)),
    }


async def _overlay_pulse(client: Client, message: str, progress: float) -> None:
    """Apply overlay milestone + yield so the browser can render before heavy steps."""
    with client:
        LOADING_OVERLAY.set_phase(message, progress)
    await asyncio.sleep(0.02)


async def run_analysis() -> None:
    """Run optimization from the UI: async so we can await paint yields before heavy work."""
    client = ui.context.client
    t0 = time.perf_counter()

    def _dt() -> float:
        return time.perf_counter() - t0

    MODEL.last_error = None
    logger.info("[OPT] click client_id=%s", getattr(client, "id", "?"))

    try:
        LOADING_OVERLAY.open()
        logger.info("[OPT] overlay opened Δt=%.3fs", _dt())

        await asyncio.sleep(0)
        await asyncio.sleep(0.1)
        logger.info("[OPT] post paint-yield Δt=%.3fs", _dt())

        try:
            if EDIT_DRAWER.dialog is not None and not EDIT_DRAWER.dialog.is_deleted:
                EDIT_DRAWER.dialog.close()
        except Exception:
            pass
        _tear_down_edit_drawer()

        await _run_optimization_pipeline(client, t0)
    except Exception:
        logger.exception("[OPT] run_analysis failed Δt=%.3fs", _dt())
        try:
            with client:
                LOADING_OVERLAY.close()
                MODEL.last_error = "Internal error while running optimization (see server logs)."
                ui.notify(MODEL.last_error, type="negative", multi_line=True)
                main_body.refresh()
        except Exception:
            logger.exception("[OPT] recovery UI failed")


async def _run_optimization_pipeline(client: Client, t0: float) -> None:
    """Validation, thread-pool optimization, then dashboard refresh — all under cooperative yields."""
    def _dt() -> float:
        return time.perf_counter() - t0

    with client:
        await asyncio.sleep(0)
        errs, warns = _run_input_validation()
        if errs:
            logger.info("[OPT] validation failed Δt=%.3fs", _dt())
            LOADING_OVERLAY.close()
            MODEL.last_error = "; ".join(errs)
            ui.notify(MODEL.last_error, type="negative", close_button="Dismiss")
            main_body.refresh()
            return
        for w in warns:
            ui.notify(w, type="warning")

        LOADING_OVERLAY.set_phase("Validated inputs — model pipeline ready.", 0.15)
        logger.info("[OPT] validation ok Δt=%.3fs", _dt())

    await _overlay_pulse(client, "Preparing scenario search…", 0.30)
    await _overlay_pulse(client, "Generating and scoring scenarios…", 0.45)

    try:
        await client.run_javascript(
            "try{document.activeElement && document.activeElement.blur && document.activeElement.blur();}catch(e){}",
            timeout=0.35,
        )
    except Exception:
        pass

    with client:
        LOADING_OVERLAY.set_phase("Scoring scenarios with the conversion model…", 0.55)
    logger.info("[OPT] io_bound dispatch Δt=%.3fs", _dt())
    _tw0 = time.perf_counter()
    try:
        out = await run.io_bound(_optimization_worker)
    except Exception as e:
        logger.exception("[OPT] io_bound raised Δt=%.3fs", _dt())
        with client:
            LOADING_OVERLAY.close()
            MODEL.last_error = f"{type(e).__name__}: {e}"
            ui.notify(MODEL.last_error, type="negative", multi_line=True)
            main_body.refresh()
        return
    logger.info(
        "[OPT] io_bound done wall=%.3fs Δt=%.3fs",
        time.perf_counter() - _tw0,
        _dt(),
    )

    with client:
        if out is None or not isinstance(out, dict):
            logger.warning("[OPT] unexpected worker return: %r", out)
            LOADING_OVERLAY.close()
            MODEL.last_error = "Optimization did not return a result (server may be stopping)."
            ui.notify(MODEL.last_error, type="negative")
            main_body.refresh()
            return
        if not out.get("ok"):
            logger.warning("[OPT] worker ok=False: %s", out.get("error"))
            LOADING_OVERLAY.close()
            MODEL.last_error = str(out.get("error") or "Optimization failed.")
            ui.notify(MODEL.last_error, type="negative")
            main_body.refresh()
            return

        LOADING_OVERLAY.set_phase("Selecting recommendation…", 0.80)
        MODEL.result_df = out["df"]
        MODEL.rec_row = out["rec"]
        MODEL.aggressive_row = out["aggressive"]
        MODEL.baseline_p = float(out["baseline_p"])
        MODEL.meta = out["meta"]
        MODEL.relaxed = bool(out["relaxed"])
        MODEL.feasible_n = int(out.get("feasible_n", 0))
        MODEL.state["ui_mode"] = "dashboard"

        LOADING_OVERLAY.set_phase("Preparing dashboard (charts and tables)…", 0.92)
        logger.info("[OPT] main_body.refresh start Δt=%.3fs", _dt())
        _tr0 = time.perf_counter()
        main_body.refresh()
        logger.info(
            "[OPT] main_body.refresh done wall=%.3fs Δt=%.3fs",
            time.perf_counter() - _tr0,
            _dt(),
        )
        LOADING_OVERLAY.set_phase("Complete.", 1.0)

    await asyncio.sleep(0.05)

    with client:
        LOADING_OVERLAY.close()
    logger.info("[OPT] finished Δt=%.3fs", _dt())


@ui.refreshable
def main_body() -> None:
    MODEL.state.setdefault("ui_mode", "wizard")
    page_max = (
        PAGE_RESULTS_MAX_W
        if MODEL.state.get("ui_mode") == "dashboard"
        else PAGE_MAX_W
    )
    with ui.column().classes("w-full items-stretch").style(
        f"max-width:{page_max};margin:0 auto;"
    ):
        if MODEL.last_error and MODEL.state["ui_mode"] == "wizard":
            ui.label(MODEL.last_error).classes("text-sm").style(
                "background:#fef2f2;color:#991b1b;padding:12px;border-radius:12px;"
            )

        if MODEL.state["ui_mode"] == "wizard":
            render_wizard(state=MODEL.state, redraw=main_body.refresh, run_analysis=run_analysis)
        else:
            if MODEL.result_df is None or MODEL.rec_row is None or MODEL.aggressive_row is None:
                MODEL.state["ui_mode"] = "wizard"
                ui.notify("Run analysis from the wizard first.", type="warning")
                render_wizard(
                    state=MODEL.state, redraw=main_body.refresh, run_analysis=run_analysis
                )
                return
            render_dashboard(
                state=MODEL.state,
                result_df=MODEL.result_df,
                rec=MODEL.rec_row,
                aggressive=MODEL.aggressive_row,
                baseline_p=MODEL.baseline_p,
                feasible_n=MODEL.feasible_n,
                meta=MODEL.meta,
                relaxed=MODEL.relaxed,
                pipeline=MODEL.pipeline,
                schema=MODEL.schema,
                sample_defaults=MODEL.sample_defaults,
                redraw=main_body.refresh,
                run_analysis=run_analysis,
                open_edit=open_edit_section,
                go_wizard=go_to_wizard,
            )


@ui.page("/")
def index() -> None:
    ui.add_head_html(f"<style>{theme_css()}</style>")
    try:
        _load_artifacts()
        logger.info(
            "[OPT] startup: model pipeline and schema loaded (pipeline is None=%s)",
            MODEL.pipeline is None,
        )
    except Exception as e:
        with ui.column().classes("w-full p-8"):
            ui.label(f"Startup failed: {e}").classes("text-lg").style("color:#991b1b;")
            ui.label(traceback.format_exc()).classes("text-xs font-mono whitespace-pre-wrap")
        return

    # Edit drawer is built lazily in open_edit_section so it always matches the active client.
    LOADING_OVERLAY.build()

    with ui.header(elevated=False).style(
        "background:#FFFFFF;border-bottom:1px solid #E5E7EB;"
    ):
        with ui.row().classes("w-full items-center justify-start app-header-inner"):
            with ui.column().classes("app-header-brand-col"):
                ui.label("Subvention Optimizer").classes("header-brand")
                ui.label(
                    "Auto finance subvention · conversion & incentive efficiency"
                ).classes("header-subtitle")

    with ui.column().classes("app-shell w-full"):
        main_body()


if __name__ in {"__main__", "__mp_main__"}:
    port = int(os.environ.get("PORT", 8080))
    # Railway / Docker: disable dev reloader; trust proxy so WS + HTTPS URLs resolve correctly.
    _railway = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    _uvicorn_extra: dict[str, Any] = {}
    if _railway:
        _uvicorn_extra["forwarded_allow_ips"] = "*"
        # Edge proxies (Railway, etc.) may idle-timeout long-lived connections. Uvicorn WS ping +
        # longer HTTP keep-alive reduces spurious disconnects; they do not speed up cold starts.
        _uvicorn_extra["timeout_keep_alive"] = int(
            os.environ.get("UVICORN_TIMEOUT_KEEP_ALIVE", "120")
        )
        _uvicorn_extra["ws_ping_interval"] = float(
            os.environ.get("UVICORN_WS_PING_INTERVAL", "20")
        )
        _uvicorn_extra["ws_ping_timeout"] = float(
            os.environ.get("UVICORN_WS_PING_TIMEOUT", "90")
        )
    ui.run(
        host="0.0.0.0",
        port=port,
        title="Auto Finance Subvention Optimizer",
        favicon="🚗",
        reload=not _railway,
        # Slightly more tolerant than default 3s when the tab is backgrounded or the link is lossy.
        reconnect_timeout=float(os.environ.get("NICEGUI_RECONNECT_TIMEOUT", "12" if _railway else "3")),
        **_uvicorn_extra,
    )
