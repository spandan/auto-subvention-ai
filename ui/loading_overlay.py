"""Full-page optimization loading overlay (no bottom toasts during run)."""

from __future__ import annotations

import random
from typing import Any, Optional

from nicegui import ui

# Rotating reassurance copy (secondary line while work runs).
LOADING_ROTATING_TIPS: tuple[str, ...] = (
    "Mapping your customer, vehicle, and market inputs into the scenario engine.",
    "Enumerating rate-support and cash levers that respect your caps and budget.",
    "Scoring each package with the saved conversion model—same math as your last run.",
    "Walking the efficient frontier: best lift per dollar of support, not just max spend.",
    "Holding competitor APR, payment, and cashback fixed so comparisons stay apples-to-apples.",
    "Applying your support-cost multiplier so economics match how your desk funds programs.",
    "Respecting allowed loan terms and grid steps from your optimization constraints.",
    "Feasibility filters trim impossible bundles before we rank what’s left.",
    "Ranking by predicted close rate and incremental efficiency—then picking the recommended row.",
    "Large grids can take several seconds; the dashboard will appear as soon as scoring finishes.",
)

TIP_ROTATION_SECONDS = 2.6


def _element_has_live_client(el: Any) -> bool:
    """True if element is bound to an active browser session (not reload / disconnect)."""
    if el is None:
        return False
    try:
        deleted = el.is_deleted
    except AttributeError:
        return False
    if deleted:
        return False
    try:
        _ = el.client
    except RuntimeError:
        return False
    return True


class OptimizationLoadingOverlay:
    """Persistent centered card over blurred backdrop."""

    __slots__ = (
        "_built",
        "_dialog",
        "_tip_el",
        "_tip_index",
        "_tip_timer",
        "_progress",
        "_status_el",
    )

    def __init__(self) -> None:
        self._dialog: Optional[ui.dialog] = None
        self._tip_el: Optional[ui.label] = None
        self._tip_index: int = 0
        self._tip_timer: Any = None
        self._progress: Optional[ui.linear_progress] = None
        self._status_el: Optional[ui.label] = None
        self._built = False

    def _stop_tip_rotation(self) -> None:
        t = self._tip_timer
        self._tip_timer = None
        if t is None:
            return
        try:
            t.cancel()
        except AttributeError:
            try:
                t.deactivate()
            except Exception:
                pass
        except Exception:
            pass

    def _advance_tip(self) -> None:
        if self._tip_el is None or not _element_has_live_client(self._tip_el):
            self._stop_tip_rotation()
            return
        self._tip_index = (self._tip_index + 1) % len(LOADING_ROTATING_TIPS)
        try:
            self._tip_el.text = LOADING_ROTATING_TIPS[self._tip_index]
        except RuntimeError:
            self._stop_tip_rotation()

    def _tear_down(self) -> None:
        """Drop references and delete dialog tree (handles stale session after reload)."""
        self._stop_tip_rotation()
        dlg = self._dialog
        self._dialog = None
        self._tip_el = None
        self._progress = None
        self._status_el = None
        self._built = False
        if dlg is None:
            return
        try:
            if not dlg.is_deleted:
                dlg.delete()
        except Exception:
            pass

    def _bindings_ok(self) -> bool:
        return bool(
            self._built
            and _element_has_live_client(self._dialog)
            and _element_has_live_client(self._tip_el)
            and _element_has_live_client(self._progress)
            and _element_has_live_client(self._status_el)
        )

    def build(self) -> None:
        """Create under the current NiceGUI client, or recreate if prior client was disposed."""
        if self._bindings_ok():
            return
        self._tear_down()
        with ui.dialog() as dlg:
            self._dialog = dlg
            dlg.props("persistent maximized")
            with ui.column().classes(
                "w-full items-center justify-center"
            ).style(
                "min-height:100vh;width:100%;"
                "background:rgba(248,250,252,0.94);backdrop-filter:blur(6px);"
            ):
                with ui.card().classes("optimization-loading-card shadow-lg"):
                    ui.label("Running offer optimization").classes("ol-heading")
                    self._status_el = ui.label("Starting optimization…").classes("ol-status-line")
                    self._tip_index = random.randrange(len(LOADING_ROTATING_TIPS))
                    self._tip_el = ui.label(LOADING_ROTATING_TIPS[self._tip_index]).classes(
                        "ol-rotating-tip"
                    )
                    self._progress = ui.linear_progress(
                        value=0.05, show_value=False, color="#059669"
                    )
                    self._progress.classes("rounded-full ol-progress-bar")

        self._built = True

    def set_phase(self, message: str, progress: float) -> None:
        """Update milestone text and bar (0..1). Call inside ``with client:`` when in async context."""
        if self._status_el is None or self._progress is None:
            return
        if not _element_has_live_client(self._status_el):
            return
        try:
            self._status_el.text = message
            self._progress.value = max(0.0, min(1.0, float(progress)))
        except RuntimeError:
            self._tear_down()

    def open(self) -> None:
        self.build()
        if self._dialog is None:
            return
        try:
            self._dialog.open()
            self._stop_tip_rotation()
            self.set_phase("Starting optimization…", 0.05)
            self._tip_index = random.randrange(len(LOADING_ROTATING_TIPS))
            if self._tip_el is not None and _element_has_live_client(self._tip_el):
                self._tip_el.text = LOADING_ROTATING_TIPS[self._tip_index]
            self._tip_timer = ui.timer(TIP_ROTATION_SECONDS, self._advance_tip)
        except RuntimeError:
            self._tear_down()
            self.build()
            if self._dialog is not None:
                self._dialog.open()
                self._stop_tip_rotation()
                self.set_phase("Starting optimization…", 0.05)
                self._tip_index = random.randrange(len(LOADING_ROTATING_TIPS))
                if self._tip_el is not None and _element_has_live_client(self._tip_el):
                    self._tip_el.text = LOADING_ROTATING_TIPS[self._tip_index]
                self._tip_timer = ui.timer(TIP_ROTATION_SECONDS, self._advance_tip)

    def close(self) -> None:
        """Always tear down after close so the next run gets a fresh dialog (avoids stale closed QDialog blocking open())."""
        dlg = self._dialog
        if dlg is None:
            return
        try:
            if _element_has_live_client(dlg) and not dlg.is_deleted:
                dlg.close()
        except RuntimeError:
            pass
        finally:
            self._tear_down()
