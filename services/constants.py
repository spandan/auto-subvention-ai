"""Shared paths and domain constants for the optimizer UI and services."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAX_FULL_ENUMERATION = 25_000
LOAN_TERMS = [36, 48, 60, 72, 84]

_DEMO_DEFAULTS_VERSION = 5

CUSTOMER_SEGMENTS: list[str] = [
    "Value Shopper",
    "Payment Sensitive",
    "Loyalist",
    "Conquest Buyer",
    "Premium Buyer",
    "Utility Buyer",
    "EV Interested",
]

CUSTOMER_SEGMENT_OPTION_LABELS: dict[str, str] = {
    "Value Shopper": "Value Shopper — chases rebates, discounts, and lowest total out-the-door.",
    "Payment Sensitive": "Payment Sensitive — buys on monthly payment and wallet comfort first.",
    "Loyalist": "Loyalist — loves the brand; repeat buyer; hard to lure away.",
    "Conquest Buyer": "Conquest Buyer — cross-shopping; winnable from a rival with the right offer.",
    "Premium Buyer": "Premium Buyer — pays for prestige, features, and experience over bare price.",
    "Utility Buyer": "Utility Buyer — mission-first: space, towing, durability, or work use.",
    "EV Interested": "EV Interested — prefers electric or plug-in when range and charging work.",
}

MODEL_BY_MAKE: dict[str, list[str]] = {
    "Toyota": ["Camry", "Corolla", "RAV4", "Highlander", "Tacoma"],
    "Honda": ["Civic", "Accord", "CR-V", "Pilot"],
    "Ford": ["F-150", "Escape", "Explorer", "Mustang"],
    "Chevrolet": ["Silverado", "Equinox", "Tahoe", "Malibu"],
    "Hyundai": ["Elantra", "Sonata", "Tucson", "Palisade"],
    "Kia": ["K5", "Sportage", "Telluride", "Sorento"],
    "Nissan": ["Altima", "Rogue", "Pathfinder", "Frontier"],
    "Jeep": ["Wrangler", "Grand Cherokee", "Compass"],
    "BMW": ["330i", "X3", "X5", "i4"],
    "Mercedes": ["C300", "GLE350", "E350", "EQE"],
    "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
}
MAKES: list[str] = list(MODEL_BY_MAKE.keys())

TRIM_LEVELS: list[str] = [
    "Base",
    "Sport",
    "Premium",
    "Limited",
    "Touring",
    "Platinum",
]

BODY_STYLES_UI: list[str] = [
    "Sedan",
    "SUV",
    "Truck",
    "Coupe",
    "Hatchback",
    "Crossover",
]

FUEL_TYPES_UI: list[str] = [
    "Gasoline",
    "Hybrid",
    "Plug-in Hybrid",
    "Diesel",
    "EV",
]

VEHICLE_SEGMENTS: list[str] = [
    "Economy",
    "Compact SUV",
    "Midsize SUV",
    "Luxury",
    "Truck",
    "Sedan",
    "EV",
]

DEALER_SIZE_TIERS: list[str] = ["Small", "Medium", "Large", "Mega"]

PRIMARY_COMPETITORS: list[str] = [
    "Toyota",
    "Honda",
    "Ford",
    "Chevrolet",
    "Hyundai",
    "Kia",
    "Nissan",
    "Tesla",
    "BMW",
]

SALES_TYPES_UI: list[str] = ["Retail", "Lease", "Finance", "Cash"]

REGIONS: list[str] = [
    "Northeast",
    "Southeast",
    "Midwest",
    "Southwest",
    "West",
]

STATES: list[str] = [
    "TX",
    "CA",
    "FL",
    "NY",
    "NJ",
    "IL",
    "AZ",
    "WA",
    "GA",
    "NC",
]

MONTH_OPTIONS: list[int] = list(range(1, 13))

MONTH_LABELS: list[str] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

DOW_LABELS: list[str] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

YES_NO: tuple[str, ...] = ("Yes", "No")

SIDEBAR_SECTION_ORDER: tuple[str, ...] = (
    "customer",
    "vehicle",
    "dealer_inv",
    "financing",
    "competitor",
    "macro",
)

WIZARD_STEP_TITLE: dict[str, str] = {
    "customer": "Customer Profile",
    "vehicle": "Vehicle & Product",
    "dealer_inv": "Dealer & Inventory",
    "financing": "Optimization Constraints",
    "competitor": "Competitor & Market",
    "macro": "Financial Market Conditions",
}
