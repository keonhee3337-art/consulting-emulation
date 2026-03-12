"""
RAGAS Evaluation Pipeline — Step 2.4
Consulting Emulation Project: Automated M&A Due Diligence & Strategy War Room

Evaluates the FinAgent pipeline (Router → SQL → RAG → Report) against a
hardcoded 15-question benchmark using four RAGAS metrics:
  - answer_relevancy
  - faithfulness
  - context_precision
  - answer_correctness

Usage:
    pip install ragas datasets python-dotenv
    python eval/ragas_benchmark.py

Results are printed as a scorecard and saved to eval/ragas_results.json.
"""

import sys
import os
import json
import traceback

# ---------------------------------------------------------------------------
# 0. Dependency check — fail fast with a useful message if ragas is missing
# ---------------------------------------------------------------------------
try:
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        faithfulness,
        context_precision,
        answer_correctness,
    )
    from datasets import Dataset
except ImportError:
    print(
        "\n[ERROR] Missing dependencies.\n"
        "Install with:\n\n"
        "    pip install ragas datasets python-dotenv\n"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# 1. Load environment — OPENAI_API_KEY from FinAgent .env
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

FINAGENT_DIR = r"c:/Users/keonh/OneDrive/바탕 화면/FinAgent"
load_dotenv(os.path.join(FINAGENT_DIR, ".env"))

if not os.getenv("OPENAI_API_KEY"):
    print(
        "\n[ERROR] OPENAI_API_KEY not found.\n"
        f"Expected .env at: {FINAGENT_DIR}/.env\n"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Wire FinAgent onto sys.path so its modules are importable
# ---------------------------------------------------------------------------
if FINAGENT_DIR not in sys.path:
    sys.path.insert(0, FINAGENT_DIR)

# ---------------------------------------------------------------------------
# 3. Benchmark dataset — 15 Q&A pairs across all three route types
# ---------------------------------------------------------------------------
BENCHMARK = [
    # --- SQL-only (structured financial data queries) ---
    {
        "question": "What was Samsung Electronics' revenue in 2023?",
        "ground_truth": (
            "Samsung Electronics reported total revenue (sales) of approximately "
            "258.94 trillion KRW in 2023, a decline from 2022 due to weak semiconductor demand."
        ),
        "type": "sql",
    },
    {
        "question": "Which company had the highest net profit in 2022?",
        "ground_truth": (
            "Samsung Electronics had the highest net profit among major Korean companies in 2022, "
            "driven by strong semiconductor and memory sales before the downturn."
        ),
        "type": "sql",
    },
    {
        "question": "Compare SK Hynix and Samsung operating profit from 2021 to 2023.",
        "ground_truth": (
            "Samsung Electronics maintained positive operating profit across 2021-2023, "
            "while SK Hynix swung to an operating loss in 2023 due to the memory chip downturn. "
            "Both companies suffered from falling DRAM and NAND prices in 2022-2023."
        ),
        "type": "sql",
    },
    {
        "question": "What was SK Hynix's operating profit margin in 2022?",
        "ground_truth": (
            "SK Hynix had a positive operating profit margin in 2022 before swinging to a "
            "significant operating loss in 2023 as memory prices collapsed."
        ),
        "type": "sql",
    },
    {
        "question": "What was Samsung's net income in 2021?",
        "ground_truth": (
            "Samsung Electronics reported net income of approximately 39.9 trillion KRW in 2021, "
            "a strong year driven by semiconductor demand and display businesses."
        ),
        "type": "sql",
    },
    # --- RAG-only (document retrieval / analyst report queries) ---
    {
        "question": "What drove SK Hynix's recovery in 2024?",
        "ground_truth": (
            "SK Hynix's 2024 recovery was primarily driven by surging demand for HBM "
            "(High Bandwidth Memory) used in AI accelerators and data center GPUs. "
            "SK Hynix secured a dominant position supplying HBM3e to Nvidia, commanding "
            "premium pricing and restoring margins."
        ),
        "type": "rag",
    },
    {
        "question": "Explain the HBM opportunity for Korean chipmakers.",
        "ground_truth": (
            "HBM (High Bandwidth Memory) is a high-performance memory stack required for "
            "AI training and inference GPUs. Korean chipmakers SK Hynix and Samsung dominate "
            "DRAM production and are the primary HBM suppliers globally. SK Hynix leads with "
            "HBM3e supply to Nvidia; Samsung is qualifying HBM3e for additional customers. "
            "The AI infrastructure buildout creates a multi-year demand tailwind."
        ),
        "type": "rag",
    },
    {
        "question": "What is Samsung's competitive strategy in semiconductors?",
        "ground_truth": (
            "Samsung's semiconductor strategy centers on vertical integration across logic "
            "(System LSI), memory (DRAM, NAND), and foundry (Samsung Foundry). "
            "Key strategic pillars: maintain memory cost leadership, close the HBM gap with "
            "SK Hynix, and grow advanced foundry (3nm GAA) to compete with TSMC. "
            "Samsung also invests heavily in next-generation packaging."
        ),
        "type": "rag",
    },
    {
        "question": "What are the key risks facing Korean semiconductor companies in 2024?",
        "ground_truth": (
            "Key risks include US-China tech restrictions limiting sales to Chinese customers, "
            "potential HBM supply glut if AI capex slows, geopolitical risks around Taiwan, "
            "and intensifying foundry competition from TSMC and Intel Foundry Services."
        ),
        "type": "rag",
    },
    {
        "question": "How does LG Electronics generate revenue across its business segments?",
        "ground_truth": (
            "LG Electronics generates revenue across four segments: Home Appliance & Air Solution "
            "(H&A), Home Entertainment (HE), Vehicle Component Solutions (VS), and Business Solutions (BS). "
            "H&A is the largest and most profitable segment; VS is the fastest growing due to EV demand."
        ),
        "type": "rag",
    },
    # --- Both (queries needing SQL data + document context) ---
    {
        "question": "Analyze Samsung's revenue decline in 2023 and what caused it.",
        "ground_truth": (
            "Samsung's 2023 revenue declined approximately 14% year-over-year to around "
            "258.94 trillion KRW. The primary causes were: (1) a global memory chip oversupply "
            "cycle that caused DRAM and NAND prices to collapse by 40-60%, (2) weakened "
            "consumer electronics demand post-pandemic, and (3) inventory corrections by "
            "major customers including hyperscalers and smartphone OEMs."
        ),
        "type": "both",
    },
    {
        "question": "How does SK Hynix's financial performance relate to HBM demand?",
        "ground_truth": (
            "SK Hynix's 2023 operating loss of approximately 7.7 trillion KRW contrasts sharply "
            "with its rapid recovery in 2024, directly tied to HBM3 and HBM3e ramp for Nvidia. "
            "HBM commands 5-8x the ASP of conventional DRAM, allowing SK Hynix to restore "
            "gross margins even with lower total volume. Financial recovery is structurally "
            "linked to AI infrastructure investment cycles."
        ),
        "type": "both",
    },
    {
        "question": "Is Samsung Electronics undervalued relative to its earnings power?",
        "ground_truth": (
            "Samsung trades at a significant discount to TSMC and other global semis on "
            "EV/EBITDA and P/E metrics, partly reflecting the 'Korea discount' (governance risk, "
            "conglomerate structure) and foundry execution uncertainty. Its normalized earnings "
            "power — assuming memory cycle recovery and HBM ramp — would suggest the current "
            "valuation is conservative."
        ),
        "type": "both",
    },
    {
        "question": "Compare Samsung and SK Hynix profitability in 2023 and explain the gap.",
        "ground_truth": (
            "In 2023, Samsung posted an operating profit of approximately 6.57 trillion KRW "
            "while SK Hynix recorded an operating loss of approximately 7.73 trillion KRW. "
            "The gap reflects Samsung's diversification — consumer electronics, displays, and "
            "foundry partially offset semiconductor losses — whereas SK Hynix is a pure-play "
            "memory company with no such hedge."
        ),
        "type": "both",
    },
    {
        "question": "What capital allocation decisions should Samsung prioritize given its 2023 results?",
        "ground_truth": (
            "Given 2023's depressed earnings, Samsung should prioritize: (1) accelerating HBM "
            "capacity investment to close the SK Hynix lead, (2) rationalizing foundry capex "
            "until yield rates improve at 3nm, (3) maintaining shareholder returns to defend "
            "valuation, and (4) investing in next-gen packaging (2.5D/3D) as a differentiation "
            "vector against pure DRAM commoditization."
        ),
        "type": "both",
    },
]

# ---------------------------------------------------------------------------
# 4. Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(question: str, thread_id: str) -> dict:
    """
    Invoke the FinAgent LangGraph pipeline for a single question.

    Returns:
        {
            "answer": str,       # state["report"]
            "contexts": [str],   # retrieved context(s) used for generation
        }

    On failure, returns {"answer": "", "contexts": [], "error": str}.
    """
    from agent.graph import build_graph  # imported here to defer until after sys.path setup

    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    state = graph.invoke({"query": question}, config=config)

    answer = state.get("report", "")
    route = state.get("route", "both")

    # Build context list — RAGAS expects a list of strings per question
    contexts = []
    if route in ("rag_only", "both"):
        rag_ctx = state.get("rag_result", "")
        if rag_ctx:
            contexts.append(rag_ctx)
    if route in ("sql_only", "both"):
        sql_ctx = state.get("sql_result", "")
        if sql_ctx:
            contexts.append(sql_ctx)

    # Fallback: if no context captured, use the answer itself
    if not contexts:
        contexts = [answer] if answer else ["No context retrieved."]

    return {"answer": answer, "contexts": contexts}


# ---------------------------------------------------------------------------
# 5. Collect pipeline outputs for all benchmark questions
# ---------------------------------------------------------------------------

def collect_results(benchmark: list) -> tuple[list, list]:
    """
    Run each benchmark question through the pipeline.

    Returns:
        (ragas_rows, per_question_records)

    ragas_rows: list of dicts ready for datasets.Dataset
    per_question_records: list of dicts including errors, for JSON output
    """
    ragas_rows = []
    per_question_records = []

    total = len(benchmark)
    for i, item in enumerate(benchmark):
        question = item["question"]
        ground_truth = item["ground_truth"]
        q_type = item["type"]
        thread_id = f"eval-{i}"

        print(f"[{i+1}/{total}] Running: {question[:70]}...")

        record = {
            "index": i,
            "question": question,
            "ground_truth": ground_truth,
            "type": q_type,
            "thread_id": thread_id,
        }

        try:
            result = run_pipeline(question, thread_id)
            answer = result["answer"]
            contexts = result["contexts"]

            record["answer"] = answer
            record["contexts"] = contexts
            record["error"] = None

            ragas_rows.append({
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": ground_truth,
            })

            print(f"  -> OK (answer length: {len(answer)} chars, contexts: {len(contexts)})")

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            print(f"  -> FAILED: {error_msg}")
            traceback.print_exc()
            record["answer"] = ""
            record["contexts"] = []
            record["error"] = error_msg

        per_question_records.append(record)

    return ragas_rows, per_question_records


# ---------------------------------------------------------------------------
# 6. RAGAS evaluation
# ---------------------------------------------------------------------------

METRICS = [
    answer_relevancy,
    faithfulness,
    context_precision,
    answer_correctness,
]

METRIC_NAMES = [
    "answer_relevancy",
    "faithfulness",
    "context_precision",
    "answer_correctness",
]


def run_ragas(ragas_rows: list) -> dict:
    """
    Build a HuggingFace Dataset from ragas_rows and call ragas.evaluate().
    Returns a dict of metric_name -> float score.
    """
    if not ragas_rows:
        print("\n[WARNING] No successful pipeline results to evaluate.")
        return {name: None for name in METRIC_NAMES}

    dataset = Dataset.from_list(ragas_rows)
    results = evaluate(dataset, metrics=METRICS)

    scores = {}
    for name in METRIC_NAMES:
        scores[name] = float(results[name]) if results[name] is not None else None

    return scores


# ---------------------------------------------------------------------------
# 7. Scorecard printer
# ---------------------------------------------------------------------------

def print_scorecard(scores: dict) -> None:
    valid_scores = [v for v in scores.values() if v is not None]
    overall = sum(valid_scores) / len(valid_scores) if valid_scores else None

    print("\n" + "=" * 42)
    print("RAGAS Evaluation Results")
    print("=" * 42)
    print(f"{'Metric':<28} {'Score':>8}")
    print("-" * 38)
    for name, score in scores.items():
        display = f"{score:.4f}" if score is not None else "N/A"
        print(f"{name:<28} {display:>8}")
    print("-" * 38)
    overall_display = f"{overall:.4f}" if overall is not None else "N/A"
    print(f"{'Overall Score':<28} {overall_display:>8}")
    print("=" * 42 + "\n")


# ---------------------------------------------------------------------------
# 8. Save results to JSON
# ---------------------------------------------------------------------------

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__),
    "ragas_results.json",
)


def save_results(scores: dict, per_question_records: list) -> None:
    valid_scores = [v for v in scores.values() if v is not None]
    overall = sum(valid_scores) / len(valid_scores) if valid_scores else None

    output = {
        "summary": {
            **scores,
            "overall_score": overall,
        },
        "per_question": per_question_records,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Full results saved to: {OUTPUT_PATH}")


# ---------------------------------------------------------------------------
# 9. Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nFinAgent RAGAS Evaluation Pipeline")
    print(f"Benchmark: {len(BENCHMARK)} questions")
    print(f"FinAgent path: {FINAGENT_DIR}\n")

    # Step 1: Run pipeline for all benchmark questions
    ragas_rows, per_question_records = collect_results(BENCHMARK)

    successful = len(ragas_rows)
    failed = len(per_question_records) - successful
    print(f"\nPipeline complete: {successful} succeeded, {failed} failed.")

    if failed > 0:
        print("Failed questions:")
        for r in per_question_records:
            if r.get("error"):
                print(f"  [{r['index']+1}] {r['question'][:60]}... -> {r['error']}")

    # Step 2: RAGAS evaluation
    print("\nRunning RAGAS evaluation (this calls OpenAI API)...")
    scores = run_ragas(ragas_rows)

    # Step 3: Output
    print_scorecard(scores)
    save_results(scores, per_question_records)
