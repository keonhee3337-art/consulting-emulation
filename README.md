# M&A Due Diligence Suite

**Agentic AI system that automates M&A financial analysis for Korean public companies — built to emulate the analytical stack used by MBB and Big4 consulting firms.**

> Built by [Keonhee Kim](https://github.com/keonhee3337-art) — Business Administration student at Sungkyunkwan University (SKKU), Korea.  
> Live API: `https://v7zapdvb10.execute-api.ap-northeast-2.amazonaws.com/`

---

## What It Does

A multi-agent AI pipeline that takes a natural language query — *"What is Samsung's intrinsic value?"* or *"Compare SK Hynix and Samsung profitability 2021–2024"* — and returns a structured financial analysis in seconds, including:

- **DCF valuation** (discounted cash flow with WACC = 10%, terminal growth = 2.5%)
- **Comparable company analysis** (EV/EBITDA comps across Samsung, SK Hynix, LG Electronics)
- **5-year revenue, operating profit, and net profit history** (live DART data)
- **XGBoost financial distress scoring**
- **Auto-generated PowerPoint deck** (consulting-style .pptx output)

Data source: Korea's DART public disclosure database (금융감독원 전자공시시스템) — the same data used by Korean investment banks and consulting firms.

---

## Architecture

```
User Query (natural language)
        │
        ▼
  Supervisor Agent  ─────────────────────────────────────┐
  (LangGraph StateGraph)                                  │
        │                                                  │
   Route decision                                         │
        │                                                  │
   ┌────▼──────────┬──────────────┬──────────────┐        │
   │               │              │              │        │
Text2SQL Agent  RAG Agent   Valuation Agent  Both        │
(SQLite +       (OpenAI      (DCF + EV/      (SQL +      │
DART pipeline)  embeddings + EBITDA comps +  RAG in      │
                cosine sim)  XGBoost)        parallel)   │
   └────┬──────────┴──────────────┴──────────────┘        │
        │                                                  │
        ▼                                                  │
  Report Agent ◄─────────────────────────────────────────┘
        │
        ▼
  Markdown report + PPTX deck
```

**Stack:** Python · LangGraph · RAG · Text2SQL · OpenAI GPT-4o · FastAPI · Streamlit · AWS Lambda · DART-FSS API · SQLite · XGBoost · python-pptx · Plotly

---

## Key Modules

| Module | Description |
|--------|-------------|
| `agents/supervisor.py` | LangGraph supervisor — classifies query intent, routes to specialist agents |
| `agents/valuation_agent.py` | DCF model + EV/EBITDA comparable company analysis for Korean equities |
| `agents/graph_builder.py` | Builds the LangGraph StateGraph with conditional edges and parallel execution |
| `data/dart_pipeline.py` | Live DART financial data ingestion — Samsung, SK Hynix, LG Electronics |
| `data/hybrid_search.py` | Hybrid retrieval: BM25 keyword search + dense OpenAI embeddings + RRF fusion |
| `models/distress_model.py` | XGBoost financial distress classifier trained on Korean company financial ratios |
| `eval/ragas_benchmark.py` | RAGAS evaluation pipeline — measures hallucination rate, context precision, answer relevancy |
| `output/pptx_generator.py` | Auto-generates 5-slide consulting deck from Report Agent output |
| `deploy/` | AWS Lambda deployment via CloudFormation (live in ap-northeast-2) |
| `app.py` | Streamlit dashboard — Plotly charts (grouped bar, margin trend, DCF waterfall, valuation comparison) |

---

## Why This Matters for Consulting AI Practices

Consulting firms like **McKinsey QuantumBlack**, **BCG Gamma**, and **Deloitte AI & Analytics** deploy agentic AI systems to automate exactly this type of work — financial document retrieval, valuation modeling, and structured report generation. This project demonstrates:

1. **Multi-agent orchestration** — LangGraph supervisor routing to specialist nodes, not a single LLM prompt
2. **Structured + unstructured retrieval** — Text2SQL for financial databases + RAG for qualitative documents
3. **Domain depth** — Korean DART data, Chaebol structure, WACC modeling for Korean equities
4. **Production deployment** — AWS Lambda API live, not just a local notebook
5. **Evaluation discipline** — RAGAS benchmark quantifies quality (hallucination rate, context precision)

---

## Deployment

| Environment | URL / Command |
|------------|---------------|
| AWS Lambda API (live) | `https://v7zapdvb10.execute-api.ap-northeast-2.amazonaws.com/` |
| Streamlit Cloud | `keonhee-duediligence.streamlit.app` |
| Local | `streamlit run app.py` |

**API example:**
```bash
curl -X POST https://v7zapdvb10.execute-api.ap-northeast-2.amazonaws.com/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Samsung Electronics intrinsic value based on DCF?"}'
```

---

## Setup

```bash
git clone https://github.com/keonhee3337-art/consulting-emulation
cd consulting-emulation
pip install -r requirements.txt
```

**Required environment variables** (`.env`):
```
OPENAI_API_KEY=your_key
DARTFSS_API_KEY=your_key   # from dart.fss.or.kr
```

**Run locally:**
```bash
streamlit run app.py
```

**Run pipeline directly:**
```bash
python run_pipeline.py "Compare Samsung and SK Hynix operating margins 2022-2024"
```

---

## Sample Queries

```
"What is Samsung Electronics' intrinsic value?"
"Compare SK Hynix and Samsung profitability 2021-2024"
"Explain the HBM opportunity for Korean chipmakers"
"What is SK Hynix's DCF valuation assuming 10% WACC?"
"Which Korean electronics company has the strongest balance sheet?"
```

---

## Evaluation (RAGAS)

RAGAS benchmark measures retrieval and generation quality across 15 test questions spanning all 4 route types (`sql_only`, `rag_only`, `valuation`, `both`).

```bash
python eval/ragas_benchmark.py
```

Metrics: Answer Relevancy, Faithfulness, Context Precision, Answer Correctness
Results saved to: `eval/ragas_results.json`

> Note: Runs ~15 OpenAI API calls. Cost: ~$0.05 per benchmark run.

---

## About the Author

**Keonhee Kim (김건희)** — Business Administration, Sungkyunkwan University (SKKU), South Korea.

Builds agentic AI systems with a focus on Korean market applications — financial data retrieval, multi-agent orchestration, and consulting workflow automation.

**Other projects:**
- [FinAgent](https://github.com/keonhee3337-art/FinAgent) — Multi-agent financial analysis system. LangGraph + custom VectorDB + Text2SQL. Live at keonhee-finagent.streamlit.app
- [DART MCP Server](https://github.com/keonhee3337-art/dart-mcp-server) — Custom MCP server exposing Korean DART financial data (search_company, get_financials, get_disclosures) to Claude and other LLM clients
- [AI Project Portfolio](https://github.com/keonhee3337-art/AI-project) — Samsung stock forecast (Prophet + Linear Regression), SQL analysis, AI chatbot

**Keywords:** `LangGraph` `agentic AI` `multi-agent system` `RAG` `Text2SQL` `Korean market` `DART financial data` `SKKU` `consulting AI` `BCG Gamma` `McKinsey QuantumBlack` `Deloitte AI` `financial analysis automation` `MCP server`
