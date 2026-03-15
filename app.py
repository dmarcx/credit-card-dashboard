"""
app.py — Streamlit UI for the Credit Card Dashboard.

Layout, widgets, and rendering only.
All business logic is delegated to analytics.py.
"""

from io import BytesIO

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from analytics import (
    get_mock_data,
    compute_kpis,
    get_category_breakdown,
    get_top_merchants,
    get_anomalies,
)
from parser import parse_pdf

# ── Chart Theme ──────────────────────────────────────────────────────────────────

CHART_COLORS: list[str] = [
    "#f2a900", "#3b82f6", "#10b981", "#f43f5e",
    "#8b5cf6", "#fb923c", "#06b6d4", "#84cc16",
]

PLOTLY_PAPER_BG = "#070c18"
PLOTLY_PLOT_BG  = "#0a0f1e"
PLOTLY_GRID     = "#1c2d4a"
PLOTLY_TEXT     = "#7a93b8"
PLOTLY_TITLE    = "#e2e8f4"

HEBREW_MONTHS: dict[int, str] = {
    1: "ינואר",  2: "פברואר", 3: "מרץ",     4: "אפריל",
    5: "מאי",    6: "יוני",   7: "יולי",    8: "אוגוסט",
    9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר",
}

# ── CSS ──────────────────────────────────────────────────────────────────────────

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --bg:           #070c18;
    --bg-card:      #0d1422;
    --border:       #1c2d4a;
    --border-hi:    #243550;
    --accent:       #f2a900;
    --accent-dim:   rgba(242,169,0,0.12);
    --blue:         #3b82f6;
    --green:        #10b981;
    --red:          #f43f5e;
    --warn:         #f59e0b;
    --tx:           #e2e8f4;
    --tx2:          #7a93b8;
    --tx3:          #3d5270;
}

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
.hdr        { padding: 1.5rem 0 1.2rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem; }
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
.ic.high   { background: rgba(244,63,94,.07);   border-color: var(--red);  color: #fca5a5; }
.ic.medium { background: rgba(245,158,11,.07); border-color: var(--warn); color: #fcd34d; }

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
    font-size: 1rem !important;
    font-family: 'Heebo', sans-serif !important;
}
[data-testid="stDataFrame"] .ag-cell {
    line-height: 2 !important;
}

/* ── Misc ── */
hr { border-color: var(--border) !important; margin: 1.2rem 0 !important; }
::-webkit-scrollbar            { width: 5px; height: 5px; }
::-webkit-scrollbar-track      { background: var(--bg); }
::-webkit-scrollbar-thumb      { background: var(--border-hi); border-radius: 3px; }
"""


def inject_css() -> None:
    """Inject global dark RTL CSS into the Streamlit page."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _period_to_hebrew(period_str: str) -> str:
    """Convert 'YYYY-MM' string to a Hebrew month label (e.g. 'נובמבר 2025')."""
    p = pd.Period(period_str)
    return f"{HEBREW_MONTHS.get(p.month, str(p.month))} {p.year}"


def _dark_layout(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply the project's dark Plotly theme to a figure."""
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(color=PLOTLY_TITLE, size=18, family="Heebo"),
            x=1, xanchor="right",
        ),
        paper_bgcolor=PLOTLY_PAPER_BG,
        plot_bgcolor=PLOTLY_PLOT_BG,
        font=dict(color=PLOTLY_TEXT, family="Heebo", size=16),
        margin=dict(t=52, b=10, l=10, r=90),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=PLOTLY_TEXT, size=15)),
        xaxis=dict(gridcolor=PLOTLY_GRID, color=PLOTLY_TEXT, linecolor=PLOTLY_GRID, tickfont=dict(size=15)),
        yaxis=dict(gridcolor=PLOTLY_GRID, color=PLOTLY_TEXT, linecolor=PLOTLY_GRID, tickfont=dict(size=15)),
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


def render_pie_chart(df: pd.DataFrame) -> None:
    """Render interactive donut pie chart of spending by category."""
    cat_df = get_category_breakdown(df)
    fig = px.pie(
        cat_df,
        values="total",
        names="category",
        color_discrete_sequence=CHART_COLORS,
        hole=0.52,
    )
    fig.update_traces(
        textposition="outside",
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>₪%{value:,.0f}<br>%{percent}<extra></extra>",
        textfont_size=15,
    )
    fig = _dark_layout(fig, "לפי קטגוריה")
    fig.update_layout(
        showlegend=False,
        height=440,
        annotations=[dict(
            text=f"₪{df['amount'].sum():,.0f}",
            x=0.5, y=0.5,
            font=dict(size=22, color=PLOTLY_TITLE, family="IBM Plex Mono"),
            showarrow=False,
        )],
    )
    st.plotly_chart(fig, use_container_width=True)


def render_merchants_chart(df: pd.DataFrame) -> None:
    """Render horizontal bar chart of top merchants by spend."""
    merchant_df = get_top_merchants(df, n=8)
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
    fig = _dark_layout(fig, "ספקים מובילים")
    fig.update_layout(
        height=440,
        xaxis=dict(visible=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=14)),
        bargap=0.3,
        margin=dict(t=52, b=10, l=10, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_anomalies(df: pd.DataFrame) -> None:
    """Render the insights and anomalies alert cards."""
    anomalies = get_anomalies(df)
    if not anomalies:
        st.caption("לא זוהו חריגות בתקופה הנבחרת.")
        return
    cards = '<div class="iw">'
    for a in anomalies:
        icon = "🚨" if a["severity"] == "high" else "⚠️"
        cards += f'<div class="ic {a["severity"]}"><span>{icon}</span><span>{a["message"]}</span></div>'
    cards += "</div>"
    st.markdown(cards, unsafe_allow_html=True)


def render_transactions_table(df: pd.DataFrame) -> None:
    """Render the searchable, sortable full transactions table."""
    search = st.text_input("🔍 חיפוש לפי שם ספק", placeholder="לדוגמה: שופרסל, ארומה...")

    display = df[["date", "merchant", "category", "amount"]].copy()
    display["date"] = display["date"].dt.strftime("%d/%m/%Y")
    display = display.rename(columns={
        "date":     "תאריך",
        "merchant": "בית עסק",
        "category": "קטגוריה",
        "amount":   "סכום (₪)",
    })

    if search:
        display = display[display["בית עסק"].str.contains(search, na=False)]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config={"סכום (₪)": st.column_config.NumberColumn(format="₪%.2f")},
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
                st.session_state[cache_key] = parse_pdf(BytesIO(f.getvalue()))
            except ValueError as exc:
                errors.append(f"❌ {f.name}: {exc}")
                st.session_state[cache_key] = None

        cached = st.session_state.get(cache_key)
        if cached is not None:
            dfs.append(cached)

    if not dfs:
        return None, errors

    merged = (
        pd.concat(dfs, ignore_index=True)
        .sort_values("date")
        .reset_index(drop=True)
    )
    return merged, errors


def _render_empty_state() -> None:
    """Render the welcome screen shown before any data is loaded."""
    st.markdown("""
    <div style="display:flex; flex-direction:column; align-items:center;
                justify-content:center; min-height:55vh; text-align:center; gap:1rem;">
      <div style="font-size:3.5rem;">💳</div>
      <div style="font-size:1.6rem; font-weight:800; color:var(--tx);">
        דשבורד הוצאות אשראי
      </div>
      <div style="font-size:0.9rem; color:var(--tx2); max-width:380px; line-height:1.7;">
        העלה קובץ PDF של פירוט כרטיס אשראי <b>כאל</b> מהתפריט הצדדי,
        או לחץ על <b>נתוני הדגמה</b> כדי לראות את הדשבורד בפעולה.
      </div>
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
                if st.session_state.get("data_source") != "pdf":
                    st.session_state.pop("filter_months", None)
                    st.session_state.pop("filter_cats", None)
                st.session_state.df_all = df_parsed
                st.session_state.data_source = "pdf"
            for err in parse_errors:
                st.error(err)

        # Demo data button (visible when no PDF data is loaded)
        if st.session_state.get("data_source") != "pdf":
            if st.button("🎲 נתוני הדגמה", use_container_width=True):
                st.session_state.df_all = get_mock_data()
                st.session_state.data_source = "demo"
                st.session_state.pop("filter_months", None)
                st.session_state.pop("filter_cats", None)

        # Clear button (visible only when data is present)
        if st.session_state.get("df_all") is not None:
            if st.button("🗑️ נקה נתונים", use_container_width=True):
                st.session_state.clear()
                st.rerun()

        df_all: pd.DataFrame | None = st.session_state.get("df_all")

        # Filters — shown only after data is loaded
        if df_all is not None:
            st.divider()

            all_periods = sorted(
                df_all["date"].dt.to_period("M").unique().astype(str).tolist(),
                reverse=True,
            )
            # key= lets Streamlit persist selections across reruns via session_state.
            # We only set the initial value; after that Streamlit owns the key.
            if "filter_months" not in st.session_state:
                st.session_state["filter_months"] = all_periods
            selected_months = st.multiselect(
                "חודשים",
                options=all_periods,
                key="filter_months",
                format_func=_period_to_hebrew,
            )
            st.divider()

            all_cats = sorted(df_all["category"].unique().tolist())
            if "filter_cats" not in st.session_state:
                st.session_state["filter_cats"] = all_cats
            selected_cats = st.multiselect(
                "קטגוריות",
                options=all_cats,
                key="filter_cats",
            )
            st.divider()

            source = "קובץ PDF" if st.session_state.get("data_source") == "pdf" else "נתוני הדגמה"
            n_months = df_all["date"].dt.to_period("M").nunique()
            st.caption(f"מקור: {source}")
            st.caption(f"📊 {len(df_all):,} עסקאות | {n_months} חודשים")
            st.caption("🔒 קבצי PDF לא מועלים ל-GitHub")

    # ── Empty state ───────────────────────────────────────────────────────────────
    df_all = st.session_state.get("df_all")
    if df_all is None:
        _render_empty_state()
        return

    # ── Apply filters ─────────────────────────────────────────────────────────────
    df = df_all.copy()
    if selected_months:
        df = df[df["date"].dt.to_period("M").astype(str).isin(selected_months)]
    if selected_cats:
        df = df[df["category"].isin(selected_cats)]

    # ── Header ────────────────────────────────────────────────────────────────────
    is_demo = st.session_state.get("data_source") == "demo"
    subtitle = "נתוני הדגמה — העלה PDF לנתונים אמיתיים" if is_demo else "ניתוח פירוט כרטיס אשראי"
    st.markdown(f"""
    <div class="hdr">
      <div class="hdr-title">דשבורד <span>הוצאות אשראי</span></div>
      <div class="hdr-sub">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.warning("אין נתונים תואמים לסינון הנבחר.")
        return

    # ── KPIs ──────────────────────────────────────────────────────────────────────
    render_kpis(compute_kpis(df))

    # ── Charts ────────────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">ניתוח הוצאות</div>', unsafe_allow_html=True)
    col_pie, col_bar = st.columns(2, gap="medium")
    with col_pie:
        render_pie_chart(df)
    with col_bar:
        render_merchants_chart(df)

    # ── Category Summary ──────────────────────────────────────────────────────────
    st.markdown('<div class="sec">סיכום קטגוריות</div>', unsafe_allow_html=True)
    cat_summary = get_category_breakdown(df).copy()
    cat_summary.columns = ["קטגוריה", 'סה"כ (₪)', "עסקאות"]
    st.dataframe(
        cat_summary,
        use_container_width=True,
        hide_index=True,
        column_config={'סה"כ (₪)': st.column_config.NumberColumn(format="₪%.2f")},
    )

    # ── Anomalies ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">תובנות וחריגים</div>', unsafe_allow_html=True)
    render_anomalies(df)

    # ── Full Transactions Table ───────────────────────────────────────────────────
    st.markdown('<div class="sec">כל העסקאות</div>', unsafe_allow_html=True)
    render_transactions_table(df)


if __name__ == "__main__":
    main()
