"""Full-page optimization loading overlay (no bottom toasts during run)."""

from __future__ import annotations

from typing import Any, Optional

from nicegui import ui

STEP_LABELS: tuple[str, ...] = (
    "1. Loading model pipeline",
    "2. Preparing customer and market features",
    "3. Generating offer scenarios",
    "4. Scoring scenarios",
    "5. Selecting recommended package",
)


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

    __slots__ = ("_built", "_dialog", "_progress", "_step_el")

    def __init__(self) -> None:
        self._dialog: Optional[ui.dialog] = None
        self._progress: Optional[ui.linear_progress] = None
        self._step_el: Optional[ui.label] = None
        self._built = False

    def _tear_down(self) -> None:
        """Drop references and delete dialog tree (handles stale session after reload)."""
        dlg = self._dialog
        self._dialog = None
        self._progress = None
        self._step_el = None
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
            and _element_has_live_client(self._progress)
            and _element_has_live_client(self._step_el)
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
                    ui.label(
                        "Scoring incentive packages and selecting the most efficient offer."
                    ).classes("ol-subheading")
                    self._step_el = ui.label(STEP_LABELS[0]).classes("ol-step-text")
                    self._progress = ui.linear_progress(
                        value=0.02, show_value=False, color="#059669"
                    )
                    self._progress.classes("rounded-full mt-6")

        self._built = True

    def open(self) -> None:
        self.build()
        if self._dialog is None:
            return
        try:
            self.reset()
            self._dialog.open()
        except RuntimeError:
            self._tear_down()
            self.build()
            if self._dialog is not None:
                self.reset()
                self._dialog.open()

    def close(self) -> None:
        if self._dialog is None or not _element_has_live_client(self._dialog):
            self._tear_down()
            return
        try:
            self._dialog.close()
        except RuntimeError:
            self._tear_down()

    def reset(self) -> None:
        self.set_phase(0, 0.02)

    def set_phase(self, index: int, progress: float) -> None:
        """Index 0..4 for step labels; progress 0..1."""
        if self._step_el is None or self._progress is None:
            return
        if not _element_has_live_client(self._step_el):
            return
        try:
            idx = max(0, min(len(STEP_LABELS) - 1, int(index)))
            self._step_el.text = STEP_LABELS[idx]
            self._progress.value = max(0.0, min(1.0, float(progress)))
        except RuntimeError:
            self._tear_down()
