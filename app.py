"""
app.py — Streamlit UI for the Credit Card Dashboard.

Layout, widgets, and rendering only.
All business logic is delegated to analytics.py.
"""

import base64
import re
from io import BytesIO
from pathlib import Path

import json

import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from analytics import (
    get_mock_data,
    compute_kpis,
    get_category_breakdown,
    get_top_merchants,
    get_insights,
)
from parser import parse_pdf

# ── Theme palettes ───────────────────────────────────────────────────────────────

# Months with fewer than this many transactions are treated as carry-over
# artifacts and hidden from the month filter (but still present in the data).
MIN_MONTH_TRANSACTIONS: int = 3

# ── Billing-month detection ───────────────────────────────────────────────────

_HEBREW_MONTHS: dict[str, int] = {
    'ינואר': 1,  'פברואר': 2,  'מרץ': 3,    'אפריל': 4,
    'מאי':   5,  'יוני':   6,  'יולי': 7,   'אוגוסט': 8,
    'ספטמבר': 9, 'אוקטובר': 10,'נובמבר': 11, 'דצמבר': 12,
}


def _parse_billing_month(filename: str) -> pd.Period | None:
    """
    Extract the billing month from a PDF filename.

    Supports:
      - Numeric:  "כאל 01-26.pdf"           → January 2026   (MM-YY)
      - Hebrew:   "ישראכרט פברואר 26.pdf"   → February 2026
    Returns None if the filename contains no recognisable month.
    """
    stem = Path(filename).stem

    # Pattern 1: MM-YY  e.g. "01-26"
    m = re.search(r'\b(\d{2})-(\d{2})\b', stem)
    if m:
        month, year = int(m.group(1)), 2000 + int(m.group(2))
        if 1 <= month <= 12:
            return pd.Period(year=year, month=month, freq='M')

    # Pattern 2: Hebrew month name + 2-digit year  e.g. "פברואר 26"
    for heb_name, month_num in _HEBREW_MONTHS.items():
        if heb_name in stem:
            yr_m = re.search(r'\b(\d{2})\b', stem)
            if yr_m:
                return pd.Period(year=2000 + int(yr_m.group(1)),
                                 month=month_num, freq='M')
    return None

CHART_COLORS: list[str] = [
    "#f2a900", "#3b82f6", "#10b981", "#f43f5e",
    "#8b5cf6", "#fb923c", "#06b6d4", "#84cc16",
]

_DARK = dict(
    bg="#070c18", bg_card="#0d1422", border="#1c2d4a", border_hi="#243550",
    accent="#f2a900", accent_dim="rgba(242,169,0,0.12)",
    blue="#3b82f6", green="#10b981", red="#f43f5e", warn="#f59e0b",
    tx="#e2e8f4", tx2="#7a93b8", tx3="#3d5270",
    plotly_paper="#070c18", plotly_plot="#0a0f1e",
    plotly_grid="#1c2d4a", plotly_text="#7a93b8", plotly_title="#e2e8f4",
)
_LIGHT = dict(
    bg="#f0f4fa", bg_card="#ffffff", border="#d1dce8", border_hi="#b0c0d4",
    accent="#c98f00", accent_dim="rgba(201,143,0,0.14)",
    blue="#2563eb", green="#059669", red="#e11d48", warn="#d97706",
    tx="#0f1b2d", tx2="#4a6480", tx3="#96aabf",
    plotly_paper="#f0f4fa", plotly_plot="#ffffff",
    plotly_grid="#d1dce8", plotly_text="#4a6480", plotly_title="#0f1b2d",
)


def _t() -> dict:
    """Return the active theme palette dict."""
    return _LIGHT if st.session_state.get("theme") == "light" else _DARK

HEBREW_MONTHS: dict[int, str] = {
    1: "ינואר",  2: "פברואר", 3: "מרץ",     4: "אפריל",
    5: "מאי",    6: "יוני",   7: "יולי",    8: "אוגוסט",
    9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר",
}

# ── CSS ──────────────────────────────────────────────────────────────────────────

_CSS_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');"

_CSS_STATIC = """

/* ── Global ── */
html, body, .stApp {
    background: var(--bg) !important;
    font-family: 'Heebo', sans-serif !important;
    color: var(--tx) !important;
}
.main .block-container {
    padding: 1.5rem 2rem 4rem !important;
    max-width: 1400px !important;
    direction: rtl;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: var(--bg-card) !important;
    border-left: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { direction: rtl; }
section[data-testid="stSidebar"] label {
    font-size: 0.85rem !important;
    font-weight: 700 !important;
    color: var(--tx2) !important;
    text-transform: uppercase;
    letter-spacing: 0.07em;
}

/* ── Header ── */
.hdr {
    padding: 1.5rem 0 1.2rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1.2rem;
}
.hdr-logo   { flex-shrink: 0; }
.hdr-logo img { height: 80px; display: block; }
.hdr-text   { flex: 1; text-align: center; }
.hdr-title  { font-size: 2.2rem; font-weight: 800; color: var(--tx); letter-spacing: -0.02em; margin: 0 0 0.25rem; }
.hdr-title span { color: var(--accent); }
.hdr-sub    { font-size: 1rem; color: var(--tx2); margin: 0; }

/* ── KPI Row ── */
.kpi-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 0.25rem;
}
.kpi {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.4rem 1.6rem 1.2rem;
    position: relative;
    overflow: hidden;
    transition: border-color .2s;
}
.kpi:hover { border-color: var(--border-hi); }
.kpi::after {
    content: ''; position: absolute;
    top: 0; right: 0;
    width: 4px; height: 100%;
    border-radius: 0 10px 10px 0;
}
.kpi.g::after { background: var(--accent); }
.kpi.b::after { background: var(--blue); }
.kpi.e::after { background: var(--green); }
.kpi-ico  { font-size: 1.5rem; opacity: 0.18; position: absolute; left: 1.2rem; top: 1.2rem; }
.kpi-lbl  { font-size: 1rem; font-weight: 700; color: var(--tx2); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem; }
.kpi-val  { font-family: 'IBM Plex Mono', monospace; font-size: 2.8rem; font-weight: 500; color: var(--tx); direction: ltr; text-align: right; line-height: 1; }
.kpi-val small { font-size: 1.5rem; color: var(--tx2); }
.kpi-hint { font-size: 1rem; color: var(--tx3); margin-top: 0.35rem; }

/* ── Section Dividers ── */
.sec {
    font-size: 0.82rem; font-weight: 700; color: var(--tx2);
    text-transform: uppercase; letter-spacing: 0.1em;
    margin: 1.8rem 0 0.9rem;
    display: flex; align-items: center; gap: 0.5rem;
}
.sec::after { content: ''; flex: 1; height: 1px; background: var(--border); }

/* ── Insights ── */
.iw { display: flex; flex-direction: column; gap: 0.5rem; }
.ic {
    display: flex; align-items: flex-start; gap: 0.7rem;
    padding: 0.9rem 1.2rem; border-radius: 8px;
    font-size: 0.97rem; line-height: 1.6;
    border-right: 3px solid;
}
.ic.high      { background: rgba(244,63,94,.07);   border-color: var(--red);    color: var(--red); }
.ic.medium    { background: rgba(245,158,11,.07); border-color: var(--warn);   color: var(--warn); }
.ic.recurring { background: rgba(14,165,233,.07);  border-color: var(--blue);   color: var(--blue); }
.ic.onetime   { background: rgba(52,211,153,.07);  border-color: var(--green);  color: var(--green); }
.insight-sub {
    font-size: 0.78rem; font-weight: 700; color: var(--tx3);
    text-transform: uppercase; letter-spacing: 0.1em;
    margin: 0.9rem 0 0.4rem;
}

/* ── Category chips ── */
.chip-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 0.8rem; justify-content: flex-end; }
/* Streamlit button overrides for chip style */
[data-testid="stHorizontalBlock"] .stButton button {
    border-radius: 20px !important;
    padding: 0.2rem 0.7rem !important;
    font-size: 0.82rem !important;
    height: auto !important;
    min-height: 0 !important;
}

/* ── Search Input ── */
.stTextInput input {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--tx) !important;
    direction: rtl;
    font-size: 1rem !important;
    padding: 0.6rem 0.9rem !important;
}
.stTextInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-dim) !important;
}
.stTextInput label { color: var(--tx2) !important; font-size: 0.9rem !important; }

/* ── Dataframe tables ── */
[data-testid="stDataFrame"] .ag-cell,
[data-testid="stDataFrame"] .ag-header-cell-text {
    font-size: 1.35rem !important;
    font-family: 'Heebo', sans-serif !important;
}
[data-testid="stDataFrame"] .ag-header-cell-text {
    font-size: 1.2rem !important;
    font-weight: 700 !important;
}
[data-testid="stDataFrame"] .ag-cell {
    line-height: 2.4 !important;
}

/* ── Plotly modebar (hover toolbar) ── */
.modebar-container {
    z-index: 9999 !important;
    background: var(--bg-card) !important;
    border-radius: 6px !important;
    border: 1px solid var(--border) !important;
    padding: 2px 4px !important;
}
.modebar-btn path { fill: var(--tx2) !important; }
.modebar-btn:hover path { fill: var(--accent) !important; }
.modebar-btn.active path { fill: var(--accent) !important; }

/* ── Misc ── */
hr { border-color: var(--border) !important; margin: 1.2rem 0 !important; }
::-webkit-scrollbar            { width: 5px; height: 5px; }
::-webkit-scrollbar-track      { background: var(--bg); }
::-webkit-scrollbar-thumb      { background: var(--border-hi); border-radius: 3px; }
"""


def inject_css() -> None:
    """Inject theme-aware RTL CSS into the Streamlit page."""
    p = _t()
    root = (
        f":root {{"
        f"--bg:{p['bg']};--bg-card:{p['bg_card']};--border:{p['border']};"
        f"--border-hi:{p['border_hi']};--accent:{p['accent']};"
        f"--accent-dim:{p['accent_dim']};--blue:{p['blue']};--green:{p['green']};"
        f"--red:{p['red']};--warn:{p['warn']};--tx:{p['tx']};"
        f"--tx2:{p['tx2']};--tx3:{p['tx3']};}}"
    )
    css = _CSS_IMPORT + root + _CSS_STATIC
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _logo_b64() -> str:
    """Return the theme-appropriate MARCAI logo as a base64 data-URI."""
    is_light = st.session_state.get("theme") == "light"
    filename = "MarcAI Logo Black.png" if is_light else "MarcAI Logo White.png"
    logo_path = Path(__file__).parent / filename
    if not logo_path.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode()


def _period_to_hebrew(period_str: str) -> str:
    """Convert 'YYYY-MM' string to a Hebrew month label (e.g. 'נובמבר 2025')."""
    p = pd.Period(period_str)
    return f"{HEBREW_MONTHS.get(p.month, str(p.month))} {p.year}"


def _dark_layout(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply the current theme's Plotly styling to a figure."""
    p = _t()
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(color=p["plotly_title"], size=18, family="Heebo"),
            x=0, xanchor="left",
            pad=dict(l=6),
        ),
        paper_bgcolor=p["plotly_paper"],
        plot_bgcolor=p["plotly_plot"],
        font=dict(color=p["plotly_text"], family="Heebo", size=16),
        margin=dict(t=52, b=10, l=10, r=90),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=p["plotly_text"], size=15)),
        xaxis=dict(gridcolor=p["plotly_grid"], color=p["plotly_text"], linecolor=p["plotly_grid"], tickfont=dict(size=15)),
        yaxis=dict(gridcolor=p["plotly_grid"], color=p["plotly_text"], linecolor=p["plotly_grid"], tickfont=dict(size=15)),
    )
    return fig


# ── Render Components ────────────────────────────────────────────────────────────

def render_kpis(kpis: dict) -> None:
    """Render the three KPI metric cards as custom HTML."""
    total = kpis["total_spend"]
    avg   = kpis["monthly_avg"]
    count = kpis["transaction_count"]
    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi g">
        <div class="kpi-ico">💰</div>
        <div class="kpi-lbl">סה"כ הוצאות</div>
        <div class="kpi-val"><small>₪</small>{total:,.0f}</div>
        <div class="kpi-hint">בתקופה הנבחרת</div>
      </div>
      <div class="kpi b">
        <div class="kpi-ico">📅</div>
        <div class="kpi-lbl">ממוצע חודשי</div>
        <div class="kpi-val"><small>₪</small>{avg:,.0f}</div>
        <div class="kpi-hint">לחודש</div>
      </div>
      <div class="kpi e">
        <div class="kpi-ico">🧾</div>
        <div class="kpi-lbl">עסקאות</div>
        <div class="kpi-val">{count:,}</div>
        <div class="kpi-hint">עסקאות בסה"כ</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_pie_chart(df: pd.DataFrame, active_cat: str | None = None,
                     cat_df: pd.DataFrame | None = None) -> None:
    """Render donut pie chart with pull highlight on the active category."""
    if cat_df is None:
        cat_df = _pie_cat_df(df)

    pull_vals = [0.08 if r["category"] == active_cat else 0 for _, r in cat_df.iterrows()]

    fig = px.pie(
        cat_df,
        values="total",
        names="category",
        color_discrete_sequence=CHART_COLORS,
        hole=0.52,
    )
    fig.update_traces(
        pull=pull_vals,
        textposition="inside",
        textinfo="percent",
        insidetextorientation="radial",
        hovertemplate="<b>%{label}</b><br>₪%{value:,.0f}<br>%{percent}<extra></extra>",
        textfont_size=13,
    )
    fig = _dark_layout(fig, "לפי קטגוריה")
    p = _t()
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.02, xanchor="left",
            y=0.5, yanchor="middle",
            font=dict(size=13, color=p["plotly_text"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=460,
        margin=dict(t=52, b=20, l=10, r=160),
        annotations=[dict(
            text=f"₪{df['amount'].sum():,.0f}",
            x=0.5, y=0.5,
            font=dict(size=22, color=p["plotly_title"], family="IBM Plex Mono"),
            showarrow=False,
        )],
    )
    st.plotly_chart(fig, use_container_width=True)


def _pie_cat_df(df: pd.DataFrame) -> pd.DataFrame:
    """Build the same category DataFrame used by render_pie_chart (with אחר merging)."""
    cat_df = get_category_breakdown(df)
    total = cat_df["total"].sum()
    threshold = total * 0.02
    small = cat_df[cat_df["total"] < threshold]
    if not small.empty:
        other_row = {"category": "אחר", "total": small["total"].sum(), "count": small["count"].sum()}
        cat_df = pd.concat(
            [cat_df[cat_df["total"] >= threshold], pd.DataFrame([other_row])],
            ignore_index=True,
        ).sort_values("total", ascending=False).reset_index(drop=True)
    return cat_df


def get_category_color_map(cat_df: pd.DataFrame) -> dict[str, str]:
    """Return the category → hex color mapping matching the pie chart's assignment.

    px.pie with color_discrete_sequence assigns CHART_COLORS[i] to the category
    at row i of the dataframe (first-occurrence order). We replicate that here,
    preserving the "אחר" slot so subsequent color indices stay in sync.
    """
    return {
        row["category"]: CHART_COLORS[i % len(CHART_COLORS)]
        for i, row in cat_df.iterrows()
        if row["category"] != "אחר"
    }


def _inject_chip_colors(color_map: dict[str, str]) -> None:
    """Inject JS that applies pie-chart colors to chip buttons by matching button text.

    Uses MutationObserver on the parent document so it works even when buttons
    haven't fully rendered yet at script execution time. Guards against stacking
    multiple observers by only re-injecting when the color map actually changes.
    """
    import hashlib
    color_hash = hashlib.md5(json.dumps(color_map, sort_keys=True).encode()).hexdigest()
    if st.session_state.get("_chip_colors_hash") == color_hash:
        return
    st.session_state["_chip_colors_hash"] = color_hash

    colors_json = json.dumps(color_map)
    script = f"""
    <script>
    (function() {{
        const colors = {colors_json};

        function applyColors() {{
            try {{
                const doc = window.parent.document;
                doc.querySelectorAll('button').forEach(btn => {{
                    // Get raw text from <p> child or button itself
                    const rawText = (btn.querySelector('p') || btn).textContent.trim();
                    const isActive = rawText.startsWith('\\u2713');  // ✓
                    const label   = rawText.replace(/^\\u2713\\s*/, '').trim();
                    const color   = colors[label];
                    if (!color) return;
                    btn.style.setProperty('background',    isActive ? color : color + '28', 'important');
                    btn.style.setProperty('border-color',  color, 'important');
                    btn.style.setProperty('color',         isActive ? '#ffffff' : color, 'important');
                    btn.style.setProperty('border-radius', '20px', 'important');
                    btn.style.setProperty('font-weight',   '600', 'important');
                }});
            }} catch(e) {{}}
        }}

        // Fire immediately and on a schedule
        [0, 100, 300, 700, 1500].forEach(t => setTimeout(applyColors, t));

        // Also re-apply on every DOM mutation (Streamlit React re-renders buttons)
        try {{
            const obs = new MutationObserver(applyColors);
            obs.observe(window.parent.document.body, {{childList: true, subtree: true}});
            setTimeout(() => obs.disconnect(), 10000);
        }} catch(e) {{}}
    }})();
    </script>
    """
    components.html(script, height=0, scrolling=False)


def render_category_chips(cats: list[str], active_cat: str | None) -> None:
    """Render clickable category filter chips. Clicking a chip sets/clears the filter."""
    n_cols = min(len(cats), 5)
    for row_start in range(0, len(cats), n_cols):
        row_cats = cats[row_start: row_start + n_cols]
        cols = st.columns(len(row_cats))
        for i, cat in enumerate(row_cats):
            is_active = (cat == active_cat)
            if cols[i].button(
                f"✓ {cat}" if is_active else cat,
                key=f"chip_{cat}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state["chart_filter_cat"] = None if is_active else cat
                st.rerun()


def render_merchants_chart(df: pd.DataFrame, active_cat: str | None = None) -> None:
    """Render horizontal bar chart of top merchants by spend.

    If active_cat is set, filters merchants to that category only.
    """
    df_src = df[df["category"] == active_cat] if active_cat else df
    merchant_df = get_top_merchants(df_src, n=8)
    title = f"ספקים — {active_cat}" if active_cat else "ספקים מובילים"
    fig = go.Figure(go.Bar(
        x=merchant_df["total"],
        y=merchant_df["merchant"],
        orientation="h",
        marker=dict(color=CHART_COLORS[0], opacity=0.82, line=dict(width=0)),
        hovertemplate="<b>%{y}</b><br>₪%{x:,.0f}<extra></extra>",
        text=[f"₪{v:,.0f}" for v in merchant_df["total"]],
        textposition="inside",
        insidetextanchor="end",
        textfont=dict(color="#ffffff", size=15),
    ))
    fig = _dark_layout(fig, title)
    fig.update_layout(
        height=440,
        xaxis=dict(visible=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=14)),
        bargap=0.3,
        margin=dict(t=52, b=10, l=10, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_anomalies(df: pd.DataFrame) -> None:
    """Render recurring expenses, one-time purchases, and anomaly alerts."""
    insights = get_insights(df)
    recurring = insights["recurring"]
    one_time  = insights["one_time"]
    alerts    = insights["alerts"]

    has_content = recurring or one_time or alerts
    if not has_content:
        st.caption("לא זוהו תובנות בתקופה הנבחרת.")
        return

    html = '<div class="iw">'

    # ── Recurring expenses ──
    if recurring:
        html += '<div class="insight-sub">🔁 הוצאות קבועות</div>'
        for r in recurring:
            html += (
                f'<div class="ic recurring">'
                f'<span>🔁</span>'
                f'<span><b>{r["merchant"]}</b> — ממוצע ₪{r["avg"]:,.0f} לחודש'
                f' &nbsp;·&nbsp; {r["months"]} חודשים</span>'
                f'</div>'
            )

    # ── One-time purchases ──
    if one_time:
        html += '<div class="insight-sub">⚡ הוצאות חד פעמיות</div>'
        for o in one_time:
            html += (
                f'<div class="ic onetime">'
                f'<span>⚡</span>'
                f'<span><b>{o["merchant"]}</b> — ₪{o["amount"]:,.0f}'
                f' &nbsp;·&nbsp; {o["category"]}</span>'
                f'</div>'
            )

    # ── Alerts ──
    if alerts:
        html += '<div class="insight-sub">🚨 חריגות</div>'
        for a in alerts:
            icon = "🚨" if a["severity"] == "high" else "⚠️"
            html += (
                f'<div class="ic {a["severity"]}">'
                f'<span>{icon}</span><span>{a["message"]}</span>'
                f'</div>'
            )

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_transactions_table(df: pd.DataFrame) -> None:
    """Render the searchable, sortable full transactions table."""
    search = st.text_input("🔍 חיפוש לפי שם ספק", placeholder="לדוגמה: שופרסל, ארומה...")

    has_installments = "installment" in df.columns and df["installment"].astype(bool).any()
    cols = ["date", "merchant", "category", "amount"]
    if has_installments:
        cols.append("installment")

    display = df[cols].copy()
    display["date"] = display["date"].dt.strftime("%d/%m/%Y")
    rename_map = {
        "date":     "תאריך",
        "merchant": "בית עסק",
        "category": "קטגוריה",
        "amount":   "סכום (₪)",
    }
    if has_installments:
        rename_map["installment"] = "תשלומים"
    display = display.rename(columns=rename_map)

    if search:
        display = display[display["בית עסק"].str.contains(search, na=False)]

    col_config: dict = {"סכום (₪)": st.column_config.NumberColumn(format="₪%.2f")}
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config=col_config,
    )
    st.caption(f"מציג {len(display):,} מתוך {len(df):,} עסקאות")


# ── Upload processing ─────────────────────────────────────────────────────────────

def _process_uploads(files: list) -> tuple[pd.DataFrame | None, list[str]]:
    """Parse uploaded PDF files and return a merged DataFrame.

    Results are cached in session_state by (name, size) to avoid re-parsing
    the same file on every Streamlit re-run.

    Args:
        files: List of Streamlit UploadedFile objects.

    Returns:
        Tuple of (merged DataFrame or None, list of error messages).
    """
    dfs: list[pd.DataFrame] = []
    errors: list[str] = []

    for f in files:
        cache_key = f"pdf_{f.name}_{f.size}"
        if cache_key not in st.session_state:
            try:
                df = parse_pdf(BytesIO(f.getvalue()))
                # Determine billing month: from filename, or fall back to the
                # most frequent transaction month in the PDF.
                billing = _parse_billing_month(f.name)
                if billing is None:
                    billing = df["date"].dt.to_period("M").value_counts().idxmax()
                # Add billing_month column for grouping/filtering.
                # The original 'date' column is kept untouched for display.
                df["billing_month"] = billing
                st.session_state[cache_key] = df
            except ValueError as exc:
                errors.append(f"❌ {f.name}: {exc}")
                st.session_state[cache_key] = None

        cached = st.session_state.get(cache_key)
        if cached is not None:
            dfs.append(cached)

    if not dfs:
        return None, errors

    # Merge all PDFs without per-file date filtering.
    # Carry-over rows (isolated old transactions) are suppressed in the UI by
    # only showing months with >= MIN_MONTH_TRANSACTIONS in the filter list.
    merged = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates(subset=["date", "merchant", "amount"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    return merged, errors


def _reset_filters() -> None:
    """Clear sidebar month and category filter selections."""
    st.session_state.pop("filter_months", None)
    st.session_state.pop("filter_cats", None)


def _render_empty_state() -> None:
    """Render the welcome screen shown before any data is loaded."""
    logo_src = _logo_b64()
    logo_html = (
        f'<img src="{logo_src}" style="height:72px; margin-top:1.2rem;" alt="MARCAI"/>'
        if logo_src else ""
    )
    st.markdown(f"""
    <div style="display:flex; flex-direction:column; align-items:center;
                justify-content:center; min-height:55vh; text-align:center; gap:1.2rem;
                direction:rtl;">
      <div style="font-size:4.5rem;">💳</div>
      <div style="font-size:2.4rem; font-weight:800; color:var(--tx); letter-spacing:-0.02em;">
        דשבורד הוצאות אשראי
      </div>
      <div style="font-size:1.15rem; color:var(--tx2); max-width:480px; line-height:1.8;">
        העלה קובץ PDF של פירוט כרטיס אשראי <b>כאל</b> או <b>ישראכרט</b> מהתפריט הצדדי,
        או לחץ על <b>נתוני הדגמה</b> כדי לראות את הדשבורד בפעולה.
      </div>
      {logo_html}
    </div>
    """, unsafe_allow_html=True)


# ── Main ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point — configures page and orchestrates all dashboard sections."""
    st.set_page_config(
        page_title="דשבורד הוצאות | כרטיס אשראי",
        page_icon="💳",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()

    # Defaults so variables are always bound even if sidebar runs conditionally
    selected_months: list[str] = []
    selected_cats: list[str] = []

    # ── Sidebar ──────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 💳 דשבורד הוצאות")
        is_light = st.session_state.get("theme") == "light"
        if st.button("☀️ מוד בהיר" if not is_light else "🌙 מוד כהה", use_container_width=True):
            st.session_state["theme"] = "light" if not is_light else "dark"
            st.rerun()
        st.divider()

        # File uploader
        uploaded_files = st.file_uploader(
            "העלה קבצי PDF",
            type=["pdf"],
            accept_multiple_files=True,
            help="ניתן להעלות מספר קבצי PDF במקביל",
        )

        # Parse any newly uploaded files
        if uploaded_files:
            df_parsed, parse_errors = _process_uploads(uploaded_files)
            if df_parsed is not None:
                # Reset filters whenever the uploaded file set changes
                uploaded_key = frozenset((f.name, f.size) for f in uploaded_files)
                if st.session_state.get("uploaded_key") != uploaded_key:
                    _reset_filters()
                    st.session_state["uploaded_key"] = uploaded_key
                st.session_state.df_all = df_parsed
                st.session_state.data_source = "pdf"
            for err in parse_errors:
                st.error(err)

        # Demo data button (visible when no PDF data is loaded)
        if st.session_state.get("data_source") != "pdf":
            if st.button("🎲 נתוני הדגמה", use_container_width=True):
                st.session_state.df_all = get_mock_data()
                st.session_state.data_source = "demo"
                _reset_filters()

        # Clear button (visible only when data is present)
        if st.session_state.get("df_all") is not None:
            if st.button("🗑️ נקה נתונים", use_container_width=True):
                st.session_state.clear()
                st.rerun()

        df_all: pd.DataFrame | None = st.session_state.get("df_all")

        # Filters — shown only after data is loaded
        if df_all is not None:
            st.divider()

            month_counts = df_all["billing_month"].value_counts()
            all_periods = sorted(
                [str(m) for m, n in month_counts.items() if n >= MIN_MONTH_TRANSACTIONS],
                reverse=True,
            )
            # key= lets Streamlit persist selections across reruns via session_state.
            # We only set the initial value; after that Streamlit owns the key.
            if "filter_months" not in st.session_state:
                # Default to all visible months (carry-overs already excluded above)
                st.session_state["filter_months"] = all_periods

            col_mlbl, col_mall = st.columns([3, 1])
            col_mlbl.markdown("**חודשים**")
            if col_mall.button("הכל", key="btn_all_months", use_container_width=True):
                st.session_state["filter_months"] = all_periods
            selected_months = st.multiselect(
                "חודשים",
                options=all_periods,
                key="filter_months",
                format_func=_period_to_hebrew,
                label_visibility="collapsed",
            )
            st.divider()

            all_cats = sorted(df_all["category"].unique().tolist())
            if "filter_cats" not in st.session_state:
                st.session_state["filter_cats"] = all_cats

            col_clbl, col_call = st.columns([3, 1])
            col_clbl.markdown("**קטגוריות**")
            if col_call.button("הכל", key="btn_all_cats", use_container_width=True):
                st.session_state["filter_cats"] = all_cats
            selected_cats = st.multiselect(
                "קטגוריות",
                options=all_cats,
                key="filter_cats",
                label_visibility="collapsed",
            )
            st.divider()

            source = "קובץ PDF" if st.session_state.get("data_source") == "pdf" else "נתוני הדגמה"
            n_months_total = df_all["billing_month"].nunique()
            st.caption(f"מקור: {source}")
            st.caption(f"📊 {len(df_all):,} עסקאות | {n_months_total} חודשים בקובץ")
            st.caption("🔒 קבצי PDF לא מועלים ל-GitHub")

    # ── Empty state ───────────────────────────────────────────────────────────────
    df_all = st.session_state.get("df_all")
    if df_all is None:
        _render_empty_state()
        return

    # ── Apply filters ─────────────────────────────────────────────────────────────
    df = df_all.copy()
    if selected_months:
        df = df[df["billing_month"].astype(str).isin(selected_months)]
    if selected_cats:
        df = df[df["category"].isin(selected_cats)]

    # ── Header ────────────────────────────────────────────────────────────────────
    is_demo = st.session_state.get("data_source") == "demo"
    subtitle = "נתוני הדגמה — העלה PDF לנתונים אמיתיים" if is_demo else "ניתוח פירוט כרטיס אשראי"
    logo_src = _logo_b64()
    logo_html = f'<div class="hdr-logo"><img src="{logo_src}" alt="MARCAI"/></div>' if logo_src else ""
    st.markdown(f"""
    <div class="hdr">
      {logo_html}
      <div class="hdr-text">
        <div class="hdr-title">דשבורד <span>הוצאות אשראי</span></div>
        <div class="hdr-sub">{subtitle}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.warning("אין נתונים תואמים לסינון הנבחר.")
        return

    # ── Charts ────────────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">ניתוח הוצאות</div>', unsafe_allow_html=True)
    active_cat: str | None = st.session_state.get("chart_filter_cat")
    pie_cat_df = _pie_cat_df(df)          # compute once — shared by chart + color map
    cat_color_map = get_category_color_map(pie_cat_df)
    col_pie, col_bar = st.columns(2, gap="medium")
    with col_pie:
        render_pie_chart(df, active_cat=active_cat, cat_df=pie_cat_df)
    with col_bar:
        render_merchants_chart(df, active_cat=active_cat)

    cats = sorted(df["category"].unique().tolist())
    render_category_chips(cats, active_cat)
    _inject_chip_colors(cat_color_map)

    # ── Apply chart category filter ───────────────────────────────────────────────
    df_view = df[df["category"] == active_cat].copy() if active_cat else df

    # ── KPIs ──────────────────────────────────────────────────────────────────────
    render_kpis(compute_kpis(df_view))

    # ── Category Summary ──────────────────────────────────────────────────────────
    st.markdown('<div class="sec">סיכום קטגוריות</div>', unsafe_allow_html=True)
    cat_summary = get_category_breakdown(df_view).copy()
    cat_summary.columns = ["קטגוריה", 'סה"כ (₪)', "עסקאות"]
    st.dataframe(
        cat_summary,
        use_container_width=True,
        hide_index=True,
        column_config={'סה"כ (₪)': st.column_config.NumberColumn(format="₪%.2f")},
    )

    # ── Anomalies ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">תובנות וחריגים</div>', unsafe_allow_html=True)
    render_anomalies(df_view)

    # ── Full Transactions Table ───────────────────────────────────────────────────
    st.markdown('<div class="sec">כל העסקאות</div>', unsafe_allow_html=True)
    render_transactions_table(df_view)


if __name__ == "__main__":
    main()
