"""
DART Live Data Pipeline
Fetches financial data and disclosures from DART (Korean FSS) using dart-fss.

Uses the same dart-fss patterns as the DART MCP server at:
  c:/Users/keonh/OneDrive/바탕 화면/dart-mcp-server/server.py

Key patterns:
  - dart.get_corp_list() → corp_list.find_by_corp_name() for search
  - corp.get_financial_statements(bsns_year, reprt_code, fs_div) for financials
  - dart.filings.search(corp_code, bgn_de, end_de) for disclosures
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

import dart_fss as dart

# Load DARTFSS_API_KEY from .env.
# Korean characters in __file__ mangle on Windows when resolved via os.path,
# so we use the known absolute path directly and fall back to the cwd-relative
# path if the hardcoded one doesn't exist (e.g., if the project moves).
_ENV_HARDCODED = (
    "c:/Users/keonh/OneDrive/바탕 화면/MCP_Agentic AI/.env"
)
_ENV_PATH = _ENV_HARDCODED if os.path.exists(_ENV_HARDCODED) else ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _init_dart():
    """Set the DART API key. Raises if not configured."""
    key = os.getenv("DARTFSS_API_KEY") or os.getenv("DART_API_KEY")
    if not key:
        raise ValueError(
            "DARTFSS_API_KEY not set. Add it to "
            "c:/Users/keonh/OneDrive/바탕 화면/MCP_Agentic AI/.env"
        )
    dart.set_api_key(key)


def search_company(company_name_korean: str) -> list[dict]:
    """
    Search DART for a company by Korean name.

    Uses dart.get_corp_list() to download the full DART corp list,
    then filters by corp_name using find_by_corp_name().

    Returns up to 10 matches, each with:
      - corp_code  : 8-digit DART identifier (used in other functions)
      - corp_name  : Korean company name
      - stock_code : KRX stock ticker (None for unlisted companies)
    """
    _init_dart()
    corp_list = dart.get_corp_list()
    results = corp_list.find_by_corp_name(company_name_korean, exactly=False)

    if not results:
        return []

    output = []
    for corp in results[:10]:
        output.append({
            "corp_code": corp.corp_code,
            "corp_name": corp.corp_name,
            "stock_code": getattr(corp, "stock_code", None),
        })
    return output


def get_financials(corp_code: str, year: int) -> dict:
    """
    Fetch annual financial statements for a company-year from DART.

    Uses corp.get_financial_statements() with:
      - reprt_code "11011" = annual report
      - fs_div "CFS" = consolidated financial statements (preferred)
      - Falls back to "OFS" (separate) if consolidated not available

    Extracts key income statement lines by scanning account names:
      - 매출액 / 수익(매출액) → revenue
      - 영업이익 → operating_profit
      - 당기순이익 → net_income

    Returns dict with keys: corp_code, year, revenue, operating_profit,
    net_income, currency (all KRW millions), plus raw_row_count for
    debugging. Returns error key on failure.
    """
    _init_dart()
    corp_list = dart.get_corp_list()
    corp = corp_list.find_by_corp_code(corp_code)

    if not corp:
        return {"error": f"No company found for corp_code={corp_code}"}

    # Annual report code
    reprt_code = "11011"

    fs = None
    for fs_div in ("CFS", "OFS"):
        try:
            fs = corp.get_financial_statements(
                bsns_year=str(year),
                reprt_code=reprt_code,
                fs_div=fs_div,
            )
            # dart-fss returns None or an empty DataFrame on no data
            if fs is not None and not (hasattr(fs, "empty") and fs.empty):
                break
        except Exception:
            fs = None
            continue

    if fs is None or (hasattr(fs, "empty") and fs.empty):
        return {"error": f"No financial data for corp_code={corp_code}, year={year}"}

    # Convert to list of dicts for uniform handling
    if hasattr(fs, "to_dict"):
        rows = fs.to_dict(orient="records")
    else:
        return {"error": "Unexpected financial statement format", "raw": str(fs)}

    result = {
        "corp_code": corp_code,
        "year": year,
        "revenue": None,
        "operating_profit": None,
        "net_income": None,
        "currency": "KRW_millions",
        "raw_row_count": len(rows),
    }

    # Account name substrings to match — order matters (first match wins)
    _REVENUE_KEYS = ("매출액", "수익(매출액)", "영업수익")
    _OP_PROFIT_KEYS = ("영업이익",)
    _NET_INCOME_KEYS = ("당기순이익",)

    def _extract_value(row: dict) -> int | None:
        """Pull the numeric value from a financial statement row dict."""
        # dart-fss uses the year as a column key — try common patterns
        for k, v in row.items():
            if str(year) in str(k) and v is not None:
                try:
                    return int(str(v).replace(",", "").replace(" ", ""))
                except (ValueError, TypeError):
                    return None
        return None

    def _matches(account_nm: str, keywords: tuple) -> bool:
        return any(kw in str(account_nm) for kw in keywords)

    for row in rows:
        acct = str(row.get("account_nm", row.get("계정명", "")))
        if result["revenue"] is None and _matches(acct, _REVENUE_KEYS):
            result["revenue"] = _extract_value(row)
        elif result["operating_profit"] is None and _matches(acct, _OP_PROFIT_KEYS):
            result["operating_profit"] = _extract_value(row)
        elif result["net_income"] is None and _matches(acct, _NET_INCOME_KEYS):
            result["net_income"] = _extract_value(row)

    return result


def get_recent_disclosures(corp_code: str, limit: int = 5) -> list[dict]:
    """
    Fetch most recent DART disclosures (공시) for a company.

    Uses dart.filings.search() with:
      - bgn_de : 90 days ago (YYYYMMDD)
      - end_de : today
      - page_count : limit

    Returns list of dicts with:
      - title   : disclosure report name
      - date    : receipt date (YYYYMMDD)
      - url     : link to full filing on dart.fss.or.kr
      - filer   : submitter name
    """
    _init_dart()

    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    end_date = datetime.now().strftime("%Y%m%d")

    try:
        filings = dart.filings.search(
            corp_code=corp_code,
            bgn_de=start_date,
            end_de=end_date,
            page_count=limit,
        )
    except Exception as e:
        return [{"error": f"Disclosure fetch failed: {e}"}]

    if not filings or not hasattr(filings, "list"):
        return []

    results = []
    for item in filings.list[:limit]:
        rcept_no = getattr(item, "rcept_no", "")
        results.append({
            "title": getattr(item, "report_nm", None),
            "date": getattr(item, "rcept_dt", None),
            "filer": getattr(item, "flr_nm", None),
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
        })
    return results


def build_financial_context(
    company_name_korean: str,
    years: list[int] | None = None,
) -> str:
    """
    High-level function: search company → fetch 3 years of financials → format as context string.

    Designed for injection into the Report Agent system prompt or RAG context.

    Steps:
      1. search_company() → pick first result
      2. get_financials() for each year in `years`
      3. get_recent_disclosures() for the 5 most recent filings
      4. Format everything as a readable text block

    years defaults to [current_year-1, current_year-2, current_year-3]
    """
    if years is None:
        current_year = datetime.now().year
        years = [current_year - 1, current_year - 2, current_year - 3]

    # --- Step 1: find the company ---
    matches = search_company(company_name_korean)
    if not matches:
        return f"[DART] No company found matching '{company_name_korean}'"

    company = matches[0]
    corp_code = company["corp_code"]
    corp_name = company["corp_name"]
    stock_code = company.get("stock_code", "N/A")

    lines = [
        f"=== DART Financial Context: {corp_name} ===",
        f"DART corp_code : {corp_code}",
        f"Stock code     : {stock_code}",
        "",
        "--- Financial Statements (KRW, millions) ---",
    ]

    # --- Step 2: financials per year ---
    for year in years:
        data = get_financials(corp_code, year)
        if "error" in data:
            lines.append(f"  {year}: {data['error']}")
            continue

        def _fmt(v):
            if v is None:
                return "N/A"
            try:
                return f"{int(v):,}"
            except (ValueError, TypeError):
                return str(v)

        lines.append(
            f"  {year}: Revenue {_fmt(data['revenue'])} | "
            f"Operating Profit {_fmt(data['operating_profit'])} | "
            f"Net Income {_fmt(data['net_income'])}"
        )

    # --- Step 3: recent disclosures ---
    disclosures = get_recent_disclosures(corp_code, limit=5)
    lines.append("")
    lines.append("--- Recent Disclosures (last 90 days) ---")

    if not disclosures:
        lines.append("  No recent disclosures found.")
    else:
        for d in disclosures:
            if "error" in d:
                lines.append(f"  Error: {d['error']}")
            else:
                lines.append(f"  [{d.get('date', '?')}] {d.get('title', '?')} — {d.get('url', '')}")

    lines.append("")
    return "\n".join(lines)


# --- Test block ---

if __name__ == "__main__":
    load_dotenv(dotenv_path=_ENV_PATH)

    print("Test 1: build_financial_context('삼성전자')")
    print("-" * 60)
    context = build_financial_context("삼성전자")
    print(context)

    print("\nTest 2: get_recent_disclosures for 삼성전자 (first 3)")
    print("-" * 60)
    # Samsung DART corp_code is 00126380
    matches = search_company("삼성전자")
    if matches:
        corp_code = matches[0]["corp_code"]
        print(f"corp_code: {corp_code}")
        disclosures = get_recent_disclosures(corp_code, limit=3)
        print(json.dumps(disclosures, ensure_ascii=False, indent=2))
    else:
        print("Company not found.")
