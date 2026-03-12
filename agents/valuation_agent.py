"""
Valuation Agent — Step 2.3 of Automated M&A Due Diligence & Strategy War Room.

Performs two valuation methods purely from SQLite financial data:
  1. DCF (Discounted Cash Flow) — 5-year projection, terminal value, PV sum
  2. Comparable Company Analysis (EV/EBITDA comps) — peer median multiple

No OpenAI calls. No new pip installs. stdlib + sqlite3 only.
"""

import sqlite3
import os
import statistics
from typing import Optional

# ---------------------------------------------------------------------------
# Database path — same SQLite used by FinAgent's sql_agent.py
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../../../FinAgent/data/financial.db"
)

# Normalize to absolute path so relative resolution doesn't bite us
DB_PATH = os.path.abspath(DB_PATH)

# ---------------------------------------------------------------------------
# DCF assumptions (stated explicitly for portfolio/interview transparency)
# ---------------------------------------------------------------------------
FCF_MARGIN_PROXY = 0.85   # FCF = Net Income × 0.85 (capex-light proxy; real analysis uses CFO - capex)
WACC = 0.10               # 10% — industry standard for Korean large-cap tech/electronics
TERMINAL_GROWTH_RATE = 0.025   # 2.5% — long-run GDP growth proxy for Korea
FALLBACK_REVENUE_GROWTH = 0.05  # 5% — used when <2 years of data available to compute CAGR
PROJECTION_YEARS = 5


# ---------------------------------------------------------------------------
# DB helper — read-only connection
# ---------------------------------------------------------------------------
def _fetch_company_financials(company: str) -> list[dict]:
    """Return all rows for a company sorted by year ascending."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT year, revenue_billion_krw, operating_profit_billion_krw, net_profit_billion_krw
        FROM financials
        WHERE company = ?
        ORDER BY year ASC
        """,
        (company,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _fetch_all_companies() -> list[str]:
    """Return all distinct company names in the DB."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT company FROM financials")
    companies = [r[0] for r in cursor.fetchall()]
    conn.close()
    return companies


def _fetch_latest_row(company: str) -> Optional[dict]:
    """Return the most recent year's row for a company."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT year, revenue_billion_krw, operating_profit_billion_krw, net_profit_billion_krw
        FROM financials
        WHERE company = ?
        ORDER BY year DESC
        LIMIT 1
        """,
        (company,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Step 1: Identify target company from state["query"]
# ---------------------------------------------------------------------------
def _resolve_company(query: str, available: list[str]) -> Optional[str]:
    """
    Case-insensitive substring match between query and company names.
    Returns the first match, or None if no company is mentioned.
    """
    q_lower = query.lower()
    for company in available:
        if company.lower() in q_lower:
            return company
    # Also try partial matches (e.g. "Samsung" matches "Samsung Electronics")
    for company in available:
        # Check each word of the company name
        for word in company.split():
            if len(word) > 3 and word.lower() in q_lower:
                return company
    return None


# ---------------------------------------------------------------------------
# Step 2: DCF Valuation
# ---------------------------------------------------------------------------
def _run_dcf(rows: list[dict], company: str) -> dict:
    """
    DCF using last 3 available years of data.

    Returns a dict with:
      - ev_dcf_bn: enterprise value estimate in KRW billions
      - fcf_base: base FCF used for projection (KRW bn)
      - growth_rate: revenue CAGR used for FCF growth
      - assumptions_note: string describing what was assumed
    """
    # Use last 3 years (or however many exist)
    recent = rows[-3:] if len(rows) >= 3 else rows

    # --- Base FCF: average net income over available period × 0.85 ---
    # We average to smooth single-year anomalies (e.g. SK Hynix 2023 loss)
    net_incomes = [r["net_profit_billion_krw"] for r in recent if r["net_profit_billion_krw"] is not None]

    if not net_incomes:
        return {
            "ev_dcf_bn": None,
            "error": "No net income data available for DCF.",
        }

    avg_net_income = sum(net_incomes) / len(net_incomes)
    fcf_base = avg_net_income * FCF_MARGIN_PROXY

    # --- Revenue CAGR for growth rate ---
    revenues = [r["revenue_billion_krw"] for r in recent if r["revenue_billion_krw"] is not None]
    years_span = len(revenues) - 1

    if years_span >= 1 and revenues[0] > 0:
        # CAGR = (end / start) ^ (1 / n) - 1
        cagr = (revenues[-1] / revenues[0]) ** (1 / years_span) - 1
        # Cap CAGR at +/- 25% to avoid model blow-up from single-year swings
        growth_rate = max(-0.25, min(0.25, cagr))
        growth_note = f"computed CAGR of {cagr:.1%} from {len(recent)}-year data (capped ±25%)"
    else:
        growth_rate = FALLBACK_REVENUE_GROWTH
        growth_note = f"fallback assumption ({FALLBACK_REVENUE_GROWTH:.0%} — insufficient data)"

    # --- Project 5 years of FCF ---
    projected_fcfs = []
    for t in range(1, PROJECTION_YEARS + 1):
        fcf_t = fcf_base * (1 + growth_rate) ** t
        projected_fcfs.append(fcf_t)

    # --- Discount each FCF to present value ---
    pv_fcfs = []
    for t, fcf_t in enumerate(projected_fcfs, start=1):
        pv = fcf_t / (1 + WACC) ** t
        pv_fcfs.append(pv)

    # --- Terminal Value (Gordon Growth Model) ---
    # TV = FCF_year5 × (1 + g) / (WACC - g)
    fcf_year5 = projected_fcfs[-1]
    terminal_value = fcf_year5 * (1 + TERMINAL_GROWTH_RATE) / (WACC - TERMINAL_GROWTH_RATE)

    # Discount terminal value to present
    pv_terminal = terminal_value / (1 + WACC) ** PROJECTION_YEARS

    # --- Enterprise Value = sum of PV(FCFs) + PV(terminal value) ---
    ev_dcf = sum(pv_fcfs) + pv_terminal

    return {
        "ev_dcf_bn": round(ev_dcf, 1),
        "fcf_base": round(fcf_base, 1),
        "growth_rate": growth_rate,
        "growth_note": growth_note,
        "pv_sum_fcfs": round(sum(pv_fcfs), 1),
        "pv_terminal": round(pv_terminal, 1),
        "years_of_data": len(recent),
    }


# ---------------------------------------------------------------------------
# Step 3: Comparable Company Analysis (EV/EBITDA comps)
# ---------------------------------------------------------------------------
def _run_comps(target_company: str, all_companies: list[str]) -> dict:
    """
    EV/EBITDA comp analysis.

    Since we lack market cap data, we use a simplified implied-EV approach:
      - Proxy EV for each peer = sum of PV(5-year operating profit) at WACC
        (this treats operating profit as a rough EBITDA proxy)
      - EV/EBITDA multiple = implied_EV / latest operating_profit
      - Apply peer median multiple to target EBITDA

    Returns a dict with ev_comps_bn and supporting details.
    """
    peers = [c for c in all_companies if c != target_company]

    if not peers:
        return {
            "ev_comps_bn": None,
            "error": "No peer companies available in DB for comps analysis.",
        }

    # --- Compute EV/EBITDA multiple for each peer ---
    peer_multiples = []
    for peer in peers:
        peer_row = _fetch_latest_row(peer)
        if peer_row is None:
            continue
        ebitda_proxy = peer_row["operating_profit_billion_krw"]
        if ebitda_proxy is None or ebitda_proxy <= 0:
            # Skip peers with negative or missing EBITDA (e.g. SK Hynix 2023)
            continue

        # Implied EV for peer: use 5-year perpetuity of current EBITDA at WACC
        # (simplified — avoids needing peer market caps)
        # EV = EBITDA / WACC  (Gordon: g=0 baseline, then adjust for growth)
        # More conservatively: use midpoint of no-growth and 2.5% growth perpetuity
        ev_no_growth = ebitda_proxy / WACC
        ev_with_growth = ebitda_proxy * (1 + TERMINAL_GROWTH_RATE) / (WACC - TERMINAL_GROWTH_RATE)
        implied_ev = (ev_no_growth + ev_with_growth) / 2

        multiple = implied_ev / ebitda_proxy
        peer_multiples.append({"peer": peer, "ebitda": ebitda_proxy, "multiple": multiple})

    if not peer_multiples:
        return {
            "ev_comps_bn": None,
            "error": "All peer companies have non-positive EBITDA — comps not computable.",
        }

    # --- Peer median EV/EBITDA multiple ---
    multiples_only = [p["multiple"] for p in peer_multiples]
    median_multiple = statistics.median(multiples_only)

    # --- Apply to target ---
    target_row = _fetch_latest_row(target_company)
    if target_row is None:
        return {"ev_comps_bn": None, "error": "No data for target company."}

    target_ebitda = target_row["operating_profit_billion_krw"]
    if target_ebitda is None or target_ebitda <= 0:
        return {
            "ev_comps_bn": None,
            "error": f"Target EBITDA proxy is non-positive ({target_ebitda}) — comps not applicable.",
        }

    ev_comps = median_multiple * target_ebitda

    return {
        "ev_comps_bn": round(ev_comps, 1),
        "target_ebitda": round(target_ebitda, 1),
        "median_multiple": round(median_multiple, 2),
        "peer_details": peer_multiples,
        "target_year": target_row["year"],
    }


# ---------------------------------------------------------------------------
# Step 4: Format output summary
# ---------------------------------------------------------------------------
def _format_summary(company: str, dcf: dict, comps: dict) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f"VALUATION SUMMARY — {company}")
    lines.append("=" * 60)

    # --- DCF section ---
    lines.append("\n[ 1. DCF VALUATION ]")
    if dcf.get("ev_dcf_bn") is not None:
        lines.append(f"  Enterprise Value (DCF):   KRW {dcf['ev_dcf_bn']:,.1f} bn")
        lines.append(f"  Base FCF (avg, 3yr proxy): KRW {dcf['fcf_base']:,.1f} bn")
        lines.append(f"  Revenue growth rate used:  {dcf['growth_rate']:.1%} ({dcf['growth_note']})")
        lines.append(f"  PV of projected FCFs:      KRW {dcf['pv_sum_fcfs']:,.1f} bn")
        lines.append(f"  PV of terminal value:      KRW {dcf['pv_terminal']:,.1f} bn")
        lines.append(f"  Years of data used:        {dcf['years_of_data']}")
    else:
        lines.append(f"  DCF not computable: {dcf.get('error', 'unknown error')}")

    lines.append("\n  Key DCF Assumptions:")
    lines.append(f"    WACC:                  {WACC:.0%}")
    lines.append(f"    Terminal growth rate:   {TERMINAL_GROWTH_RATE:.1%}")
    lines.append(f"    Projection period:     {PROJECTION_YEARS} years")
    lines.append(f"    FCF = Net Income x {FCF_MARGIN_PROXY}")

    # --- Comps section ---
    lines.append("\n[ 2. COMPARABLE COMPANY ANALYSIS (EV/EBITDA) ]")
    if comps.get("ev_comps_bn") is not None:
        lines.append(f"  Enterprise Value (Comps): KRW {comps['ev_comps_bn']:,.1f} bn")
        lines.append(f"  Target EBITDA proxy:      KRW {comps['target_ebitda']:,.1f} bn  (year: {comps['target_year']})")
        lines.append(f"  Peer median EV/EBITDA:    {comps['median_multiple']:.1f}x")
        lines.append("  Peer multiples:")
        for p in comps["peer_details"]:
            lines.append(f"    {p['peer']}: EBITDA {p['ebitda']:,.0f} bn → implied {p['multiple']:.1f}x")
    else:
        lines.append(f"  Comps not computable: {comps.get('error', 'unknown error')}")

    lines.append("\n  Key Comps Assumptions:")
    lines.append("    EBITDA proxy = Operating Profit (D&A not available in DB)")
    lines.append("    Peer EV implied via perpetuity (midpoint: no-growth / 2.5%-growth)")
    lines.append("    Peer universe = all other companies in DB (cross-sector — interpret cautiously)")

    # --- Triangulation ---
    lines.append("\n[ 3. VALUATION RANGE ]")
    ev_dcf = dcf.get("ev_dcf_bn")
    ev_comps = comps.get("ev_comps_bn")
    if ev_dcf is not None and ev_comps is not None:
        low = min(ev_dcf, ev_comps)
        high = max(ev_dcf, ev_comps)
        mid = (ev_dcf + ev_comps) / 2
        lines.append(f"  DCF:   KRW {ev_dcf:,.1f} bn")
        lines.append(f"  Comps: KRW {ev_comps:,.1f} bn")
        lines.append(f"  Range: KRW {low:,.1f} bn — {high:,.1f} bn  (midpoint: {mid:,.1f} bn)")
    elif ev_dcf is not None:
        lines.append(f"  DCF only (comps unavailable): KRW {ev_dcf:,.1f} bn")
    elif ev_comps is not None:
        lines.append(f"  Comps only (DCF unavailable): KRW {ev_comps:,.1f} bn")
    else:
        lines.append("  Neither method produced a result — check data availability.")

    # --- Analyst note ---
    lines.append("\n[ ANALYST NOTE ]")
    lines.append(
        "  Data limitations: DB contains 3 Korean electronics companies (2020-2024); "
        "cross-sector comps reduce peer relevance; FCF proxy excludes actual capex drawdown; "
        "no net debt adjustment applied - EV figures do not represent equity value."
    )

    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public LangGraph node
# ---------------------------------------------------------------------------
def run_valuation_agent(state: dict) -> dict:
    """LangGraph node: DCF + comparable company valuation from SQLite financial data."""

    query = state.get("query", "")

    # --- Identify which company the query is about ---
    all_companies = _fetch_all_companies()

    if not all_companies:
        valuation_summary = (
            "Valuation Agent: No companies found in DB. "
            f"Check DB path: {DB_PATH}"
        )
        return {**state, "valuation_result": valuation_summary}

    target_company = _resolve_company(query, all_companies)

    if target_company is None:
        # Default to first company in DB if none detected
        target_company = all_companies[0]
        company_note = f"[Note: No specific company detected in query — defaulting to {target_company}]\n\n"
    else:
        company_note = ""

    # --- Fetch historical data for target ---
    rows = _fetch_company_financials(target_company)

    # --- Run both valuation methods ---
    dcf_result = _run_dcf(rows, target_company)
    comps_result = _run_comps(target_company, all_companies)

    # --- Format and return ---
    summary = company_note + _format_summary(target_company, dcf_result, comps_result)

    return {**state, "valuation_result": summary}
