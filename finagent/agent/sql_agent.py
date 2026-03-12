"""
Text2SQL Agent — converts natural language to SQL, runs it against SQLite,
and returns structured financial data.
"""

import sqlite3
import os
from openai import OpenAI

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/financial.db")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCHEMA = """
Table: financials
Columns:
  - id (INTEGER)
  - company (TEXT) — values: 'Samsung Electronics', 'SK Hynix', 'LG Electronics'
  - year (INTEGER) — range: 2020 to 2024
  - revenue_billion_krw (REAL)
  - operating_profit_billion_krw (REAL)
  - net_profit_billion_krw (REAL)
  - capex_billion_krw (REAL)
  - employees (INTEGER)
"""

SYSTEM_PROMPT = f"""You are a Text2SQL agent for a Korean corporate financial database.
Convert the user's question into a valid SQLite SQL query.

{SCHEMA}

Rules:
- Return ONLY the SQL query, no explanation, no markdown, no backticks.
- Use exact column names from the schema above.
- For company names, match exactly as shown (e.g. 'Samsung Electronics').
- If the question is not answerable from this schema, return: SELECT 'N/A' AS result;
"""


def run_sql_agent(state: dict) -> dict:
    """LangGraph node: convert query to SQL and execute it."""
    query = state["query"]

    # Step 1: Generate SQL from natural language
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query}
        ],
        temperature=0
    )
    sql = response.choices[0].message.content.strip()

    # Step 2: Execute SQL against SQLite (read-only — prevents injection from LLM output)
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()

        if rows:
            # Format as readable table
            header = " | ".join(columns)
            separator = "-" * len(header)
            data_rows = [" | ".join(str(v) for v in row) for row in rows]
            result = f"SQL: {sql}\n\nResults:\n{header}\n{separator}\n" + "\n".join(data_rows)
        else:
            result = f"SQL: {sql}\n\nResults: No matching records found."

    except Exception as e:
        result = f"SQL generation succeeded but execution failed: {e}\nGenerated SQL: {sql}"

    return {**state, "sql_result": result}
