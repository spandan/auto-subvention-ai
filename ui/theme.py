"""Design tokens + global CSS — executive SaaS hierarchy (Linear / Stripe-adjacent)."""

from __future__ import annotations

# -----------------------------------------------------------------------------
# Color primitives
# -----------------------------------------------------------------------------
BG = "#F8FAFC"
CARD = "#FFFFFF"
TEXT_PRIMARY = "#111827"
TEXT_SECONDARY = "#6B7280"
TEXT_TERTIARY = "#9CA3AF"
BORDER = "#E5E7EB"
BORDER_SOFT = "#F1F5F9"
ACCENT = "#334155"
ACCENT_MUTED = "#64748B"
REC_BG = "#DCFCE7"
REC_TEXT = "#166534"
INPUT_BG = "#FAFBFC"
WARN_SURFACE = "#FFFBEB"
WARN_TEXT = "#92400E"

# Content width — intentional density, no ultra-wide stretch
PAGE_MAX_W = "1180px"
# Post-optimization executive canvas (wizard body stays PAGE_MAX_W)
PAGE_RESULTS_MAX_W = "1500px"

# Scale anchor for repeated slider tooltips (never repeat as body copy)
SLIDER_SCALE_TOOLTIP = "1–10 scale: 1 = lowest intensity · 5 = moderate · 10 = highest."


def theme_css() -> str:
    """Spacing tokens: 4 · 8 · 12 · 16 · 20 · 24 · 32 — typography levels L1–L5."""
    return f"""
/* ----- Design tokens ----- */
:root {{
  --bg-page: {BG};
  --surface: {CARD};
  --surface-muted: {INPUT_BG};
  --text: {TEXT_PRIMARY};
  --muted: {TEXT_SECONDARY};
  --muted-2: {TEXT_TERTIARY};
  --border: {BORDER};
  --border-soft: {BORDER_SOFT};
  --accent: {ACCENT};
  --accent-muted: {ACCENT_MUTED};
  --rec-bg: {REC_BG};
  --rec-text: {REC_TEXT};
  --warn-bg: {WARN_SURFACE};
  --warn-text: {WARN_TEXT};

  --s-1: 4px;
  --s-2: 8px;
  --s-3: 12px;
  --s-4: 16px;
  --s-5: 20px;
  --s-6: 24px;
  --s-8: 32px;

  --radius-lg: 16px;
  --radius-md: 10px;
  --radius-sm: 8px;

  /* ~20% tighter than generic defaults */
  --font-hero: 36px;
  --font-h2: 17px;
  --font-label: 13px;
  --font-helper: 12px;
  --font-micro: 11px;
  --font-subtitle: 15px;
  --font-dash-title: 28px;

  --field-gap: 6px;
  --stack-gap: 10px;
  --section-gap: 16px;
}}

body {{
  background: var(--bg-page) !important;
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.45;
  letter-spacing: -0.01em;
}}

/* ----- Shell (tight vertical rhythm; no floating island) ----- */
.app-shell {{
  max-width: {PAGE_RESULTS_MAX_W};
  margin: 0 auto;
  padding: var(--s-3) var(--s-4) var(--s-5);
}}

.app-header-inner {{
  max-width: {PAGE_RESULTS_MAX_W};
  margin: 0 auto;
  padding: var(--s-2) var(--s-4);
}}

.app-header-brand-col {{
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-start;
  min-width: 0;
}}

.header-subtitle {{
  font-size: 12px !important;
  font-weight: 500 !important;
  color: var(--muted) !important;
  letter-spacing: 0 !important;
  line-height: 1.35 !important;
}}

/* ----- Typography hierarchy ----- */
.ds-page-title {{
  font-size: var(--font-hero);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.025em;
  color: var(--text);
  margin: 0 0 var(--s-1);
}}

.ds-page-subtitle {{
  font-size: var(--font-subtitle);
  font-weight: 400;
  line-height: 1.4;
  color: var(--muted);
  margin: 0 0 var(--s-5);
}}

.ds-dash-title {{
  font-size: var(--font-dash-title);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
  margin: 0 0 var(--s-1);
}}

.ds-h2 {{
  font-size: var(--font-h2);
  font-weight: 600;
  letter-spacing: -0.015em;
  color: var(--text);
  margin: 0 0 var(--s-3);
}}

/* Wizard main step headline (Customer Profile, Vehicle & Product, …) */
.wizard-step-title {{
  font-size: clamp(22px, 2.65vw, 26px);
  font-weight: 700;
  line-height: 1.18;
  letter-spacing: -0.022em;
  color: var(--text);
  margin: 0 0 var(--s-4);
}}

.ds-step-meta {{
  font-size: var(--font-micro);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin: 0 0 var(--s-2);
}}

.ds-label {{
  font-size: var(--font-label);
  font-weight: 500;
  color: var(--text);
}}

.ds-helper {{
  font-size: var(--font-helper);
  color: var(--muted);
  line-height: 1.35;
}}

.ds-micro {{
  font-size: var(--font-micro);
  color: var(--muted-2);
  line-height: 1.35;
}}

/* ----- Cards ----- */
.ds-card-step {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
  padding: var(--s-5);
  width: 100%;
  box-sizing: border-box;
}}

.ds-card-muted {{
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}}

/* Two-column wizard grid + premium vertical divider */
.ds-row-two {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 0;
  row-gap: var(--section-gap);
  align-items: start;
}}
/* Left column breathing room before the rule */
.ds-row-two > .ds-col-stack:first-of-type {{
  padding-right: var(--s-6);
}}
/* Sophisticated vertical separator — gradient feather + subtle highlight */
.ds-row-two > .ds-col-stack:nth-of-type(2) {{
  position: relative;
  padding-left: var(--s-6);
}}
.ds-row-two > .ds-col-stack:nth-of-type(2)::before {{
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 1px;
  border-radius: 1px;
  background: linear-gradient(
    180deg,
    rgba(148, 163, 184, 0) 0%,
    rgba(148, 163, 184, 0.45) 8%,
    #94a3b8 45%,
    #94a3b8 55%,
    rgba(148, 163, 184, 0.45) 92%,
    rgba(148, 163, 184, 0) 100%
  );
  box-shadow:
    1px 0 0 rgba(255, 255, 255, 0.85),
    -1px 0 1px rgba(15, 23, 42, 0.04);
  pointer-events: none;
}}
@media (max-width: 880px) {{
  .ds-row-two {{ grid-template-columns: 1fr; }}
  .ds-row-two > .ds-col-stack:first-of-type {{ padding-right: 0; }}
  .ds-row-two > .ds-col-stack:nth-of-type(2) {{ padding-left: 0; }}
  .ds-row-two > .ds-col-stack:nth-of-type(2)::before {{ display: none; }}
}}

/* Vertical rhythm inside columns */
.ds-col-stack {{
  display: flex;
  flex-direction: column;
  gap: var(--stack-gap);
}}

/* Single field: label → 6px → control → 6px optional helper */
.ds-field {{
  display: flex;
  flex-direction: column;
  gap: var(--field-gap);
}}

.ds-field-head {{
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: var(--s-2);
  min-height: 22px;
}}

.ds-field-head .ds-label {{
  flex: 1 1 auto;
  margin: 0;
}}

/* Group related fields without nesting cards */
.ds-field-group {{
  padding-bottom: var(--s-3);
  margin-bottom: var(--s-3);
  border-bottom: 1px solid var(--border-soft);
}}
.ds-field-group:last-child {{
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}}

/* ----- KPI ----- */
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(138px, 1fr));
  gap: var(--s-3);
}}
.kpi-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--s-3) var(--s-4);
}}
.kpi-val {{
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1.2;
}}
.kpi-lbl {{
  font-size: var(--font-micro);
  font-weight: 500;
  color: var(--muted);
  margin-top: var(--s-1);
  line-height: 1.25;
}}

/* Executive metric chip (e.g. computed DTI) */
.ds-kpi-chip {{
  background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--s-3) var(--s-4);
  margin-top: var(--s-2);
}}
.ds-kpi-chip-value {{
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--accent);
  line-height: 1.15;
}}
.ds-kpi-chip-label {{
  font-size: var(--font-micro);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: var(--s-1);
}}
.ds-kpi-chip-hint {{
  font-size: var(--font-micro);
  color: var(--muted-2);
  margin-top: var(--s-1);
}}

/* ----- Chart shells ----- */
.chart-panel {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--s-3);
  box-sizing: border-box;
}}

/* ----- Table ----- */
.rec-row {{
  background: var(--rec-bg) !important;
}}

.panel-compact {{
  max-height: 70vh;
  overflow-y: auto;
}}

/* ----- NiceGUI / Quasar density + refined inputs ----- */
.q-field--dense .q-field__control {{
  min-height: 36px !important;
}}
.q-field--outlined .q-field__control {{
  border-radius: var(--radius-md) !important;
  background: var(--surface-muted) !important;
}}
.q-field--outlined .q-field__control:before {{
  border-color: var(--border) !important;
  border-radius: inherit !important;
}}
.q-field--outlined .q-field__control:after {{
  border-radius: inherit !important;
}}
.q-field--focused .q-field__control:before {{
  border-color: var(--accent) !important;
  border-width: 1px !important;
}}
.q-field__native {{
  border-radius: var(--radius-md) !important;
}}
.q-field__marginal {{
  border-radius: 0 var(--radius-md) var(--radius-md) 0 !important;
}}
.q-field {{
  font-size: 13px !important;
}}

/* Tooltips — multi-line (\\n / sentence breaks), readable typography */
.q-tooltip {{
  white-space: pre-line !important;
  max-width: min(520px, 96vw);
  padding: var(--s-4) var(--s-5) !important;
  border-radius: var(--radius-sm) !important;
  box-shadow:
    0 4px 6px rgba(15, 23, 42, 0.05),
    0 12px 24px rgba(15, 23, 42, 0.1) !important;
  font-size: var(--font-helper) !important;
  font-weight: 400 !important;
  line-height: 1.5 !important;
  text-align: left !important;
  color: #1e293b !important;
  background: #ffffff !important;
  border: 1px solid var(--border) !important;
}}
.q-tooltip *,
.q-tooltip .q-tooltip-content {{
  white-space: pre-line !important;
}}
.q-slider {{
  min-height: 28px !important;
  padding: var(--s-1) 0 !important;
}}
.q-slider__track-container {{
  height: 4px !important;
}}
.q-slider__thumb {{
  width: 14px !important;
  height: 14px !important;
}}
.q-btn {{
  font-size: 13px !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em !important;
  /* Baseline breathing room (dense props still apply; sections below override where needed) */
  padding-left: 14px !important;
  padding-right: 14px !important;
}}

.header-brand {{
  font-size: 15px !important;
  font-weight: 600 !important;
  letter-spacing: -0.02em !important;
  color: var(--text) !important;
}}

/* Wizard actions row */
.ds-wizard-actions {{
  margin-top: var(--s-6);
  padding-top: var(--s-4);
  border-top: 1px solid var(--border-soft);
}}

/* Back / Next / Run Optimization — rounded + room for label */
.ds-wizard-actions .q-btn {{
  border-radius: var(--radius-md) !important;
  padding: 10px 24px !important;
  min-height: 42px !important;
}}
.ds-wizard-actions .q-btn .q-btn__wrapper {{
  padding: 0 !important;
  min-height: inherit !important;
}}

/* Optimization loading overlay (card typography) */
.optimization-loading-card {{
  padding: 28px 32px !important;
  border-radius: 18px !important;
  border: 1px solid var(--border) !important;
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.05),
    0 24px 48px rgba(15, 23, 42, 0.08) !important;
}}
.ol-heading {{
  font-size: 1.375rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em !important;
  color: #0f172a !important;
  margin-bottom: 6px !important;
}}
.ol-subheading {{
  font-size: 0.9rem !important;
  font-weight: 400 !important;
  color: #64748b !important;
  line-height: 1.45 !important;
  margin-bottom: 20px !important;
}}
.ol-rotating-tip {{
  font-size: 0.9rem !important;
  font-weight: 400 !important;
  color: #64748b !important;
  line-height: 1.45 !important;
  margin-bottom: 0 !important;
  min-height: 2.9em !important;
  max-width: 28rem !important;
}}

/* Results (badge only; rail + KPI use dash-* tokens) */
.rs-badge {{
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.03em;
  background: var(--rec-bg);
  color: var(--rec-text);
  border: 1px solid #bbf7d0;
}}
.rs-comp-highlight {{
  background: rgba(220, 252, 231, 0.45) !important;
}}
.def-row {{
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
  align-items: baseline;
}}
.def-row:last-child {{ border-bottom: none; }}

/* ----- Executive results dashboard shell (CSS grid, tight rail gap) ----- */
.dashboard-shell {{
  width: 100%;
  max-width: {PAGE_RESULTS_MAX_W};
  margin: 0 auto;
  padding: 20px 24px 40px;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 24px;
  align-items: stretch;
  /* Independent scroll: rail vs main (desktop); header ~app header + shell padding */
  height: calc(100dvh - 96px);
  min-height: 320px;
  overflow: hidden;
}}

@media (max-width: 960px) {{
  .dashboard-shell {{
    grid-template-columns: 1fr;
    padding: var(--s-4);
    height: auto;
    min-height: unset;
    overflow: visible;
  }}
  .sidebar-panel,
  .results-main {{
    max-height: none;
    overflow-y: visible;
  }}
}}

.sidebar-panel {{
  position: relative;
  top: auto;
  align-self: stretch;
  min-width: 0;
  min-height: 0;
  max-height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}}

/* One consistent column width: cards, adjust list, and run buttons all span the rail */
.sidebar-panel > * {{
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box;
}}

.results-main {{
  min-width: 0;
  min-height: 0;
  max-height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  width: 100%;
  gap: var(--s-5) !important;
  align-items: stretch !important;
}}

.snapshot-pane-heading {{
  margin-bottom: var(--s-3);
}}

.snapshot-pane-title {{
  font-size: 15px;
  font-weight: 700;
  color: #111827;
  letter-spacing: -0.015em;
  line-height: 1.25;
}}

.snapshot-pane-sub {{
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-2);
  margin-top: 2px;
}}

.snapshot-card {{
  display: block;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #ffffff;
  margin-bottom: 10px;
}}
.snapshot-card:last-of-type {{
  margin-bottom: 0;
}}

.snapshot-label {{
  font-size: 11px;
  letter-spacing: 0.08em;
  color: #9ca3af;
  font-weight: 700;
  text-transform: uppercase;
}}

.snapshot-primary {{
  font-size: 14px;
  font-weight: 700;
  color: #111827;
  margin-top: 6px;
  line-height: 1.35;
}}

.snapshot-secondary {{
  font-size: 13px;
  color: #64748b;
  line-height: 1.42;
  margin-top: 3px;
}}

.rail-section {{
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  margin-bottom: var(--s-4);
}}
.rail-section:last-child {{
  margin-bottom: 0;
}}

.rail-section-label {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted-2);
  margin: 0 0 10px 0;
  padding: 0;
}}

.rail-actions {{
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  width: 100%;
}}

/* Single card of edit actions — matches snapshot-card chrome */
.rail-btn-stack {{
  display: block;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
}}

.rail-btn-stack .rail-edit-btn.q-btn {{
  width: 100% !important;
  min-height: 0 !important;
  height: auto !important;
  justify-content: flex-start !important;
  align-items: center !important;
  padding: 9px 14px !important;
  margin: 0 !important;
  border-radius: 0 !important;
  border-bottom: 1px solid #f1f5f9 !important;
  box-shadow: none !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  line-height: 1.35 !important;
  letter-spacing: -0.01em;
  color: #1e293b !important;
  text-transform: none !important;
}}
.rail-btn-stack .rail-edit-btn.q-btn:last-child {{
  border-bottom: none !important;
}}
.rail-btn-stack .rail-edit-btn.q-btn .q-btn__content {{
  justify-content: flex-start !important;
  width: 100%;
  padding: 0 !important;
}}
.rail-btn-stack .rail-edit-btn.q-btn:hover {{
  background: #f8fafc !important;
}}

/* Run blocks: tighter vertical rhythm aligned to snapshot spacing */
.rail-run-stack {{
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  align-items: stretch;
}}

.btn-dash.q-btn {{
  width: 100% !important;
  max-width: 100% !important;
  align-self: stretch !important;
  box-sizing: border-box !important;
  justify-content: center !important;
  min-height: 42px !important;
  padding: 11px 20px !important;
  border-radius: var(--radius-sm) !important;
  font-size: 12px !important;
  font-weight: 600 !important;
}}

.btn-dash-primary {{
  background: #334155 !important;
  color: #fff !important;
}}

.btn-dash-secondary {{
  color: #334155 !important;
  border: 1px solid #cbd5e1 !important;
  background: #fff !important;
}}

.btn-dash-muted {{
  color: #475569 !important;
  border: 1px solid #e2e8f0 !important;
  background: #f8fafc !important;
}}

.rail-run-outline.q-btn {{
  width: 100% !important;
  max-width: 100% !important;
  align-self: stretch !important;
  box-sizing: border-box !important;
  min-height: 42px !important;
  padding: 11px 20px !important;
  border-radius: 10px !important;
  justify-content: center !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  color: #334155 !important;
  border: 1px solid #e5e7eb !important;
  background: #ffffff !important;
}}
.rail-run-outline.q-btn:hover {{
  background: #f8fafc !important;
}}

/* Hero: title block + Optimization Summary card */
.dash-hero-row {{
  width: 100%;
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-4);
  flex-wrap: wrap;
}}

.dash-title-main {{
  font-size: 40px;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #0f172a;
  line-height: 1.1;
  margin: 0;
}}

.dash-title-sub {{
  font-size: 15px;
  font-weight: 400;
  color: #64748b;
  line-height: 1.45;
  margin: var(--s-2) 0 0 0;
  max-width: 520px;
}}

.dash-badge-row {{
  margin-top: var(--s-3);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}}

.opt-summary-card {{
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--s-3) var(--s-4);
  min-width: 240px;
  flex-shrink: 0;
}}

.opt-summary-card-title {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted-2);
  margin-bottom: var(--s-3);
  padding-bottom: var(--s-2);
  border-bottom: 1px solid var(--border-soft);
}}

.opt-summary-row {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--s-4);
  font-size: 12px;
  margin-bottom: var(--s-2);
  line-height: 1.35;
}}
.opt-summary-row:last-child {{
  margin-bottom: 0;
}}

.opt-summary-k {{
  color: var(--muted);
  font-weight: 500;
  flex-shrink: 0;
}}

.opt-summary-v {{
  color: #0f172a;
  font-weight: 600;
  text-align: right;
}}

/* KPI grid */
.kpi-exec-grid {{
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: var(--s-4);
  width: 100%;
}}

@media (max-width: 1200px) {{
  .kpi-exec-grid {{
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }}
}}
@media (max-width: 720px) {{
  .kpi-exec-grid {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }}
}}

.kpi-exec-cell {{
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 18px;
  min-height: 112px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  box-sizing: border-box;
  container-type: inline-size;
  container-name: kpi-exec;
}}

.kpi-exec-cell--accent {{
  background: linear-gradient(180deg, #f0fdf4 0%, #ffffff 55%);
  border-color: #bbf7d0;
}}

.kpi-exec-label {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #64748b;
  order: 1;
}}

.kpi-exec-value {{
  /* Fallback when cqi unsupported */
  font-size: clamp(21px, 2.45vw, 30px);
  font-weight: 800;
  letter-spacing: -0.035em;
  color: #0f172a;
  line-height: 1.05;
  margin: var(--s-3) 0 auto 0;
  order: 2;
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  min-width: 0;
  white-space: nowrap;
}}

@supports (font-size: 1cqi) {{
  .kpi-exec-value {{
    font-size: clamp(18px, min(2.45vw, 12cqi), 30px);
  }}
}}

.kpi-exec-hint {{
  font-size: 11px;
  font-weight: 500;
  color: var(--muted-2);
  margin-top: var(--s-3);
  line-height: 1.35;
  order: 3;
}}

.dash-section-h2 {{
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #0f172a;
  margin: 0;
  line-height: 1.2;
}}

/* Flat analytic panels (not floating hero cards) */
.dash-panel {{
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 18px;
  margin: 0;
  box-shadow: none;
}}

/* Current / Recommended / Aggressive table: do not shrink inside flex column (avoids tiny scroll box) */
.offer-comparison-panel {{
  flex-shrink: 0;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  overflow-x: auto;
  overflow-y: visible;
  max-height: none;
  min-height: min-content;
}}
.offer-comparison-grid-inner {{
  display: grid;
  grid-template-columns: minmax(140px, 1.1fr) repeat(3, minmax(0, 1fr));
  grid-auto-rows: minmax(44px, auto);
  gap: 0;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
  width: 100%;
  min-width: min(100%, 720px);
}}

.chart-card {{
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 20px 22px;
  margin: 0;
  box-shadow: none;
}}

.chart-header {{
  margin-bottom: 16px;
}}

.chart-title {{
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 6px 0;
  line-height: 1.25;
  letter-spacing: -0.018em;
  color: #0f172a;
}}

.chart-subtitle {{
  font-size: 13px;
  font-weight: 400;
  color: #64748b;
  line-height: 1.5;
  margin: 0 0 14px 0;
  max-width: 880px;
}}

.chart-body {{
  width: 100%;
  margin-top: 0;
}}

.chart-plot {{
  margin-top: 0;
}}

/* Top scenarios table: highlight optimizer recommendation row */
.scenarios-results-table .scenario-row--recommended td {{
  background-color: rgba(220, 252, 231, 0.92) !important;
  color: #14532d !important;
  font-weight: 600;
}}
.scenarios-results-table .scenario-row--recommended td:first-child {{
  box-shadow: inset 3px 0 0 0 #22c55e;
}}

.scenarios-results-table .scenario-row--aggressive td {{
  background-color: rgba(254, 243, 199, 0.85) !important;
  color: #92400e !important;
  font-weight: 600;
}}
.scenarios-results-table .scenario-row--aggressive td:first-child {{
  box-shadow: inset 3px 0 0 0 #f59e0b;
}}

.scenarios-results-table .scenario-row--current td {{
  background-color: rgba(241, 245, 249, 0.95) !important;
  color: #334155 !important;
  font-weight: 600;
}}
.scenarios-results-table .scenario-row--current td:first-child {{
  box-shadow: inset 3px 0 0 0 #64748b;
}}
"""
