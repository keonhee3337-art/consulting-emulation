"""
app.py — M&A Due Diligence Suite
Streamlit consulting dashboard with financial visualizations.

Start:
    cd projects/consulting-emulation
    streamlit run app.py
"""

import os
import sys
import tempfile

import streamlit as st

# ---------------------------------------------------------------------------
# Path + env setup — must come before any FinAgent or pipeline imports
# Local: use full FinAgent path. Cloud (Streamlit): use bundled finagent/ dir.
# ---------------------------------------------------------------------------
_LOCAL_FINAGENT = "c:/Users/keonh/OneDrive/바탕 화면/FinAgent"
_BUNDLED_FINAGENT = os.path.join(os.path.dirname(__file__), "finagent")

FINAGENT_PATH = _LOCAL_FINAGENT if os.path.exists(_LOCAL_FINAGENT) else _BUNDLED_FINAGENT
if FINAGENT_PATH not in sys.path:
    sys.path.insert(0, FINAGENT_PATH)

from dotenv import load_dotenv
load_dotenv(os.path.join(FINAGENT_PATH, ".env"))  # local only; cloud uses st.secrets

# ---------------------------------------------------------------------------
# Pipeline imports (deferred to after path setup)
# ---------------------------------------------------------------------------
from agents.graph_builder import build_consulting_graph
from agents.valuation_agent import (
    _fetch_company_financials,
    _fetch_all_companies,
    _run_dcf,
    _run_comps,
)
from output.pptx_generator import generate_deck

import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="M&A Due Diligence Suite",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS — Inter font, consulting document feel
# Calibri is standard at McKinsey/BCG; Inter is the closest open-weight web equivalent.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"], [class*="stMarkdown"], p, li, span, div {
    font-family: 'Inter', 'Calibri', 'Segoe UI', sans-serif !important;
    font-size: 14px;
    line-height: 1.6;
    color: #1a1a1a;
}

h1, h2, h3, h4 {
    font-family: 'Inter', 'Calibri', sans-serif !important;
    font-weight: 600;
    letter-spacing: -0.3px;
    color: #111827;
}

.stApp {
    background: #f9fafb;
}

.section-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #9ca3af;
    margin-bottom: 6px;
    padding-bottom: 4px;
    border-bottom: 1px solid #e5e7eb;
}

.analyst-note {
    background: #fffbeb;
    border-left: 3px solid #f59e0b;
    padding: 10px 16px;
    font-size: 12px;
    color: #78716c;
    border-radius: 2px;
    margin-top: 8px;
}

.stDownloadButton > button {
    font-family: 'Inter', 'Calibri', sans-serif !important;
    font-size: 13px;
    font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Chart constants — consulting palette (McKinsey/BCG style)
# ---------------------------------------------------------------------------
C_BLUE   = "#1d4ed8"   # primary metric
C_GREEN  = "#059669"   # positive / secondary metric
C_GRAY   = "#9ca3af"   # neutral / midpoint
C_RED    = "#dc2626"   # negative / loss
C_LIGHT  = "#f3f4f6"   # gridlines

CHART_FONT = dict(family="Inter, Calibri, Segoe UI, sans-serif", size=11, color="#374151")
CHART_TITLE_FONT = dict(size=12, family="Inter, Calibri, sans-serif", color="#111827")
CHART_LAYOUT = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=CHART_FONT,
    margin=dict(l=0, r=4, t=44, b=0),
)


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _chart_financial_history(company: str) -> None:
    """Grouped bar: Revenue, Operating Profit, Net Profit by year."""
    rows = _fetch_company_financials(company)
    if not rows:
        st.caption("No financial history in DB.")
        return

    years = [str(r["year"]) for r in rows]
    revenue   = [r.get("revenue_billion_krw") for r in rows]
    op_profit = [r.get("operating_profit_billion_krw") for r in rows]
    net_profit = [r.get("net_profit_billion_krw") for r in rows]

    def _labels(vals):
        return [f"{v:,.0f}" if v is not None else "" for v in vals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Revenue", x=years, y=revenue,
        marker_color=C_BLUE,
        text=_labels(revenue), textposition="outside", textfont=dict(size=9),
    ))
    fig.add_trace(go.Bar(
        name="Operating Profit", x=years, y=op_profit,
        marker_color=C_GREEN,
        text=_labels(op_profit), textposition="outside", textfont=dict(size=9),
    ))
    fig.add_trace(go.Bar(
        name="Net Profit", x=years, y=net_profit,
        marker_color=C_GRAY,
        text=_labels(net_profit), textposition="outside", textfont=dict(size=9),
    ))

    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(
            text=f"{company} — Revenue & Profit (KRW bn)",
            font=CHART_TITLE_FONT, x=0,
        ),
        barmode="group",
        height=300,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(size=10)),
        xaxis=dict(showgrid=False, tickfont=CHART_FONT),
        yaxis=dict(showgrid=True, gridcolor=C_LIGHT, tickfont=CHART_FONT,
                   title="KRW (bn)", title_font=dict(size=11)),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Source: FinAgent SQLite DB — DART public disclosures")


def _chart_margin_trend(company: str) -> None:
    """Line chart: Operating Margin % and Net Margin % over years."""
    rows = _fetch_company_financials(company)
    if not rows:
        return

    years = [str(r["year"]) for r in rows]
    op_margins, net_margins = [], []
    for r in rows:
        rev = r.get("revenue_billion_krw") or 0
        op  = r.get("operating_profit_billion_krw")
        net = r.get("net_profit_billion_krw")
        op_margins.append(round(op / rev * 100, 1) if rev and op is not None else None)
        net_margins.append(round(net / rev * 100, 1) if rev and net is not None else None)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        name="Operating Margin %", x=years, y=op_margins,
        mode="lines+markers+text",
        line=dict(color=C_BLUE, width=2),
        marker=dict(size=6),
        text=[f"{v:.1f}%" if v is not None else "" for v in op_margins],
        textposition="top center", textfont=dict(size=9),
    ))
    fig.add_trace(go.Scatter(
        name="Net Margin %", x=years, y=net_margins,
        mode="lines+markers+text",
        line=dict(color=C_GREEN, width=2, dash="dot"),
        marker=dict(size=6),
        text=[f"{v:.1f}%" if v is not None else "" for v in net_margins],
        textposition="bottom center", textfont=dict(size=9),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=C_RED, line_width=1, opacity=0.4)

    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(
            text=f"{company} — Profit Margins Over Time",
            font=CHART_TITLE_FONT, x=0,
        ),
        height=260,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(size=10)),
        xaxis=dict(showgrid=False, tickfont=CHART_FONT),
        yaxis=dict(showgrid=True, gridcolor=C_LIGHT, tickfont=CHART_FONT,
                   ticksuffix="%"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _chart_dcf_waterfall(dcf: dict) -> None:
    """Waterfall chart: Base FCF → PV Projected FCFs → PV Terminal Value → EV."""
    if not dcf or dcf.get("ev_dcf_bn") is None:
        st.caption("DCF data unavailable.")
        return

    pv_fcfs     = dcf.get("pv_sum_fcfs", 0)
    pv_terminal = dcf.get("pv_terminal", 0)
    ev_total    = dcf.get("ev_dcf_bn", 0)

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "total"],
        x=["PV of Projected FCFs", "PV of Terminal Value", "Enterprise Value (DCF)"],
        y=[pv_fcfs, pv_terminal, ev_total],
        text=[f"{v:,.1f}" for v in [pv_fcfs, pv_terminal, ev_total]],
        textposition="outside",
        textfont=dict(size=10, family="Inter, Calibri, sans-serif"),
        connector=dict(line=dict(color="#e5e7eb", width=1)),
        increasing=dict(marker=dict(color=C_BLUE)),
        totals=dict(marker=dict(color="#111827")),
    ))

    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(
            text="DCF Bridge — How EV is Built",
            font=CHART_TITLE_FONT, x=0,
        ),
        height=300,
        showlegend=False,
        yaxis=dict(showgrid=True, gridcolor=C_LIGHT, tickfont=CHART_FONT,
                   title="KRW (bn)", title_font=dict(size=11)),
        xaxis=dict(showgrid=False, tickfont=dict(size=11, family="Inter, Calibri, sans-serif")),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"WACC = 10% · Terminal growth = 2.5% · FCF = Net Income × 0.85 · "
        f"{dcf.get('years_of_data', '?')} years of historical data used"
    )


def _chart_valuation_comparison(dcf: dict, comps: dict, company: str) -> None:
    """Horizontal bar: DCF vs Comps valuation with midpoint."""
    ev_dcf   = dcf.get("ev_dcf_bn") if dcf else None
    ev_comps = comps.get("ev_comps_bn") if comps else None

    if ev_dcf is None and ev_comps is None:
        st.caption("Valuation data unavailable.")
        return

    labels, values, colors = [], [], []
    if ev_dcf is not None:
        labels.append("DCF Valuation")
        values.append(ev_dcf)
        colors.append(C_BLUE)
    if ev_comps is not None:
        labels.append("EV/EBITDA Comps")
        values.append(ev_comps)
        colors.append(C_GREEN)
    if ev_dcf is not None and ev_comps is not None:
        labels.append("Midpoint")
        values.append(round((ev_dcf + ev_comps) / 2, 1))
        colors.append(C_GRAY)

    fig = go.Figure(go.Bar(
        x=values, y=labels,
        orientation="h",
        marker_color=colors,
        text=[f"KRW {v:,.1f} bn" for v in values],
        textposition="outside",
        textfont=dict(size=10),
    ))

    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(
            text=f"{company} — Valuation Range",
            font=CHART_TITLE_FONT, x=0,
        ),
        height=200,
        showlegend=False,
        xaxis=dict(showgrid=True, gridcolor=C_LIGHT, tickfont=CHART_FONT,
                   title="KRW (billions)", title_font=dict(size=11)),
        yaxis=dict(showgrid=False,
                   tickfont=dict(size=11, family="Inter, Calibri, sans-serif")),
        margin=dict(l=0, r=80, t=44, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### M&A Due Diligence Suite")
    st.markdown(
        "Automated due diligence powered by LangGraph, Text2SQL, RAG, "
        "and a DCF/Comps Valuation Agent."
    )
    st.divider()
    st.markdown("**Route Legend**")
    st.markdown(
        "- `sql_only` — Structured financial data\n"
        "- `rag_only` — Strategy & qualitative\n"
        "- `valuation` — DCF, EV, intrinsic value\n"
        "- `both` — Data + narrative combined"
    )
    st.divider()
    st.caption("Data: DART disclosures + FinAgent SQLite DB (Samsung, SK Hynix, LG)")

# ---------------------------------------------------------------------------
# Graph — cached per session
# ---------------------------------------------------------------------------
if "graph" not in st.session_state:
    with st.spinner("Initialising pipeline..."):
        st.session_state.graph = build_consulting_graph()

graph = st.session_state.graph

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("## M&A Due Diligence Suite")
st.markdown(
    '<p style="color:#6b7280; font-size:13px; margin-top:-10px; margin-bottom:16px;">'
    'Automated financial analysis — Korean market (Samsung · SK Hynix · LG Electronics)'
    '</p>',
    unsafe_allow_html=True,
)
st.divider()

# ---------------------------------------------------------------------------
# Query input
# ---------------------------------------------------------------------------
col_input, col_btn = st.columns([4, 1])
with col_input:
    query = st.text_input(
        "query",
        placeholder=(
            '"What is Samsung\'s valuation?"  |  '
            '"Compare SK Hynix and Samsung profitability 2021–2023"  |  '
            '"Explain the HBM opportunity for Korean chipmakers"'
        ),
        label_visibility="collapsed",
    )
with col_btn:
    run_button = st.button("Run Analysis", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
COMPANY_MAP = {
    "Samsung Electronics": ["samsung electronics", "samsung"],
    "SK Hynix":            ["sk hynix", "hynix"],
    "LG Electronics":      ["lg electronics", "lg"],
}

ROUTE_COLORS = {
    "sql_only":  "#1d4ed8",
    "rag_only":  "#059669",
    "valuation": "#d97706",
    "both":      "#7c3aed",
}

if run_button and query.strip():
    with st.spinner("Running analysis..."):
        result = graph.invoke(
            {"query": query.strip()},
            config={"configurable": {"thread_id": "streamlit-1"}},
        )

    route          = result.get("route", "unknown")
    report         = result.get("report", "")
    valuation_text = result.get("valuation_result", None)

    # Detect company
    company_name = "Target Company"
    for name, keywords in COMPANY_MAP.items():
        if any(kw in query.lower() for kw in keywords):
            company_name = name
            break

    # Route badge
    badge_color = ROUTE_COLORS.get(route, "#6b7280")
    st.markdown(
        f'<span style="background:{badge_color}; color:white; padding:2px 10px; '
        f'border-radius:10px; font-size:11px; font-weight:600; letter-spacing:0.5px; '
        f'text-transform:uppercase">{route}</span>'
        f'&nbsp;&nbsp;<span style="color:#6b7280; font-size:13px">{company_name}</span>',
        unsafe_allow_html=True,
    )
    st.divider()

    # --- Pull structured valuation data for charts ---
    dcf_data, comps_data = {}, {}
    if company_name != "Target Company":
        rows = _fetch_company_financials(company_name)
        if rows:
            all_cos   = _fetch_all_companies()
            dcf_data  = _run_dcf(rows, company_name)
            comps_data = _run_comps(company_name, all_cos)

    # --- Valuation KPI metrics row (valuation route only) ---
    if route == "valuation" and dcf_data.get("ev_dcf_bn") is not None:
        ev_dcf   = dcf_data.get("ev_dcf_bn")
        ev_comps = comps_data.get("ev_comps_bn")
        midpoint = round((ev_dcf + ev_comps) / 2, 1) if ev_dcf and ev_comps else None

        st.markdown('<p class="section-label">Valuation Summary</p>', unsafe_allow_html=True)
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("EV — DCF", f"KRW {ev_dcf:,.1f} bn" if ev_dcf else "—")
        with k2:
            st.metric("EV — Comps", f"KRW {ev_comps:,.1f} bn" if ev_comps else "—")
        with k3:
            st.metric("Midpoint", f"KRW {midpoint:,.1f} bn" if midpoint else "—")
        with k4:
            st.metric("WACC Used", "10.0%")
        st.divider()

    # --- Main two-column layout ---
    col_report, col_charts = st.columns([1.1, 0.9], gap="large")

    with col_report:
        st.markdown('<p class="section-label">Analysis</p>', unsafe_allow_html=True)
        if report:
            st.markdown(report)
        else:
            st.warning("No report generated.")

    with col_charts:
        if company_name != "Target Company":
            tab1, tab2 = st.tabs(["Revenue & Profit", "Margins"])
            with tab1:
                _chart_financial_history(company_name)
            with tab2:
                _chart_margin_trend(company_name)
        else:
            st.caption("Name a company in your query (Samsung, SK Hynix, LG) to see charts.")

    st.divider()

    # --- Valuation charts (full width below main content) ---
    if route == "valuation" and dcf_data.get("ev_dcf_bn") is not None:
        st.markdown('<p class="section-label">Valuation Analysis</p>', unsafe_allow_html=True)
        vc1, vc2 = st.columns(2, gap="large")
        with vc1:
            _chart_dcf_waterfall(dcf_data)
        with vc2:
            _chart_valuation_comparison(dcf_data, comps_data, company_name)

        st.markdown(
            '<div class="analyst-note">Analyst note — Data limitations: '
            'EBITDA proxy = Operating Profit (D&A excluded). '
            'Peer universe = 3 Korean electronics companies only (cross-sector comps — interpret cautiously). '
            'EV figures exclude net debt adjustment and do not represent equity value.</div>',
            unsafe_allow_html=True,
        )
        st.divider()

    # --- Valuation detail expander ---
    if valuation_text:
        with st.expander("Full Valuation Detail"):
            st.code(valuation_text, language=None)

    # --- PPTX download ---
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        generate_deck(
            report=report or "",
            company_name=company_name,
            output_path=tmp_path,
            valuation_result=valuation_text,
        )
        with open(tmp_path, "rb") as f:
            pptx_bytes = f.read()

        st.download_button(
            label="Download Report as PPTX",
            data=pptx_bytes,
            file_name=f"{company_name.replace(' ', '_')}_due_diligence.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

elif run_button and not query.strip():
    st.warning("Please enter a query before running.")
