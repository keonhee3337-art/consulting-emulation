"""
Run the full M&A Due Diligence pipeline from the CLI.

Usage:
    python run_pipeline.py "What is Samsung's valuation and strategic outlook?"
    python run_pipeline.py "What was SK Hynix's revenue in 2023?"
    python run_pipeline.py "Explain the HBM opportunity for Korean chipmakers"
    python run_pipeline.py "Analyze Samsung's revenue decline in 2023 and what caused it"

Routes (auto-detected by Supervisor):
    sql_only   -- structured financial data questions
    rag_only   -- qualitative / strategy questions
    valuation  -- DCF, EV, "how much is X worth"
    both       -- requires data + narrative context

Output:
    Prints the final report to stdout.
    The route classification is printed first so you can verify routing.
"""

import sys
import os

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Add FinAgent to path (must come before any FinAgent imports)
# ---------------------------------------------------------------------------
_LOCAL_FINAGENT = "c:/Users/keonh/OneDrive/바탕 화면/FinAgent"
_BUNDLED_FINAGENT = os.path.join(os.path.dirname(__file__), "finagent")
FINAGENT_PATH = os.environ.get(
    "FINAGENT_PATH",
    _LOCAL_FINAGENT if os.path.exists(_LOCAL_FINAGENT) else _BUNDLED_FINAGENT,
)
if FINAGENT_PATH not in sys.path:
    sys.path.insert(0, FINAGENT_PATH)

# ---------------------------------------------------------------------------
# Load env from FinAgent .env (contains OPENAI_API_KEY)
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv(os.path.join(FINAGENT_PATH, ".env"))

# ---------------------------------------------------------------------------
# Build and run
# ---------------------------------------------------------------------------
from agents.graph_builder import build_consulting_graph


def run(query: str) -> None:
    """Invoke the full pipeline for a given query and print the report."""
    print(f"\nQuery: {query}")
    print("-" * 60)

    graph = build_consulting_graph()
    result = graph.invoke({"query": query})

    report = result.get("report", "No report generated.")
    print(report)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py \"your query here\"")
        sys.exit(1)
    run(sys.argv[1])
