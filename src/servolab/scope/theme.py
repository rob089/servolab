"""
ServoScope look and feel: colours, typography, card styles.

Everything visual that is not layout lives here, so the look can be changed in
one place. The style follows the TUM MiMed Robot Learning Hub: paper and ink.
Warm paper ground, white panels with solid ink borders and big radii, no soft
shadows (only a hard offset "block" shadow), Bricolage Grotesque for headings,
Space Grotesk for text and JetBrains Mono for values and small uppercase
"kickers". Diagonal hatching means "missing / offline / not yet".

Accent is TUM blue (IDs, links, primary actions); warn and bad have their own
colours. Plots are drawn in ink, the accent only marks the goal.
"""

from nicegui import ui

# --- Paper and ink ----------------------------------------------------------
PAGE = "#F6F5F2"              # page ground, sidebar
RAISED = "#FFFFFF"            # panels (cards), inputs
SUNKEN = "#EFEEEA"            # hover, code, tracks
INK = "#171614"               # text and borders ("rules")
INK_2 = "#4A4845"             # secondary text
INK_3 = "#6C6A65"             # labels, units, captions
LINE = "rgba(23, 22, 20, .14)"    # light dividers inside panels
LINE_2 = "rgba(23, 22, 20, .30)"  # borders of secondary things (inner boxes, dashed)
GRID = "#E7E5E0"              # plot grid (opaque LINE on white)

# --- Brand ------------------------------------------------------------------
ACCENT = "#3070B3"            # TUM blue
ACCENT_INK = "#245A94"        # blue text on paper, pressed buttons
ACCENT_SOFT = "#DCE8F5"
MIMED_YELLOW = "#F4C93F"
PANEL = "#0A1B33"             # navy (MiMed), for dark panels
MIMED_URL = "https://www.mimed.de"

# --- Status -----------------------------------------------------------------
OK = "#2F6B4F"
OK_SOFT = "#DDE8DF"
WARN = "#C98A0B"
WARN_INK = "#8A5A00"
WARN_SOFT = "#FBEFD3"
BAD = "#E8452A"
BAD_INK = "#B8331A"
BAD_SOFT = "#FBE3DA"

# --- Plots ------------------------------------------------------------------
PLOT_MAIN = INK
PLOT_GOAL = ACCENT
PLOT_GRID = GRID
PLOT_SERIES = [INK, ACCENT, WARN, OK, BAD, INK_3]

FONT_HEADING = '"Bricolage Grotesque", "Helvetica Neue", Arial, sans-serif'
FONT_TEXT = '"Space Grotesk", "Helvetica Neue", Arial, sans-serif'
FONT_MONO = '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace'

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Bricolage+Grotesque:opsz,wght@12..96,400..800'
    '&family=JetBrains+Mono:wght@400;500;600'
    '&family=Space+Grotesk:wght@400;500;600;700&display=swap">'
)

HATCH = "repeating-linear-gradient(45deg, var(--sl-sunken) 0 7px, var(--sl-page) 7px 14px)"

CSS = f"""
:root {{
  --sl-page: {PAGE}; --sl-raised: {RAISED}; --sl-sunken: {SUNKEN};
  --sl-ink: {INK}; --sl-ink-2: {INK_2}; --sl-ink-3: {INK_3};
  --sl-line: {LINE}; --sl-line-2: {LINE_2};
  --sl-accent: {ACCENT}; --sl-accent-ink: {ACCENT_INK}; --sl-accent-soft: {ACCENT_SOFT};
  --sl-yellow: {MIMED_YELLOW}; --sl-panel: {PANEL};
  --sl-ok: {OK}; --sl-ok-soft: {OK_SOFT};
  --sl-warn: {WARN}; --sl-warn-ink: {WARN_INK}; --sl-warn-soft: {WARN_SOFT};
  --sl-bad: {BAD}; --sl-bad-ink: {BAD_INK}; --sl-bad-soft: {BAD_SOFT};
  --sl-shadow-block: 8px 8px 0 rgba(23, 22, 20, .09);
  --sl-font-heading: {FONT_HEADING};
  --sl-font-text: {FONT_TEXT};
  --sl-font-mono: {FONT_MONO};
}}

/* ---------- base ---------- */
body {{
  background: var(--sl-page);
  color: var(--sl-ink);
  font-family: var(--sl-font-text);
  font-size: 14.5px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}
.q-btn, .q-field, .q-item, .q-tab, .q-toggle, .q-notification, .q-tooltip, .q-table, .q-menu {{
  font-family: var(--sl-font-text);
}}
.q-field__native, .q-field__suffix {{ font-variant-numeric: tabular-nums; }}
.q-separator {{ background: var(--sl-line); }}
.q-tooltip {{ background: var(--sl-ink); color: var(--sl-page); font-size: 12.5px; border-radius: 6px; }}
.q-notification {{ border-radius: 12px; }}

/* buttons: ink-bordered pills */
.q-btn {{ text-transform: none; font-weight: 500; letter-spacing: 0; border-radius: 999px; }}
.q-btn--outline:before {{ border-width: 1.5px; }}
/* the two big sidebar buttons (Connect, All torque off): same size, colour tells them apart */
.q-btn.sl-btn-main {{ min-height: 44px; font-size: 15px; font-weight: 600; }}

/* inputs: ink frame on white */
.q-field--outlined .q-field__control {{ border-radius: 6px; background: var(--sl-raised); }}
.q-field--outlined .q-field__control:before {{ border: 1.5px solid var(--sl-ink); }}
.q-field--outlined.q-field--readonly .q-field__control:before {{ border-style: dashed; border-color: var(--sl-line-2); }}
.q-field--dense .q-field__label {{ font-size: 13px; }}

/* segmented choice (ui.toggle with TOGGLE_PROPS): separate pills, the chosen one inverted */
.sl-seg.q-btn-group {{ box-shadow: none; background: none; gap: 6px; border-radius: 0; flex-wrap: wrap; }}
.sl-seg.q-btn-group > .q-btn-item {{
  border-radius: 999px !important; border: 1.5px solid var(--sl-ink); font-weight: 500;
}}
.sl-seg.q-btn-group > .q-btn-item:not(.bg-dark):hover {{ background: var(--sl-sunken) !important; }}
.sl-seg-sm.q-btn-group > .q-btn-item {{ padding: 0 12px; min-height: 30px; font-size: 13px; }}

/* sliders and switches in ink */
.q-slider__track {{ background: var(--sl-sunken); border-radius: 999px; }}
.q-slider__thumb-shape path {{ stroke: var(--sl-raised); stroke-width: 3px; }}
.q-slider__pin, .q-slider__text-container {{ font-family: var(--sl-font-mono); }}

/* dialogs */
.q-dialog .q-card {{
  border: 1.5px solid var(--sl-ink); border-radius: 20px; box-shadow: var(--sl-shadow-block);
}}

/* ---------- type ---------- */
.sl-h1 {{
  font-family: var(--sl-font-heading); font-weight: 800;
  font-size: clamp(36px, 4.2vw, 54px); line-height: .98; letter-spacing: -.035em; color: var(--sl-ink);
}}
.sl-h2, .sl-card-title {{
  font-family: var(--sl-font-heading); font-weight: 700;
  font-size: 22px; line-height: 1.08; letter-spacing: -.02em; color: var(--sl-ink);
}}
.sl-h3 {{
  font-family: var(--sl-font-heading); font-weight: 700;
  font-size: 17px; line-height: 1.15; letter-spacing: -.015em; color: var(--sl-ink);
}}
/* small mono uppercase label above a value or a heading */
.sl-kicker {{
  font-family: var(--sl-font-mono); font-size: 11px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--sl-ink-3); line-height: 1.4;
}}
.sl-label {{ font-weight: 600; font-size: 13.5px; color: var(--sl-ink); }}
.sl-hint {{ font-size: 12.5px; color: var(--sl-ink-3); line-height: 1.45; }}
.sl-muted {{ color: var(--sl-ink-3); }}
.sl-mono {{ font-family: var(--sl-font-mono); font-size: .9em; }}
.sl-num {{ font-variant-numeric: tabular-nums; }}

/* page head: kicker, big title, mono meta row */
.sl-metarow {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px 0;
  font-family: var(--sl-font-mono); font-size: 12px; letter-spacing: .04em; color: var(--sl-ink-3);
}}
.sl-metarow > * + *::before {{ content: "·"; margin-inline: 10px; color: var(--sl-ink-3); }}
.sl-metarow b {{ color: var(--sl-ink); font-weight: 600; }}
.sl-metarow .warn, .sl-metarow .warn b {{ color: var(--sl-warn-ink); }}

/* ---------- panels ---------- */
.sl-card {{
  background: var(--sl-raised);
  border: 1.5px solid var(--sl-ink);
  border-radius: 20px;
  padding: 22px 24px 24px;
  width: 100%;
  min-width: 0;
}}
/* "nothing here (yet)": dashed frame on hatching */
.sl-empty {{
  border: 1.5px dashed var(--sl-line-2); border-radius: 20px; padding: 36px 40px;
  display: grid; grid-template-columns: minmax(0, 440px) minmax(0, 1fr); gap: 16px 48px; align-items: center;
}}
@media (max-width: 1100px) {{ .sl-empty {{ grid-template-columns: minmax(0, 1fr); }} }}
.sl-doodle {{ display: block; width: 100%; height: auto; }}

/* live values: small tiles */
.sl-tile {{
  display: flex; flex-direction: column; gap: 2px; min-width: 0;
  padding: 10px 14px; border: 1.5px solid var(--sl-line); border-radius: 10px; background: var(--sl-page);
}}
.sl-stat-label {{
  font-family: var(--sl-font-mono); font-size: 10px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--sl-ink-3);
}}
.sl-stat-value {{
  font-family: var(--sl-font-mono); font-size: 21px; font-weight: 500;
  letter-spacing: -.02em; line-height: 1.25; color: var(--sl-ink);
}}
.sl-stat-unit {{ font-size: 12px; color: var(--sl-ink-3); margin-left: 6px; }}

/* status pills: mono uppercase, coloured border and soft fill */
.sl-pill {{
  display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; line-height: 1.5;
  border: 1.5px solid; border-radius: 4px; padding: 1px 7px;
  font-family: var(--sl-font-mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase;
}}
.sl-pill-ok {{ background: var(--sl-ok-soft); color: var(--sl-ok); border-color: var(--sl-ok); }}
.sl-pill-warn {{ background: var(--sl-warn-soft); color: var(--sl-warn-ink); border-color: var(--sl-warn); }}
.sl-pill-bad {{ background: var(--sl-bad); color: #fff; border-color: var(--sl-bad); }}
.sl-pill-info {{ background: var(--sl-sunken); color: var(--sl-ink-2); border-color: var(--sl-line-2); }}
.sl-pill-accent {{ background: var(--sl-accent-soft); color: var(--sl-accent-ink); border-color: var(--sl-accent); }}
.sl-pill-neutral {{ background: transparent; color: var(--sl-ink-3); border-color: var(--sl-line-2); border-style: dashed; }}

/* EEPROM marker in the register list */
.sl-tag-eeprom {{
  font-family: var(--sl-font-mono); font-size: 9.5px; letter-spacing: .08em; line-height: 1.5;
  padding: 0 5px; border-radius: 3px; border: 1px solid var(--sl-warn);
  background: var(--sl-warn-soft); color: var(--sl-warn-ink);
}}

/* info banner */
.sl-note {{
  background: var(--sl-sunken); color: var(--sl-ink-2); border: 1.5px solid var(--sl-line-2);
  border-radius: 10px; padding: 12px 16px; font-size: 13.5px;
}}
.sl-note .q-icon {{ color: var(--sl-ink); }}
.sl-text-warn {{ color: var(--sl-warn-ink); }}

/* ---------- sidebar ---------- */
.q-drawer {{ background: var(--sl-page); }}
.q-drawer--bordered.q-drawer--left {{ border-right: 1.5px solid var(--sl-ink); }}
.sl-brand {{
  font-family: var(--sl-font-heading); font-size: 27px; font-weight: 800; line-height: 1;
  letter-spacing: -.045em; color: var(--sl-ink);
}}
.sl-brand i {{ font-style: normal; color: var(--sl-accent); }}
.sl-side-label {{
  font-family: var(--sl-font-mono); font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--sl-ink-3); padding: 0 4px;
}}
.sl-count {{
  font-family: var(--sl-font-mono); font-size: 10.5px; color: var(--sl-ink-3);
  border: 1.5px solid var(--sl-line-2); border-radius: 4px; padding: 0 6px; line-height: 1.5;
}}
.sl-device {{
  display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 8px 14px; border-radius: 12px; cursor: pointer; border: 1.5px solid transparent;
  transition: background .12s ease;
}}
.sl-device:hover {{ background: var(--sl-sunken); }}
.sl-device-selected, .sl-device-selected:hover {{ background: var(--sl-ink); color: var(--sl-page); }}
.sl-device-selected .sl-muted {{ color: rgba(246, 245, 242, .62); }}
.sl-device-off {{ background: {HATCH}; border: 1.5px dashed var(--sl-line-2); }}
.sl-device-off .sl-device-name {{ color: var(--sl-ink-3); }}
.sl-device-name {{ font-weight: 600; line-height: 1.2; }}
.sl-dot {{ width: 8px; height: 8px; border-radius: 50%; flex: none; }}
.sl-dot-ok {{ background: var(--sl-ok); }}
.sl-dot-warn {{ background: var(--sl-warn); }}
.sl-dot-off {{ background: transparent; border: 1.5px solid var(--sl-ink-3); }}
.sl-device-selected .sl-dot-ok {{ background: #7FCBA4; }}
.sl-nav {{
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 8px 14px; border-radius: 999px; cursor: pointer; font-weight: 500; color: var(--sl-ink);
}}
.sl-nav:hover {{ background: var(--sl-sunken); }}
.sl-nav-selected, .sl-nav-selected:hover {{ background: var(--sl-ink); color: var(--sl-page); }}

/* connection box (a banner) */
.sl-conn {{
  border-radius: 10px; padding: 10px 12px; font-size: 13.5px; font-weight: 600; width: 100%;
  border: 1.5px solid;
}}
.sl-conn-ok {{ background: var(--sl-ok-soft); color: var(--sl-ok); border-color: var(--sl-ok); }}
.sl-conn-lost {{ background: var(--sl-bad-soft); color: var(--sl-bad-ink); border: 2.5px solid var(--sl-bad); }}

/* ---------- settings ---------- */
.sl-expansion {{ border: 1.5px solid var(--sl-line-2); border-radius: 12px; background: var(--sl-raised); overflow: hidden; }}
.sl-expansion .q-expansion-item__container > .q-item {{ padding: 10px 16px; }}
.q-expansion-item .q-item__section--avatar .q-icon {{ color: var(--sl-ink); }}
.q-expansion-item .q-item__label {{ font-family: var(--sl-font-heading); font-weight: 700; font-size: 15.5px; letter-spacing: -.01em; }}
.q-expansion-item .q-item__label--caption {{
  font-family: var(--sl-font-mono); font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase;
  color: var(--sl-ink-3); font-weight: 400;
}}
.sl-reg-row {{ border-top: 1px solid var(--sl-line); padding: 10px 0; }}
.sl-reg-row:first-child {{ border-top: none; }}

/* ---------- docs ---------- */
.sl-tabs .q-tabs__content {{ gap: 6px; }}
.sl-tabs .q-tab {{
  border: 1.5px solid var(--sl-ink); border-radius: 999px; min-height: 36px; padding: 0 16px; color: var(--sl-ink);
}}
.sl-tabs .q-tab__label {{ font-size: 14.5px; font-weight: 500; }}
.sl-tabs .q-tab--active {{ background: var(--sl-ink); color: var(--sl-page); }}
.sl-tabs .q-tab__indicator, .sl-tabs .q-focus-helper {{ display: none; }}
.sl-signature {{
  font-family: var(--sl-font-mono); font-size: 13.5px; font-weight: 600; color: var(--sl-accent-ink);
}}
/* every docs tab: table of contents left (stays in view), content in the remaining width */
.sl-docs-panels, .sl-docs-panels .q-panel-parent, .sl-docs-panels .q-panel {{ overflow: visible !important; }}
.sl-docs-grid {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 24px; align-items: start; }}
@media (min-width: 1024px) {{ .sl-docs-grid {{ grid-template-columns: 236px minmax(0, 1fr); }} }}
.sl-toc {{ position: sticky; top: 24px; max-height: calc(100vh - 48px); overflow-y: auto; padding: 4px 0 12px; }}
@media (max-width: 1023px) {{ .sl-toc {{ position: static; max-height: none; }} }}
.sl-toc > * {{ flex-shrink: 0; align-self: stretch; }}   /* a column with max-height would squeeze its items */
.sl-toc a {{ text-decoration: none; }}
.sl-toc-head {{
  display: block; padding: 6px 14px; margin-top: 8px; border-radius: 999px;
  font-family: var(--sl-font-heading); font-weight: 700; font-size: 15px; letter-spacing: -.01em;
  color: var(--sl-ink) !important;
}}
.sl-toc-head:first-of-type {{ margin-top: 0; }}
.sl-toc-item {{
  display: block; margin-left: 14px; padding: 3px 12px; border-left: 1.5px solid var(--sl-line);
  font-family: var(--sl-font-mono); font-size: 12px; color: var(--sl-ink-2) !important;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.sl-toc-head:hover, .sl-toc-item:hover {{ background: var(--sl-sunken); color: var(--sl-accent-ink) !important; }}
.sl-toc-item:hover {{ border-left-color: var(--sl-ink); border-radius: 0 6px 6px 0; }}
.sl-toc-note {{ padding: 0 14px; font-family: var(--sl-font-mono); font-size: 11px; color: var(--sl-ink-3); }}
.sl-anchor {{ scroll-margin-top: 24px; }}
html {{ scroll-behavior: smooth; }}

/* API entry: signature, below it the description on an indent line */
.sl-api-entry {{
  display: flex; flex-direction: column; gap: 8px; align-self: stretch;
  border-top: 1px solid var(--sl-line); padding: 14px 0 4px; margin-top: 6px;
}}
.sl-api-entry .sl-signature {{ overflow-wrap: anywhere; }}
.sl-docstring {{
  white-space: pre-wrap; font-family: var(--sl-font-mono);
  font-size: 12.5px; line-height: 1.6; color: var(--sl-ink-2);
  border-left: 1.5px solid var(--sl-line); padding: 2px 0 2px 16px; margin-left: 2px;
}}
/* running text in the guides: full-width panel, but lines short enough to read */
.sl-prose p, .sl-prose li, .sl-prose h1, .sl-prose h2, .sl-prose h3 {{ max-width: 88ch; }}
.sl-docs {{ font-size: 15px; }}
.sl-docs h1, .sl-docs h2, .sl-docs h3 {{ font-family: var(--sl-font-heading); color: var(--sl-ink); }}
.sl-docs h1 {{ font-size: 38px; font-weight: 800; letter-spacing: -.035em; line-height: 1; margin: 0 0 16px; }}
.sl-docs h2 {{ font-size: 23px; font-weight: 700; letter-spacing: -.02em; margin: 32px 0 8px; }}
.sl-docs h3 {{ font-size: 18px; font-weight: 700; letter-spacing: -.015em; margin: 22px 0 6px; }}
.sl-docs p, .sl-docs li {{ line-height: 1.6; color: var(--sl-ink); }}
.sl-docs a {{ color: var(--sl-accent-ink); text-underline-offset: 3px; }}
.sl-docs code {{
  font-family: var(--sl-font-mono); font-size: .82em;
  background: var(--sl-sunken); border: 1px solid var(--sl-line); padding: 0 4px; border-radius: 3px;
}}
.sl-docs pre code {{ background: transparent; border: none; padding: 0; font-size: 12.5px; }}
.sl-docs pre {{
  background: var(--sl-page); color: var(--sl-ink); border: 1.5px solid var(--sl-line-2);
  padding: 14px 16px; border-radius: 12px; overflow-x: auto; line-height: 1.66;
}}
.sl-docs table {{ border-collapse: collapse; margin: 10px 0; font-size: 14px; }}
.sl-docs th {{
  font-family: var(--sl-font-mono); font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase;
  font-weight: 400; color: var(--sl-ink-3); border-bottom: 1.5px solid var(--sl-ink);
}}
.sl-docs th, .sl-docs td {{ padding: 8px 12px; text-align: left; }}
.sl-docs td {{ border-bottom: 1px solid var(--sl-line); }}
.q-table__card {{ background: transparent; }}
.q-table thead th {{
  font-family: var(--sl-font-mono); font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase;
  font-weight: 400; color: var(--sl-ink-3); border-bottom: 1.5px solid var(--sl-ink);
}}
.q-table tbody td {{ border-color: var(--sl-line); }}
.nicegui-code {{ border-radius: 12px; border: 1.5px solid var(--sl-line-2); background: var(--sl-page); }}
.nicegui-code, .nicegui-code code {{ font-family: var(--sl-font-mono); }}

/* ---------- logo stamp ---------- */
/* The TUM MiMed logo, pressed into the paper. On every page it sits at the
   top centre like branded paper: absolutely placed, so it takes no space.
   (.sl-letterhead is the page column.) */
.sl-letterhead {{ position: relative; }}
.sl-letterhead > .sl-stamp {{ position: absolute; top: 8px; left: 50%; transform: translateX(-50%); }}
/* The stamp itself: a darker
   fill with a light lower edge and a dark upper edge (two drop shadows). */
.sl-stamp {{
  display: inline-block; flex: none; line-height: 0; cursor: pointer;
  filter: drop-shadow(0 1px 0 rgba(255, 255, 255, .95)) drop-shadow(0 -1px 0 rgba(23, 22, 20, .16));
}}
.sl-stamp i {{
  display: block; width: 132px; aspect-ratio: 193.098 / 30.834;
  background: linear-gradient(180deg, rgba(23, 22, 20, .13), rgba(23, 22, 20, .07));
  -webkit-mask: url("/servoscope-assets/logo.svg") center / contain no-repeat;
          mask: url("/servoscope-assets/logo.svg") center / contain no-repeat;
}}
.sl-stamp:hover i {{ background: linear-gradient(180deg, rgba(23, 22, 20, .24), rgba(23, 22, 20, .14)); }}
.sl-stamp:focus-visible {{ outline: 2px solid var(--sl-accent); outline-offset: 4px; border-radius: 4px; }}
"""

# ui.toggle props for a segmented choice: separate ink pills, the chosen one inverted.
# Add the class "sl-seg" (and "sl-seg-sm" for the small version) to the toggle.
TOGGLE_PROPS = "no-caps unelevated color=white text-color=dark toggle-color=dark toggle-text-color=white"

# Shared look for every echart.
CHART_TEXT = {"fontFamily": FONT_TEXT, "color": INK_3, "fontSize": 11}
CHART_AXIS_LABEL = {"fontFamily": FONT_MONO, "color": INK_3, "fontSize": 11}
CHART_TOOLTIP = {
    "trigger": "axis",
    "backgroundColor": RAISED,
    "borderColor": INK,
    "borderWidth": 1.5,
    "padding": [8, 12],
    "textStyle": {"fontFamily": FONT_MONO, "fontSize": 12, "color": INK},
    "extraCssText": "border-radius: 10px; box-shadow: 4px 4px 0 rgba(23,22,20,.09);",
    "axisPointer": {"lineStyle": {"color": INK_3, "width": 1}},
}


def apply_theme() -> None:
    """Colours, fonts and CSS of ServoScope. Call once per page, before building it."""
    ui.colors(
        primary=ACCENT,
        secondary=MIMED_YELLOW,
        accent=ACCENT,
        positive=OK,
        negative=BAD,
        warning=WARN,
        info=ACCENT_INK,
        dark=INK,
    )
    ui.add_head_html(FONTS_LINK)
    ui.add_css(CSS)


def card() -> ui.column:
    """A panel: white paper with an ink frame. Use as a context manager: with card(): ..."""
    return ui.column().classes("sl-card gap-4")


def pill(text: str, kind: str = "info", title: str = "") -> str:
    """HTML of a status pill. kind: ok, warn, bad, info, accent, neutral."""
    title_attr = f' title="{title}"' if title else ""
    return f'<span class="sl-pill sl-pill-{kind}"{title_attr}>{text}</span>'


def page_head(kicker: str, title: str) -> tuple[ui.column, ui.row]:
    """Kicker + big title. Returns (left, right): add a meta row to `left`, pills or buttons to `right`."""
    with ui.row().classes("w-full items-end justify-between gap-x-8 gap-y-4 pt-2 pb-2 no-wrap"):
        with ui.column().classes("gap-3 min-w-0") as left:
            ui.label(kicker).classes("sl-kicker")
            ui.label(title).classes("sl-h1")
        right = ui.row().classes("items-center gap-2 pb-1")
    return left, right


def logo_stamp() -> None:
    """The TUM MiMed logo, pressed into the paper. Links to the chair's website."""
    with ui.element("a").classes("sl-stamp") \
            .props(f'href="{MIMED_URL}" target="_blank" rel="noopener" title="TUM MiMed" aria-label="TUM MiMed website"'):
        ui.element("i")
