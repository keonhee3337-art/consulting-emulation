"""
Report Agent — synthesizes SQL results and RAG findings into a
structured markdown report. Final node in the LangGraph pipeline.
"""

import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are a senior strategy consultant generating a structured analysis report.
You have been given two inputs:
1. SQL query results from a structured financial database
2. RAG findings from financial analysis documents

Synthesize these into a clean markdown report with these sections:
## Key Findings
- Bullet points of the most important insights

## Financial Data Summary
- Present the SQL results in a readable format

## Market & Strategic Context
- Insights from the document retrieval

## Analyst Note
- One-sentence flag on data limitations or what additional analysis would strengthen this

Keep it concise. Use numbers. Avoid filler language.
Respond in the same language as the original question. If the question is in Korean, write the entire report in Korean."""


def run_report_agent(state: dict) -> dict:
    """LangGraph node: synthesize SQL + RAG results into a final report."""
    user_content = f"""Original question: {state['query']}

SQL Results:
{state.get('sql_result', 'No SQL results.')}

RAG Findings:
{state.get('rag_result', 'No RAG findings.')}

Generate the analysis report."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        temperature=0.4
    )

    report = response.choices[0].message.content.strip()
    return {**state, "report": report}
