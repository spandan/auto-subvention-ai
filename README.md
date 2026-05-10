---
title: Auto Finance Offer Conversion Simulator
emoji: 🚗
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: "1.41.0"
app_file: app.py
pinned: false
---

# Auto Finance Offer Conversion Simulator

Streamlit app that loads a trained **scikit-learn** pipeline (`model_pipeline.pkl`) and estimates **customer conversion probability** from **business-friendly** sidebar inputs (engineered ML features are computed in code). A **Subvention Simulator** sweeps subvention levels with APR/payment adjustments.

**Phase 2** adds **profit & economics**: configurable gross margin, F&I reserve, inventory holding cost, optional cashback-as-cost, a calibrated **subvention program cost** estimate, **expected profit** (`P(convert) × net contribution if closed`), and a second optimization hint (**best expected profit** vs **best conversion**).

The app **does not train or retrain** models; conversion scores come only from `predict_proba()` on your saved pipeline. Phase 2 dollar math is **illustrative**—tune sidebar sliders to match your desk / OEM program.

## Expected artifacts (project root)

Place these files next to `app.py`:

| File | Purpose |
|------|---------|
| `model_pipeline.pkl` | Trained pipeline loaded with `joblib.load()`; must implement `predict_proba`. |
| `feature_schema.json` | JSON object with a `required_columns` array (ordered feature names for the model input row). Optional: `categorical_values` for selectbox options (see below). |
| `sample_input.json` | Single JSON object: defaults for widgets and **fallback values** for any required columns not produced by the UI. |
| `model_metadata.json` | Optional; shown in the **Model Info** tab. |

### `feature_schema.json` shape

Minimal:

```json
{
  "required_columns": ["fico_score", "our_apr", "..."]
}
```

Optional `categorical_values` for sidebar selectboxes (otherwise categories are inferred from `sample_input.json`):

```json
{
  "required_columns": ["income_band", "vehicle_segment", "..."],
  "categorical_values": {
    "income_band": ["<40k", "40k-75k", "75k+"],
    "vehicle_segment": ["Compact", "Midsize", "SUV", "Truck"]
  }
}
```

The app **always recomputes** these derived columns from the sidebar row (and again in the subvention simulator after APR changes). Include them in `required_columns` whenever your pipeline was trained with them:

- `apr_gap_bps` = `(our_apr - competitor_apr) * 100`
- `payment_gap` = `our_monthly_payment - competitor_monthly_payment`
- `cashback_gap` = `our_cashback - competitor_cashback`
- `sensitivity_x_apr_gap` = `price_sensitivity_score * apr_gap_bps`
- `loyalty_x_payment_gap` = `brand_loyalty_score * payment_gap`
- `urgency_x_pricing_disadvantage` = `customer_urgency_score * max(apr_gap_bps, 0)`

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the URL shown in the terminal (typically `http://localhost:8501`).

## Deploy on Hugging Face Spaces

1. Create a **new Space** at [huggingface.co/new-space](https://huggingface.co/new-space), choose **Streamlit** as the SDK.
2. Push this repository (or upload files) so the Space root contains `app.py`, `requirements.txt`, and `README.md` with the YAML frontmatter above (Hugging Face uses it for title, SDK, and `app_file`).
3. Upload your artifacts (`model_pipeline.pkl`, `feature_schema.json`, `sample_input.json`, `model_metadata.json`) to the Space repository root **or** use Space **Secrets / files** if you prefer not to commit large binaries—either way, the files must be present beside `app.py` at runtime.
4. Wait for the build to finish; open the Space URL.

**Note:** The Space build installs dependencies from `requirements.txt`. `lightgbm` is listed because many pipelines persist a LightGBM step inside the pickled sklearn pipeline.

## Troubleshooting

### `Can't get attribute '_RemainderColsList'` (model load fails)

Pickled **pipelines that include `ColumnTransformer`** are tied to the **scikit-learn version** used when the file was saved. Objects saved with **1.6.x** often fail to load on **1.7+** because internal helpers such as `_RemainderColsList` were removed ([upstream discussion](https://github.com/scikit-learn/scikit-learn/issues/32090)).

**Fix:** Run the app with **the same sklearn major.minor as training**, or at least **`scikit-learn<1.7`** if the model was produced on 1.6.x.

- **Conda (recommended):** `conda install "scikit-learn>=1.6,<1.7"` (or pin the exact version from your training env).
- **venv + pip:** use `requirements.txt` in this repo (sklearn is pinned to `>=1.6,<1.7`).
- **Long-term:** re-export the pipeline after fitting with your target sklearn version, or record `sklearn.__version__` in `model_metadata.json` and match it in production.

## App behavior (summary)

### Phase 1 (conversion ML)

- **Single Scenario:** business inputs → engineered features → DataFrame aligned to `feature_schema.required_columns` → conversion probability, likelihood band, competitive position, optional **Model Feature Preview**.
- **Subvention Simulator:** sweeps candidate subvention (bps), adjusts our APR and monthly payment per app rules, recomputes features, plots **P(convert)** vs subvention, table of scenarios, highlights **best conversion probability**.
- **Model Info:** raw JSON for `model_metadata.json` and `feature_schema.json`.

### Phase 2 (profit & economics)

Sidebar section **Profit & economics (Phase 2)** (does not feed the ML model):

| Control | Role |
|--------|------|
| Vehicle front-end gross ($) | Contribution if the deal closes |
| F&I / backend contribution ($) | Additional reserve per closed deal |
| Inventory holding cost ($ / day) | × days in inventory |
| Treat cashback as funded cost | Subtract **Our Cashback** from net when checked |
| Subvention cost calibration (×) | Scales the proxy subvention cost formula |

**Single Scenario:** metrics for estimated subvention cost, holding cost, net if closed, and **expected profit**.

**Subvention Simulator:** extra columns (`subvention_cost_usd`, `holding_cost_usd`, `net_if_closed_usd`, `expected_profit_usd`), second chart **expected profit vs subvention**, and callout for **best expected profit** (may differ from best conversion).
