# Auto Finance Subvention Optimization Simulator — Architecture

This document describes how the NiceGUI application collects inputs, builds model-ready features, runs predictions, and executes the dealer support scenario optimization.

## Overview

The app is a **conversion simulator**: users enter a structured automotive finance quote (customer, vehicle, dealer/inventory, financing, competitor, market). After **Run optimization**, the pipeline aligns inputs to the trained model schema, predicts **conversion probability** for the baseline offer, then **searches** feasible dealer-rate and cash lever combinations and ranks outcomes for the dashboard.

**Primary artifacts**

| File | Role |
|------|------|
| `model_pipeline.pkl` | Serialized sklearn / LightGBM classifier pipeline (`joblib.load`). |
| `feature_schema.json` | Canonical `required_columns` for alignment before `predict_proba`. |
| `sample_input.json` | Optional defaults for alignment gaps during development. |
| `model_metadata.json` | Training metadata (documentation / debug UI). |

Orchestration and UI wiring live in **`app.py`**. Feature engineering, model alignment, validation, and the scenario optimizer live in **`services/`** (`feature_engineering.py`, `model_service.py`, `optimizer.py`).

---

## End-to-end flow

```mermaid
flowchart LR
  subgraph inputs["Business inputs (wizard / edit drawer)"]
    S1[Customer]
    S2[Vehicle]
    S3[Dealer / inventory]
    S4[Financing / offer]
    S5[Competitor]
    S6[Market / timing]
  end

  subgraph gate["Gate"]
    BTN[Run optimization]
  end

  subgraph prep["Feature prep"]
    BF[build_business_inputs]
    CF[calculate_model_features]
    AL[align_to_schema]
    SCH[(feature_schema.json)]
  end

  subgraph model["Model"]
    PKL[(model_pipeline.pkl)]
    PP[predict_proba → P(convert)]
  end

  subgraph sim["Optimization"]
    OPT[run_constraint_based_offer_scenarios]
    SEL[Select recommended / aggressive rows]
  end

  subgraph ui["UI"]
    W[Wizard steps]
    D[Results dashboard]
  end

  S1 & S2 & S3 & S4 & S5 & S6 --> BF
  BF --> BTN
  BTN --> CF
  CF --> AL
  SCH --> AL
  AL --> PKL
  PKL --> PP
  PP --> OPT
  OPT --> SEL
  SEL --> D
  W --> BF
```

---

## Inputs collected

Wizard sections map into a single **`build_business_inputs()`** dict (in-memory **`MODEL.state`**, keyed with **`sb_*`** fields used by **`ui/`** widgets). Business-facing labels avoid internal ML naming on primary surfaces.

| Section | Examples |
|---------|----------|
| **1 · Customer** | Credit score, monthly income, DTI drivers, behavioral sliders (price sensitivity, urgency, brand, etc.), segment flags. |
| **2 · Vehicle** | Make, model, year, trim, fuel, pricing, residual / support hints. |
| **3 · Dealer & inventory** | Dealer size, volume, margins, inventory age and pressure signals. |
| **4 · Financing & offer** | Loan amount, down payment, term, standard vs dealer APR, monthly payment, cash levers, dealer rate support (baseline scenario). |
| **5 · Competitor** | Competing APR, payment, cashback, aggressiveness sliders. |
| **6 · Market & timing** | Indices, timing, geography, desk settings; calibration such as **support cost multiplier**. |

Optimization runs **only when** the user triggers **Run optimization** on the wizard or **Re-run optimization** from the results sidebar after edits.

---

## Feature engineering

**`calculate_model_features(business)`** (in **`services/feature_engineering.py`**) produces a row aligned with **`feature_schema.json → required_columns`**, including bands/tiers, payment and LTV ratios, competitive gaps, interaction terms, and subvention-linked APR constructs expected by the pipeline.

**Alignment** uses **`services/model_service.py`** patterns (schema order, sample defaults).

---

## What is predicted

| Output | Meaning |
|--------|---------|
| **Baseline conversion probability** | `predict_proba` for the aligned row at the user’s baseline support and financing. |
| **Per-scenario conversion probability** | Same model across evaluated feasible scenarios. |

The **recommended** row follows constrained selection rules (efficiency, lift, budget caps) implemented in **`services/optimizer.py`** — not necessarily maximum raw conversion.

---

## Scenario optimization

The constraint-based search (**`run_constraint_based_offer_scenarios`** in **`services/optimizer.py`**) builds a grid of dealer support and cash combinations subject to business rules, enriches each row with cost and margin estimates, and returns a `DataFrame` consumed by the dashboard charts and tables.

---

## UI surface

| Mode | Purpose |
|------|---------|
| **Wizard** | Sequential capture of all sections; **Run optimization** submits. |
| **Results dashboard** | Hero summary, KPIs, comparison panels, efficient-frontier style charts, top scenarios table, Excel export, model debug; **Adjust inputs** opens per-section edit dialogs; **Apply** saves state; **Re-run optimization** refreshes the search. |

A loading overlay runs during **artifact load** (startup) and during **optimization** after submit.

---

## Dependencies

See **`requirements.txt`** (NiceGUI, pandas, numpy, scikit-learn, LightGBM, joblib, plotly, openpyxl). The pinned sklearn range should stay compatible with the environment used to pickle **`model_pipeline.pkl`**.
