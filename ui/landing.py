"""Landing page: choose Dealer Offer Optimization vs OEM Incentive Planning."""

from __future__ import annotations

from typing import Callable

from nicegui import ui


def render_landing(
    *,
    start_dealer: Callable[[], None],
    start_oem: Callable[[], None],
) -> None:
    with ui.column().classes("w-full items-center landing-shell"):
        with ui.column().classes("landing-hero w-full items-center"):
            ui.label("Auto Finance Subvention Optimization Platform").classes(
                "landing-title w-full text-center"
            )
            ui.label(
                "Optimize incentive strategies for dealers and OEMs using customer behavior, "
                "inventory pressure, market conditions, and support-cost efficiency."
            ).classes("landing-subtitle w-full text-center")
            ui.element("div").classes("landing-hero-rule")

        with ui.element("div").classes("landing-tile-grid w-full"):
            with ui.element("div").classes("mode-tile mode-tile--dealer"):
                ui.icon("storefront").classes("mode-tile-icon")
                ui.label("Dealer Offer Optimization").classes("mode-tile-title")
                ui.label(
                    "Optimize financing and incentive packages for an individual customer and "
                    "vehicle based on affordability, inventory conditions, and competitor offers."
                ).classes("mode-tile-desc")
                ui.label("Use cases").classes("mode-tile-use-h")
                ui.html(
                    "<ul class='mode-tile-use'>"
                    "<li>Desk managers</li>"
                    "<li>Finance managers</li>"
                    "<li>Real-time customer negotiation</li>"
                    "<li>Offer structuring</li>"
                    "</ul>"
                )
                ui.button(
                    "Start Dealer Optimization",
                    on_click=start_dealer,
                ).props("unelevated dense no-caps").classes("mode-tile-cta btn-cta btn-cta--dealer w-full")

            with ui.element("div").classes("mode-tile mode-tile--oem"):
                ui.icon("precision_manufacturing").classes("mode-tile-icon")
                ui.label("OEM Incentive Planning").classes("mode-tile-title")
                ui.label(
                    "Simulate regional and dealership incentive strategies using market "
                    "conditions, inventory pressure, competitor positioning, and standardized "
                    "buyer assumptions."
                ).classes("mode-tile-desc")
                ui.label("Use cases").classes("mode-tile-use-h")
                ui.html(
                    "<ul class='mode-tile-use'>"
                    "<li>OEM pricing teams</li>"
                    "<li>Regional incentive planning</li>"
                    "<li>Market strategy simulation</li>"
                    "<li>Campaign design</li>"
                    "</ul>"
                )
                ui.button(
                    "Start OEM Planning",
                    on_click=start_oem,
                ).props("unelevated dense no-caps").classes("mode-tile-cta btn-cta btn-cta--oem w-full")
