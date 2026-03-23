"""
DART Live Data Pipeline
Fetches financial data and disclosures from DART (Korean FSS) using dart-fss.

API patterns confirmed against dart-fss installed version:
  - dart.get_corp_list() + find_by_corp_name(name, exactly=True) for search
  - corp.extract_fs(bgn_de, end_de, report_tp='annual') returns FinancialStatement
    * .extract_fs searches by FILING date, not fiscal year -- annual reports filed in year+1
    * ._statements['is'] is a pandas DataFrame with MultiIndex columns
    * Column level-0: 'YYYYMMDD-YYYYMMDD' (the fiscal period)
    * Column level-1: 'label_en', 'label_ko', 'concept_id', etc. for metadata
    * Values are in actual KRW (not millions) -- divide by 1_000_000 to normalize
  - dart.filings.search(corp_code, bgn_de, end_de) for disclosures

Windows note: cp949 terminal garbles Korean in print() -- this is cosmetic, data is correct.
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

import dart_fss as dart

# Load DARTFSS_API_KEY from .env.
# Korean characters in __file__ mangle on Windows when resolved via os.path,
# so we use the known absolute path directly and fall back to ".env" if moved.
_ENV_HARDCODED = (
    "c:/Users/keonh/OneDrive/바탕 화면/MCP_Agentic AI/.env"
)
_ENV_PATH = _ENV_HARDCODED if os.path.exists(_ENV_HARDCODED) else ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _init_dart():
    """Set the DART API key. Raises ValueError if not configured."""
    key = os.getenv("DARTFSS_API_KEY") or os.getenv("DART_API_KEY")
    if not key:
        raise ValueError(
            "DARTFSS_API_KEY not set. Add it to .env or Streamlit Cloud secrets."
        )
    dart.set_api_key(key)


def search_company(company_name_korean: str) -> list[dict]:
    """
    Search DART for a company by Korean name.

    Strategy: try exactly=True first (exact name match) -> fall back to
    exactly=False (substring match) if no exact result. This prevents
    'Samsung Electronics' from matching 'Samsung Electronics Service Energy'.

    Returns up to 10 matches, each with:
      - corp_code  : 8-digit DART identifier (used in other functions)
      - corp_name  : Korean company name
      - stock_code : KRX stock ticker (None for unlisted companies)
    """
    _init_dart()
    corp_list = dart.get_corp_list()

    # Prefer exact match
    results = corp_list.find_by_corp_name(company_name_korean, exactly=True)
    if not results:
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

    dart-fss extract_fs() takes a FILING date window, not a fiscal year.
    Korean companies file annual reports in Q1 of the following year, so:
      - To get FY2023 data -> search filings in 2024 (bgn_de='20240101', end_de='20241231')

    The returned FinancialStatement._statements['is'] is a pandas DataFrame
    with MultiIndex columns:
      - level-0: fiscal period string 'YYYYMMDD-YYYYMMDD'
      - level-1: 'label_en' for English account names, values in actual KRW

    We convert actual KRW to KRW millions (divide by 1_000_000) to match
    the FinAgent SQLite DB convention.

    Returns dict with: corp_code, year, revenue, operating_profit, net_income,
    currency ('KRW_millions'). Returns 'error' key on failure.
    """
    _init_dart()
    corp_list = dart.get_corp_list()
    corp = corp_list.find_by_corp_code(corp_code)

    if not corp:
        return {"error": f"No company found for corp_code={corp_code}"}

    # Annual reports are filed in year+1; search that filing window
    filing_year = year + 1
    bgn_de = f"{filing_year}0101"
    end_de = f"{filing_year}1231"

    try:
        fs = corp.extract_fs(
            bgn_de=bgn_de,
            end_de=end_de,
            report_tp="annual",
            progressbar=False,
        )
    except Exception as e:
        return {"error": f"extract_fs failed: {e}"}

    if fs is None or not hasattr(fs, "_statements"):
        return {"error": f"No financial data for corp_code={corp_code}, year={year}"}

    # Income statement preferred; fall back to balance sheet for revenue check
    is_df = fs._statements.get("is")
    if is_df is None or (hasattr(is_df, "empty") and is_df.empty):
        return {"error": f"Income statement empty for corp_code={corp_code}, year={year}"}

    # Find the column that covers fiscal year `year`
    # Column level-0 looks like '20230101-20231231'
    target_prefix = str(year)
    value_col = None
    for col in is_df.columns:
        col_key = col[0]  # e.g. '20230101-20231231'
        if isinstance(col_key, str) and col_key.startswith(target_prefix):
            value_col = col
            break

    if value_col is None:
        # No column matching target year found
        available = [c[0] for c in is_df.columns if isinstance(c[0], str) and "-" in c[0]]
        return {
            "error": f"No column for year {year}. Available periods: {available[:5]}"
        }

    # Find the statement header (level-0 of metadata columns)
    # Metadata columns have level-1 in ('label_en', 'label_ko', 'concept_id', ...)
    header = None
    for col in is_df.columns:
        if col[1] == "label_en":
            header = col[0]
            break

    if header is None:
        return {"error": "Could not locate label_en column in income statement"}

    label_col = (header, "label_en")

    # Account name substrings to match (English labels from XBRL)
    _REVENUE_KEYS = ("Revenue", "revenue", "Net sales", "Sales")
    _OP_PROFIT_KEYS = ("Operating profit", "Operating income", "operating profit")
    _NET_INCOME_KEYS = ("Profit for the year", "Net profit", "Net income",
                        "Profit attributable to owners")

    result = {
        "corp_code": corp_code,
        "year": year,
        "revenue": None,
        "operating_profit": None,
        "net_income": None,
        "currency": "KRW_millions",
    }

    def _to_millions(raw_val) -> int | None:
        if raw_val is None:
            return None
        try:
            v = float(str(raw_val).replace(",", ""))
            return int(v / 1_000_000)
        except (ValueError, TypeError):
            return None

    def _matches(label: str, keywords: tuple) -> bool:
        return any(kw.lower() in label.lower() for kw in keywords)

    for _, row in is_df.iterrows():
        label = str(row.get(label_col, ""))
        raw = row.get(value_col)
        if result["revenue"] is None and _matches(label, _REVENUE_KEYS):
            result["revenue"] = _to_millions(raw)
        elif result["operating_profit"] is None and _matches(label, _OP_PROFIT_KEYS):
            result["operating_profit"] = _to_millions(raw)
        elif result["net_income"] is None and _matches(label, _NET_INCOME_KEYS):
            result["net_income"] = _to_millions(raw)

    return result


def get_recent_disclosures(corp_code: str, limit: int = 5) -> list[dict]:
    """
    Fetch most recent DART disclosures for a company.

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

    # dart-fss SearchResults uses _report_list (not .list -- that attribute doesn't exist)
    if not filings or not hasattr(filings, "_report_list") or not filings._report_list:
        return []

    results = []
    for item in filings._report_list[:limit]:
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
    High-level function: search company -> fetch 3 years of financials -> format as context string.

    Designed for injection into the Report Agent system prompt or RAG context.

    Steps:
      1. search_company() -> pick first result (exact match preferred)
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
                lines.append(
                    f"  [{d.get('date', '?')}] {d.get('title', '?')} "
                    f"-- {d.get('url', '')}"
                )

    lines.append("")
    return "\n".join(lines)


# --- Test block ---

if __name__ == "__main__":
    import sys
    # Force UTF-8 output to avoid cp949 garbling in Windows terminal
    sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv(dotenv_path=_ENV_PATH)

    print("Test 1: build_financial_context('Samsung Electronics')")
    print("-" * 60)
    context = build_financial_context("삼성전자")
    print(context)

    print("\nTest 2: get_recent_disclosures for Samsung Electronics (first 3)")
    print("-" * 60)
    matches = search_company("삼성전자")
    if matches:
        corp_code = matches[0]["corp_code"]
        corp_name = matches[0]["corp_name"]
        print(f"Found: {corp_name} (corp_code: {corp_code})")
        disclosures = get_recent_disclosures(corp_code, limit=3)
        print(json.dumps(disclosures, ensure_ascii=False, indent=2))
    else:
        print("Company not found.")
