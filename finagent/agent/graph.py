"""
LangGraph orchestration — defines the multi-agent pipeline as a directed graph.

Flow (dynamic routing):
  router_agent classifies the query, then:
    - sql_only  → sql_agent → report_agent → END
    - rag_only  → rag_agent → report_agent → END
    - both      → sql_agent → rag_agent   → report_agent → END

Each node is a function that takes the full state dict and returns an updated state dict.
State passes between agents — each agent adds its output key and forwards everything downstream.

Checkpointing:
  Uses Postgres (Supabase) if SUPABASE_DB_URL is set, otherwise falls back to MemorySaver.
  Each Streamlit session gets a unique thread_id — state persists within the session.
"""

import os
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.router_agent import run_router_agent
from agent.sql_agent import run_sql_agent
from agent.rag_agent import run_rag_agent
from agent.report_agent import run_report_agent


def _get_checkpointer():
    """Return Postgres checkpointer if SUPABASE_DB_URL is set, else MemorySaver."""
    db_url = os.getenv("SUPABASE_DB_URL")
    if db_url:
        try:
            from psycopg_pool import ConnectionPool
            from langgraph.checkpoint.postgres import PostgresSaver
            pool = ConnectionPool(db_url, max_size=5)
            checkpointer = PostgresSaver(pool)
            checkpointer.setup()
            print("Checkpointer: Postgres (Supabase)")
            return checkpointer
        except Exception as e:
            print(f"Postgres checkpointer failed ({e}) -- falling back to MemorySaver")
    print("Checkpointer: MemorySaver (in-session memory only)")
    return MemorySaver()


class AgentState(TypedDict):
    """Shared state object that flows through the entire pipeline."""
    query: str           # Original user query
    sql_result: str      # Output from Text2SQL agent
    rag_result: str      # Output from RAG agent
    report: str          # Final synthesized report
    route: str           # Route classification: sql_only | rag_only | both


def route_query(state: dict) -> str:
    """Conditional edge function: read state['route'] and return the next node name."""
    route = state.get("route", "both")
    if route == "sql_only":
        return "sql_agent"
    elif route == "rag_only":
        return "rag_agent"
    else:
        return "sql_agent"  # "both" — sql first, then rag (via edge)


def route_after_sql(state: dict) -> str:
    """After sql_agent: go to rag_agent only if route is 'both', else go to report_agent."""
    route = state.get("route", "both")
    if route == "both":
        return "rag_agent"
    else:
        return "report_agent"


def build_graph():
    """Build and compile the LangGraph multi-agent pipeline with dynamic routing."""
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("router_agent", run_router_agent)
    workflow.add_node("sql_agent", run_sql_agent)
    workflow.add_node("rag_agent", run_rag_agent)
    workflow.add_node("report_agent", run_report_agent)

    # Entry point: always start with the router
    workflow.set_entry_point("router_agent")

    # Router → sql_agent or rag_agent based on classification
    workflow.add_conditional_edges(
        "router_agent",
        route_query,
        {
            "sql_agent": "sql_agent",
            "rag_agent": "rag_agent",
        }
    )

    # sql_agent → rag_agent (if both) or report_agent (if sql_only)
    workflow.add_conditional_edges(
        "sql_agent",
        route_after_sql,
        {
            "rag_agent": "rag_agent",
            "report_agent": "report_agent",
        }
    )

    # rag_agent always converges to report_agent
    workflow.add_edge("rag_agent", "report_agent")

    # report_agent → END
    workflow.add_edge("report_agent", END)

    return workflow.compile(checkpointer=_get_checkpointer())
