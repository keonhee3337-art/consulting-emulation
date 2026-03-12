"""
Supervisor Agent — Step 2.1 of Automated M&A Due Diligence & Strategy War Room.

Extends FinAgent's router with a 4th route (valuation) and wires three specialist
agents into a single LangGraph pipeline:

    supervisor_router
        ├─→ sql_agent      (sql_only)
        ├─→ rag_agent      (rag_only)
        ├─→ valuation_agent (valuation)  ← NEW
        └─→ sql_agent + rag_agent in parallel (both — via Send API if available)
              ↓
        report_agent → END

Routes:
    sql_only   — specific numbers, year-over-year comparisons, structured data
    rag_only   — qualitative analysis, strategy, narrative context
    valuation  — DCF, EV, enterprise value, "how much is X worth", investment thesis
    both       — requires structured data AND qualitative context together

State:
    SupervisorState extends FinAgent's AgentState with:
        - valuation_result: str  (output from ValuationAgent)
        - contexts: list[str]    (retrieved chunks, used by RAGAS evaluation)
"""

import os
from typing import TypedDict
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class SupervisorState(TypedDict):
    """
    Shared state object that flows through the full consulting pipeline.

    Extends FinAgent's AgentState with valuation_result and contexts.
    Every agent receives the full state and returns it with its output key added.
    """
    query: str              # Original user query
    route: str              # sql_only | rag_only | valuation | both
    sql_result: str         # Output from Text2SQL agent
    rag_result: str         # Output from RAG agent
    valuation_result: str   # Output from Valuation agent (DCF + comps)
    report: str             # Final synthesized report from Report agent
    contexts: list          # Retrieved document chunks — used by RAGAS eval pipeline


# ---------------------------------------------------------------------------
# Router system prompt — extended from FinAgent with valuation route
# ---------------------------------------------------------------------------

ROUTER_SYSTEM_PROMPT = """You are a query routing classifier for a financial analysis system.
Classify the user's question into exactly one of four categories:

- sql_only: The question asks for specific numbers, comparisons between years,
  revenue figures, operating profit, employees, or other structured data
  that can be answered directly from a financial database table.
  Examples: "What was Samsung's revenue in 2023?",
            "Compare operating profit of SK Hynix and LG from 2021 to 2024",
            "Which company had the highest net profit in 2022?"

- rag_only: The question asks for qualitative analysis, strategy, trends,
  explanations, or narrative context that requires document retrieval rather
  than raw numbers.
  Examples: "What drove SK Hynix's recovery?",
            "Explain the HBM opportunity for Korean chipmakers",
            "What is Samsung's competitive strategy?"

- valuation: The question asks for company valuation, DCF analysis, enterprise value,
  how much a company is worth, or investment thesis.
  Examples: "What is Samsung's valuation?",
            "Run a DCF for SK Hynix",
            "Is LG Electronics undervalued?",
            "What is the enterprise value of Samsung?",
            "Should we acquire SK Hynix — what's it worth?"

- both: The question requires both structured numbers AND qualitative context
  to answer well, but does NOT specifically ask for a formal valuation or DCF.
  Examples: "Analyze Samsung's revenue decline in 2023 and what caused it",
            "How does SK Hynix's financial performance relate to HBM demand?",
            "Compare financials and explain the strategic factors behind them"

Respond with ONLY one word: sql_only, rag_only, valuation, or both.
No explanation, no punctuation, no other text."""


# ---------------------------------------------------------------------------
# Supervisor router node
# ---------------------------------------------------------------------------

def run_supervisor_router(state: dict) -> dict:
    """
    LangGraph node: classify query and set state['route'].

    This node is the entry point of the consulting pipeline. It reads the user
    query and returns one of four routes: sql_only, rag_only, valuation, both.

    Defaults to 'both' on unexpected output (safe fallback — uses most context).
    """
    query = state["query"]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": query}
        ],
        temperature=0
    )

    raw = response.choices[0].message.content.strip().lower()

    valid_routes = ("sql_only", "rag_only", "valuation", "both")
    route = raw if raw in valid_routes else "both"

    # Initialize empty result keys so downstream nodes always find them in state
    return {
        **state,
        "route": route,
        "sql_result": state.get("sql_result", ""),
        "rag_result": state.get("rag_result", ""),
        "valuation_result": state.get("valuation_result", ""),
        "report": state.get("report", ""),
        "contexts": state.get("contexts", []),
    }


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def route_query(state: dict) -> str:
    """
    Conditional edge after supervisor_router.

    Returns the name of the next node based on state['route'].
    For 'both', attempts to use LangGraph Send API for parallel execution.
    The graph_builder handles Send; this function covers the non-parallel fallback.
    """
    route = state.get("route", "both")
    if route == "sql_only":
        return "sql_agent"
    elif route == "rag_only":
        return "rag_agent"
    elif route == "valuation":
        return "valuation_agent"
    else:
        # 'both' — sequential fallback: sql first, then rag (via route_after_sql)
        return "sql_agent"


def route_after_sql(state: dict) -> str:
    """
    Conditional edge after sql_agent.

    If route is 'both', continue to rag_agent.
    If route is 'sql_only', jump straight to report_agent.
    """
    route = state.get("route", "both")
    if route == "both":
        return "rag_agent"
    else:
        return "report_agent"


def route_to_parallel(state: dict):
    """
    Parallel fan-out for 'both' route using LangGraph Send API.

    Sends the same state to sql_agent and rag_agent concurrently.
    Used in graph_builder.py when the Send API is available.

    Returns a list of Send objects — LangGraph executes them in parallel
    and merges their state outputs before continuing to report_agent.
    """
    try:
        from langgraph.types import Send
        return [Send("sql_agent", state), Send("rag_agent", state)]
    except ImportError:
        # Older LangGraph without Send API — graph_builder falls back to sequential
        raise RuntimeError(
            "LangGraph Send API not available. "
            "graph_builder.py will use sequential fallback automatically."
        )
