---
title: Auto Finance Offer Conversion Simulator
emoji: 🚗
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Auto Finance Offer Conversion Simulator

NiceGUI app that loads a trained **scikit-learn** pipeline (`model_pipeline.pkl`) and estimates **customer conversion probability** from guided inputs. A **subvention scenario search** explores dealer rate support and cash levers under constraints, then surfaces a recommended efficient offer, charts, and scenario tables.

The app **does not train or retrain** models; scores come from `predict_proba()` on your saved pipeline. Dollar economics (support cost, margin, expected value) are **illustrative**—tune inputs to match your desk / OEM program.

## Expected artifacts (project root)

| File | Purpose |
|------|---------|
| `model_pipeline.pkl` | Trained pipeline loaded with `joblib.load()`; must implement `predict_proba`. |
| `feature_schema.json` | JSON object with a `required_columns` array (ordered feature names for the model input row). Optional: `categorical_values` for select options (see below). |
| `sample_input.json` | Single JSON object: defaults for widgets and **fallback values** for any required columns not produced by the UI. |
| `model_metadata.json` | Optional; shown in the **Model details** section on the results dashboard. |

### `feature_schema.json` shape

Minimal:

```json
{
  "required_columns": ["fico_score", "our_apr", "..."]
}
```

Optional `categorical_values` (otherwise categories are inferred from `sample_input.json`):

```json
{
  "required_columns": ["income_band", "vehicle_segment", "..."],
  "categorical_values": {
    "income_band": ["<40k", "40k-75k", "75k+"],
    "vehicle_segment": ["Compact", "Midsize", "SUV", "Truck"]
  }
}
```

The pipeline row is built from **`build_business_inputs`** + feature engineering in `services/feature_engineering.py` and aligned to `required_columns` before prediction.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:8080` (or the host/port shown in the terminal). The process listens on **`0.0.0.0`** and uses the **`PORT`** environment variable when set (e.g. on Railway or Hugging Face).

## Deploy (Docker / PaaS)

The included **`Dockerfile`** runs `python app.py`. Set **`PORT`** if your platform requires a specific listen port.

## Deploy on Railway

1. **New project → Deploy from GitHub** (or connect this repo another way).
2. Railway picks **`railway.toml`**: **`DOCKERFILE`** build and **`deploy`** settings (single replica, `/` health check, generous timeout for pickle load + NiceGUI startup).
3. **`PORT`** is set automatically — **`app.py`** already binds **`0.0.0.0`** to that port.
4. **Artifacts**: **`model_pipeline.pkl`** and **`feature_schema.json`** are required (startup **`assert_artifacts_present()`**). Add **`sample_input.json`** and **`model_metadata.json`** beside **`app.py`** when you use them — often via committing them or syncing from a Railway **volume**/CI step before start.
5. Leave **one replica** (`numReplicas = 1` in **`railway.toml`**): the app keeps state in-memory and uses WebSockets; scaling out needs sticky sessions / re-architecture.
6. **Resources**: allocate enough **RAM** for LightGBM + pandas (e.g. **≥ 1 GB**) so the bundle can load cleanly.

Generate a **public domain** under the Railway service (**Settings → Networking → Generate Domain**) — no reverse-proxy flags are required for NiceGUI behind Railway’s HTTPS.

### Run Optimization “does nothing” on Railway

- **Dependencies:** `requirements.txt` lists direct deps; `pip` installs transitive packages (e.g. **uvicorn**, **starlette**, **scipy** with scikit-learn). If a deploy log shows `ModuleNotFoundError`, pin that package explicitly.
- **Client context:** **`run_analysis`** is **`async`** and is **awaited** from the Run / Re-run buttons. Heavy scoring runs in **`run.io_bound`** (thread pool). UI updates (**`LOADING_OVERLAY`**, **`main_body.refresh()`**) run inside **`with client:`** on the same asyncio task so the browser can paint milestones before and after the worker.
- **Production server flags:** When **`RAILWAY_ENVIRONMENT`** is set, **`app.py`** sets **`reload=False`** and **`forwarded_allow_ips='*'`** for uvicorn so WebSockets and client updates behave behind Railway’s proxy.
- **Validation:** If **no loan term** is selected under optimization constraints, **`validate_business_inputs`** fails immediately after the overlay opens (overlay then closes); check for a red toast or the error banner above the wizard.
- **Logs:** In Railway → **Deployments → View logs**, look for tracebacks during **`run_analysis`** / **`_optimization_worker`** (OOM, pickle errors, etc.).

## Deploy on Hugging Face Spaces

1. Create a **Docker** Space and push this repository (or use the Space UI to add files).
2. Ensure artifacts (`model_pipeline.pkl`, `feature_schema.json`, `sample_input.json`, etc.) exist in the repo or are provided at runtime.
3. Builds install from **`requirements.txt`**. `lightgbm` supports many pickled sklearn pipelines that include a LightGBM step.

## Project layout

| Path | Role |
|------|------|
| `app.py` | NiceGUI entry: session state, `run_analysis`, edit drawer, `main_body` refresh. |
| `ui/` | Theme, wizard, dashboard, charts, loading overlay. |
| `services/` | Feature engineering, model I/O, optimization / scenario sweep. |

See **`docs/architecture.md`** for data flow and scenario logic.

## Troubleshooting

### `Can't get attribute '_RemainderColsList'` (model load fails)

Pickled **pipelines that include `ColumnTransformer`** are tied to the **scikit-learn version** used when the file was saved. Objects saved with **1.6.x** often fail to load on **1.7+** because internal helpers such as `_RemainderColsList` were removed ([upstream discussion](https://github.com/scikit-learn/scikit-learn/issues/32090)).

**Fix:** Run the app with **the same sklearn major.minor as training**, or at least **`scikit-learn<1.7`** if the model was produced on 1.6.x.

- **Conda (recommended):** `conda install "scikit-learn>=1.6,<1.7"` (or pin the exact version from your training env).
- **venv + pip:** match **`requirements.txt`** (sklearn is pinned for pickle safety).
- **Long-term:** re-export the pipeline after fitting with your target sklearn version, or record `sklearn.__version__` in `model_metadata.json` and match it in production.
