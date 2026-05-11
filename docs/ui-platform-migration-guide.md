# UI setup & migration guide (Streamlit → another platform)

This document describes **how the Auto Finance Subvention Optimization Simulator UI is structured today** in Streamlit, so you can reproduce behavior, layout contracts, and styling when moving to another frontend stack. It intentionally separates **UI mechanics** from **business/model logic** (which remains in Python and can stay server-side or move behind an API).

---

## 1. Big picture

| Aspect | Current implementation |
|--------|-------------------------|
| **Framework** | Streamlit (single Python process, script rerun on interaction) |
| **Entry point** | `main()` in `app.py` |
| **Layout** | `layout="wide"`, sidebar **expanded** by default |
| **Two UX modes** | **Pre-submit wizard** (full-page, no sidebar inputs) vs **Post-submit analysis** (sidebar parameter editor + main tabs) |
| **State** | `st.session_state` holds all form values (`sb_*` keys) and UI flags |
| **Styling** | Global CSS injected via `st.markdown(..., unsafe_allow_html=True)` — no separate CSS bundle |

---

## 2. Application modes (routing)

`main()` branches on **`st.session_state.analysis_submitted`**:

### A. Wizard mode (`analysis_submitted == False`)

1. Injects fonts + **`EXEC_THEME_CSS()`** + **`EXEC_WIZARD_DEMO_UI_CSS()`**.
2. Calls **`render_full_page_wizard()`** then **`st.stop()`** — nothing after runs on that visit.

**Purpose:** Guided multi-step form for initial data capture (same logical sections as the sidebar later).

### B. Analysis mode (`analysis_submitted == True`)

1. Injects fonts + **`EXEC_THEME_CSS()`** only (wizard-specific CSS is skipped).
2. Loads schema/model, may show fullscreen blocking overlay HTML during load/compute.
3. Renders **sidebar** edit panel via **`render_left_edit_panel()`**.
4. Renders **main area** with title, warnings/errors, then **`st.tabs([...])`** for results.

**Purpose:** Edit inputs in sidebar and explore **Offer recommendation**, **Offer analytics**, **Model Details**.

This is **not** client-side routing — it is **server reruns** with a boolean gate.

---

## 3. Session state contract (what the UI depends on)

These keys matter for behavior and layout (non-exhaustive; many `sb_*` mirror model inputs):

| Key | Role |
|-----|------|
| `analysis_submitted` | **Master switch:** wizard vs results experience |
| `quote_submitted` | Legacy alias; kept in sync for compatibility |
| `current_step` | Wizard step index `0 … len(SIDEBAR_SECTION_ORDER)-1` |
| `edit_panel_section` | Which logical section is selected in sidebar (post-submit) |
| `analysis_compute_requested` | Forces recomputation when user clicks Re-run |
| `analysis_run_cache` | Caches last run outputs to avoid redundant work |

**Widget values:** Almost all inputs use **`sb_*`** keys (e.g. `sb_fico_score`, `sb_monthly_income`). Streamlit widgets bind directly to `session_state[key]`.

**Migration:** Your new UI should read/write the same logical fields (REST body, WebSocket state, or store) so **`collect_inputs_from_session_state()` / `build_business_inputs()`** can stay unchanged if the backend stays Python.

---

## 4. Wizard structure (`render_full_page_wizard`)

**Section order** — `SIDEBAR_SECTION_ORDER` in `app.py`:

`customer` → `vehicle` → `dealer_inv` → `financing` → `competitor` → `macro`

**Render sequence per step:**

1. **`render_hero()`** — HTML `<header class="demo-hero">` with title + subtitle (`unsafe_allow_html`).
2. **`render_step_card_header(step, sec)`** — Step meta (`demo-step-meta`), step title (`demo-step-title`), scroll anchor `wizard-step-scroll-target`.
3. **`_wizard_flush_scroll_top()`** — Injects `components.html` script to align scroll (see §9).
4. **`render_quote_section_fields(sec, wizard=True)`** — All fields for that section (see §5).
5. **`render_navigation(step)`** — Back / Next / Run analysis buttons.
6. **`_wizard_flush_scroll_top()`** again.

**Two-column layout:** **`_wizard_pair_columns()`** → `st.columns(2, gap="large")` with CSS gap fallback on horizontal blocks.

---

## 5. Field rendering patterns (same functions, two layouts)

**Single implementation:** **`render_quote_section_fields(sec, wizard=True|False)`**

- **`wizard=True`:** Full-page columns, custom HTML labels (`demo-field-label`), bordered slider groups.
- **`wizard=False`:** Same field keys rendered into **`st.sidebar`** with compact labels (`_sb_row_label_help`).

### Common widget patterns

| Pattern | Streamlit primitives | Notes |
|---------|----------------------|--------|
| **Slider + exact value** | `_slider_int_with_exact` / `_slider_float_with_exact` | `st.slider` + `st.caption("Exact value")` + `st.text_input` inside **`st.container(border=True)`** → renders as **`stVerticalBlockBorderWrapper`** |
| **1–10 behavioral sliders** | `render_slider_1_10` | Wrapper around slider+exact + **`_slider_scale_caption`** → **`render_scale_guide`** (hint line + `st.expander("Scale guide")`) |
| **Continuous sliders** | `_slider_range_caption` | Short summary + expander “Full scale detail” |
| **Labels with ? help** | `_field_label` + **`_help_icon_html`** | Pure HTML markdown; popup via CSS (`.exec-field-help-wrap`) |
| **DTI KPI** | `render_dti_kpi_card` | HTML divs `.demo-kpi-card` |
| **Native Streamlit help** | `_input_help()` → `help=` on widgets | Streamlit’s `?` in chrome |

**Migration:** Map each pattern to your design system: slider + numeric input + optional collapsible “scale guide” / “full detail”.

---

## 6. CSS architecture (how “the UI look” is enforced)

Streamlit does **not** use a separate stylesheet file for the app. Instead:

1. **`EXEC_FONT_LINKS()`** — Google Fonts preconnect + Inter weights 400–700.
2. **`EXEC_THEME_CSS()`** — Always injected in `main()`:
   - **`:root` spacing tokens** (`--space-xxs` … `--exec-*` semantics)
   - **Main column** `.block-container`: `max-width: 1180px`, centered, horizontal padding via tokens
   - **Streamlit `data-testid` overrides** — `stMarkdownContainer`, `stVerticalBlockBorderWrapper`, `stVegaLiteChart`, `stMetricContainer`, `stExpander`, sliders, sidebar, tabs, etc.
   - **Executive HTML classes** — `.exec-hero-card`, `.exec-scenario-compare-card`, `.exec-chart-guide`, `.exec-section-title`, `.exec-scale-guide`, …
3. **`EXEC_WIZARD_DEMO_UI_CSS()`** — Injected **only in wizard mode**:
   - Hides **`section[data-testid="stSidebar"]`**
   - `.demo-hero`, `.demo-step-meta`, `.demo-section-title`, `.demo-field-label`, `.demo-kpi-card`, wizard-only slider/card tightening, column gap

**Important:** Styling targets **Streamlit’s DOM** (`[data-testid="stVerticalBlock"]`, `[data-baseweb="slider"]`, etc.). A new platform will **not** have these nodes — you preserve **class names** on your own components where you want parity, or rebuild visuals from the token list in `:root`.

---

## 7. HTML islands (non-widget UI)

Large parts of the “executive” dashboard are **strings of HTML** passed to `st.markdown(..., unsafe_allow_html=True)`:

- Executive summary callout (`.exec-summary-callout`)
- Scenario comparison grid (`.exec-scenario-compare-grid`, `.esc-row`, …)
- Hero metric tiles (`.exec-hero-metric-tile`, `.ehm-label`, …)
- Chart titles / guides (`exec-chart-title-main`, `exec-chart-guide`)
- Loader overlay (`MODEL_LOADING_PANEL_HTML`, `.exec-ml-fullscreen`)

**Migration:** These become React/Vue/Svelte components or server-rendered templates using the **same class names** if you want a drop-in CSS port, or redesign while keeping data bindings from the existing Python functions that build the strings.

---

## 8. Results area layout (post-submit)

1. **Sidebar:** `render_left_edit_panel()` — horizontal radio for section, then **`render_quote_section_fields(sec, wizard=False)`**, then **Re-run analysis** / **Clear results**.
2. **Main:** `st.title`, intro markdown, validation messages.
3. **Tabs:** `st.tabs(["Offer recommendation", "Offer analytics", "Model Details"])`.

Tab bodies mix Streamlit primitives (`st.dataframe`, `st.altair_chart`, expanders, popovers) with **`st.markdown` HTML** for executive cards and tables.

---

## 9. Scroll behavior (Streamlit-specific)

**`_wizard_request_scroll_top`** / **`_wizard_flush_scroll_top`** use **`streamlit.components.v1.html`** to inject JavaScript that scrolls nested scroll containers so the step header aligns to the top. 

**Migration:** Replace with your framework’s scroll-into-view on route/step change, or drop if you use real URL routing and short pages.

---

## 10. Charts & tables

- **Altair** charts via `st.altair_chart` — CSS targets `[data-testid="stVegaLiteChart"]` for padding.
- **Data tables** — `st.dataframe` / column config; CSS targets `[data-testid="stDataFrame"]` for cell padding.

**Migration:** Use your chart library (or Vega-Embed) and table component; keep the **same data** the Python functions already prepare.

---

## 11. Deployment gate

**`_deployment_startup_gate()`** runs early in `main()` and can block the rest of the UI — preserve any env/config checks in your new shell.

---

## 12. Practical migration checklist

1. **Replicate mode split:** Landing wizard vs authenticated/analysis view — map `analysis_submitted` to a route or global store flag.
2. **Port spacing tokens:** Copy `:root` variables from `EXEC_THEME_CSS()` into your global CSS / theme provider.
3. **Rebuild layouts:** Wizard = hero + step header + 2-col grid + footer nav; Analysis = sidebar form + 3 tabs.
4. **Replace Streamlit widgets** with native controls; keep **field keys** aligned with `sb_*` or a single JSON payload your existing `build_business_inputs` accepts.
5. **Replace `st.markdown` HTML** with components; keep class names for faster CSS reuse or redesign intentionally.
6. **Replace scroll hacks** with standard SPA behavior.
7. **API layer:** Optionally expose `build_business_inputs`, validation, and model endpoints via FastAPI/Flask; new UI calls HTTP instead of in-process Streamlit.

---

## 13. File map (UI-related)

| Location | Contents |
|----------|----------|
| `app.py` | All UI: `main`, render functions, CSS string builders, HTML helpers |
| `docs/architecture.md` | Model/data pipeline (complements this doc) |
| `.streamlit/config.toml` (if present) | Theme accent / Streamlit chrome |

---

## 14. What not to reimplement blindly

- **Streamlit rerun semantics:** Every interaction re-executes the script from top to bottom. A SPA should use **explicit event handlers** instead.
- **`unsafe_allow_html`:** Treat as **trusted HTML** generated by your code — in a new app, use JSX/templates with escaping discipline.
- **`data-testid` selectors:** They are **implementation details** of Streamlit’s DOM; only the **design tokens and class names** you own (`demo-*`, `exec-*`) are stable contracts if you choose to keep them.

This should be enough to replatform the **structure and contracts** of the UI while keeping **model and optimizer code** in Python or behind services unchanged.
