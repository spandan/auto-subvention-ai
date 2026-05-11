# UI notes (NiceGUI)

The simulator ships as a **NiceGUI** single-process app:

- **`app.py`** — entry point, shared `MODEL` state, `run_analysis()`, edit dialog, refreshable main body.
- **`ui/theme.py`** — global CSS tokens and layout classes.
- **`ui/wizard.py`** — multi-step input flow before the first optimization run.
- **`ui/dashboard.py`** — post-run results: sidebar snapshot / edits, charts (Plotly), tables, export.

Business and model logic live under **`services/`** (`feature_engineering`, `model_service`, `optimizer`, `constants`) and should stay independent of the UI framework.

A former Streamlit implementation was removed from this repository; deployment uses **`python app.py`** or the **`Dockerfile`** (see root **`README.md`**).
