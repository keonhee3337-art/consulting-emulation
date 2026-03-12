"""
Router Agent — classifies the user query and sets state["route"].

Routes:
  - "sql_only"  — structured numbers: comparisons, specific years, revenue figures
  - "rag_only"  — narrative/conceptual: trends, strategy, qualitative
  - "both"      — requires both structured data and narrative context
"""

import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are a query routing classifier for a financial analysis system.
Classify the user's question into exactly one of three categories:

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

- both: The question requires both structured numbers AND qualitative context
  to answer well.
  Examples: "Analyze Samsung's revenue decline in 2023 and what caused it",
            "How does SK Hynix's financial performance relate to HBM demand?",
            "Compare financials and explain the strategic factors behind them"

Respond with ONLY one word: sql_only, rag_only, or both.
No explanation, no punctuation, no other text."""


def run_router_agent(state: dict) -> dict:
    """LangGraph node: classify query and set state['route']."""
    query = state["query"]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query}
        ],
        temperature=0
    )

    raw = response.choices[0].message.content.strip().lower()

    # Validate and normalise — default to "both" if unexpected output
    if raw in ("sql_only", "rag_only", "both"):
        route = raw
    else:
        route = "both"

    return {**state, "route": route}
