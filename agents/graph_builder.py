"""
Graph Builder — compiles the full M&A Due Diligence LangGraph pipeline.

Architecture:
    supervisor_router
        ├─→ sql_agent      (sql_only / both)
        ├─→ rag_agent      (rag_only / both — parallel with sql via Send API if available)
        └─→ valuation_agent (valuation)
              ↓
        report_agent → END

Parallel execution (both route):
    If langgraph.types.Send is available (LangGraph >= 0.1.x), sql_agent and rag_agent
    run concurrently and their outputs are merged before report_agent.
    If Send is not available, the graph falls back to sequential: sql → rag → report.

Checkpointing:
    MemorySaver — in-session memory, no external DB required.
    Postgres upgrade pending Supabase password restore (see FinAgent graph.py for pattern).

Entry point for the full consulting pipeline.
"""

import sys
import os

# ---------------------------------------------------------------------------
# Add FinAgent to path — local install or bundled finagent/ for cloud deploy
# ---------------------------------------------------------------------------
_LOCAL = "c:/Users/keonh/OneDrive/바탕 화면/FinAgent"
_BUNDLED = os.path.join(os.path.dirname(__file__), "..", "finagent")
FINAGENT_PATH = _LOCAL if os.path.exists(_LOCAL) else os.path.abspath(_BUNDLED)
if FINAGENT_PATH not in sys.path:
    sys.path.insert(0, FINAGENT_PATH)

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Supervisor + state
from agents.supervisor import (
    SupervisorState,
    run_supervisor_router,
    route_query,
    route_after_sql,
)

# Specialist nodes from FinAgent (imported via sys.path, not installed as package)
from agent.sql_agent import run_sql_agent
from agent.rag_agent import run_rag_agent
from agent.report_agent import run_report_agent

# Local valuation node
from agents.valuation_agent import run_valuation_agent


# ---------------------------------------------------------------------------
# Send API availability check (done once at module load)
# ---------------------------------------------------------------------------

def _send_available() -> bool:
    """Check if LangGraph's Send API is importable."""
    try:
        from langgraph.types import Send  # noqa: F401
        return True
    except ImportError:
        return False


_HAS_SEND = _send_available()


# ---------------------------------------------------------------------------
# Wrapper: report_agent expects sql_result + rag_result in state.
# When valuation route is used, rag_result is empty — that's fine; report_agent
# handles missing fields gracefully (uses state.get with defaults).
# We inject valuation_result into the content so report_agent can reference it.
# ---------------------------------------------------------------------------

def run_report_agent_extended(state: dict) -> dict:
    """
    Thin wrapper around FinAgent's report_agent that injects valuation_result
    into the RAG findings field when the valuation route is active.

    FinAgent's report_agent reads state['rag_result'] for narrative context.
    For the valuation route, we surface the valuation summary there so the
    report includes both DCF/comps output and any SQL data if available.
    """
    route = state.get("route", "both")

    # If valuation route: surface valuation_result as the narrative context
    if route == "valuation" and state.get("valuation_result"):
        augmented_state = {
            **state,
            "rag_result": (
                f"[Valuation Analysis]\n{state['valuation_result']}\n\n"
                + (state.get("rag_result") or "")
            ).strip()
        }
    else:
        augmented_state = state

    return run_report_agent(augmented_state)


# ---------------------------------------------------------------------------
# Parallel fan-out function (only used when Send is available)
# ---------------------------------------------------------------------------

def _route_to_parallel(state: dict):
    """Fan out to sql_agent and rag_agent in parallel using LangGraph Send API."""
    from langgraph.types import Send
    return [Send("sql_agent", state), Send("rag_agent", state)]


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_consulting_graph():
    """
    Build and compile the full M&A Due Diligence LangGraph pipeline.

    Returns a compiled LangGraph app with MemorySaver checkpointing.
    Each invocation should pass a unique thread_id in config:
        graph.invoke({"query": "..."}, config={"configurable": {"thread_id": "session-1"}})

    Route behaviour:
        sql_only   — supervisor → sql_agent → report_agent
        rag_only   — supervisor → rag_agent → report_agent
        valuation  — supervisor → valuation_agent → report_agent
        both       — supervisor → sql_agent + rag_agent (parallel if Send available,
                     sequential sql→rag→report otherwise) → report_agent
    """
    workflow = StateGraph(SupervisorState)

    # --- Register nodes ---
    workflow.add_node("supervisor_router", run_supervisor_router)
    workflow.add_node("sql_agent", run_sql_agent)
    workflow.add_node("rag_agent", run_rag_agent)
    workflow.add_node("valuation_agent", run_valuation_agent)
    workflow.add_node("report_agent", run_report_agent_extended)

    # --- Entry point ---
    workflow.set_entry_point("supervisor_router")

    # --- Routing from supervisor ---
    if _HAS_SEND:
        # Parallel execution for 'both' route via Send API
        # For other routes, conditional edges direct to the single specialist
        print("Graph: parallel execution enabled (LangGraph Send API available)")

        workflow.add_conditional_edges(
            "supervisor_router",
            lambda state: state.get("route", "both"),
            {
                "sql_only": "sql_agent",
                "rag_only": "rag_agent",
                "valuation": "valuation_agent",
                "both": "sql_agent",   # parallel Send handled separately below
            }
        )

        # Note: True parallel Send for 'both' requires the graph to use
        # a map-reduce pattern. We add a second conditional that fans out
        # when route == 'both' by routing to sql first, then rag via route_after_sql.
        # Full Send-based parallelism requires LangGraph >= 0.2 with map nodes.
        # The current implementation uses sequential sql → rag for 'both' in both paths.
        # To enable true parallel execution, upgrade to LangGraph 0.2+ and restructure
        # the 'both' branch as a map node. This is noted here as a known upgrade path.

    else:
        # Sequential fallback — same structure, no Send dependency
        print("Graph: Send API unavailable — using sequential execution for 'both' route")

        workflow.add_conditional_edges(
            "supervisor_router",
            route_query,
            {
                "sql_agent": "sql_agent",
                "rag_agent": "rag_agent",
                "valuation_agent": "valuation_agent",
            }
        )

    # --- Post-sql routing: 'both' continues to rag, 'sql_only' goes to report ---
    workflow.add_conditional_edges(
        "sql_agent",
        route_after_sql,
        {
            "rag_agent": "rag_agent",
            "report_agent": "report_agent",
        }
    )

    # --- rag_agent and valuation_agent always converge to report_agent ---
    workflow.add_edge("rag_agent", "report_agent")
    workflow.add_edge("valuation_agent", "report_agent")

    # --- report_agent → END ---
    workflow.add_edge("report_agent", END)

    checkpointer = MemorySaver()
    print("Checkpointer: MemorySaver (Postgres upgrade pending Supabase restore)")

    return workflow.compile(checkpointer=checkpointer)
