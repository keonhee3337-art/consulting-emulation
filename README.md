# Automated M&A Due Diligence & Strategy War Room

**Status:** Planning — not started
**Created:** 2026-03-12
**Origin:** Gemini-authored concept on Notion; expanded here

---

## What This Is

An agentic AI system that emulates the internal analytical stack of MBB and Big4 firms — specifically the tools used in M&A due diligence, financial analysis, and strategy work. Built on the FinAgent foundation, upgraded to consulting-grade.

**Signal value:** Shows firms you understand *what they actually use internally* — not just that you've built a chatbot.

---

## Architecture Overview

```
User Query
    ↓
Supervisor Agent (LangGraph)
    ├─→ Text2SQL Agent     ← DART + SQLite financial data
    ├─→ GraphRAG Agent     ← Neo4j: Chaebol cross-shareholding
    └─→ Valuation Agent   ← DCF + Comparable Company Analysis
            ↓
    Report Agent → pptx + Markdown
```

---

## 3-Phase Build Plan

### Phase 1: Enterprise Data Pipeline
**Goal:** Production-grade data layer — not just SQLite

| Step | Task | Time | Notes |
|------|------|------|-------|
| 1.1 | DART API full integration — replace mock data with live `search_company` + `get_financials` | 3h | DART MCP already built; wire into FinAgent |
| 1.2 | Hybrid search: add BM25 keyword layer alongside existing dense embeddings | 4h | `rank_bm25` library; re-rank with RRF (Reciprocal Rank Fusion) |
| 1.3 | Neo4j local install + Chaebol graph schema | 5h | Samsung → subsidiaries → cross-holdings. Cypher query intro |
| 1.4 | Entity extraction: LLM reads DART disclosures → extracts entities → populates Neo4j | 4h | spaCy + GPT-4o extraction prompt |
| 1.5 | Data validation layer — schema checks, null handling, logging | 2h | Prevents silent failures in production |

**Phase 1 subtotal: ~18 hours**

---

### Phase 2: Advanced Orchestration (LangGraph)
**Goal:** Multi-agent supervisor routing with specialized nodes

| Step | Task | Time | Notes |
|------|------|------|-------|
| 2.1 | Supervisor Agent — extends FinAgent router; routes to 3 specialists | 3h | `Command` object + conditional edges |
| 2.2 | GraphRAG Agent — Cypher query generation from natural language | 5h | LLM writes Cypher → executes on Neo4j → formats result |
| 2.3 | Valuation Agent — DCF model + Comparable Company Analysis | 6h | Python financials: WACC, terminal value, EV/EBITDA comps |
| 2.4 | RAGAS evaluation pipeline — hallucination rate, context precision, answer relevance | 4h | `ragas` library; run on 20 benchmark questions |
| 2.5 | LangGraph Send API — parallel SQL+RAG+Graph execution | 3h | Cuts latency; shows you know advanced LangGraph |
| 2.6 | Memory / checkpointing — Postgres (Supabase) for conversation history | 2h | Already wired in FinAgent; restore Supabase first |

**Phase 2 subtotal: ~23 hours**

---

### Phase 3: Enterprise Output & Deployment
**Goal:** Consulting-quality outputs + cloud deployment

| Step | Task | Time | Notes |
|------|------|------|-------|
| 3.1 | python-pptx report generation — auto-generate slide deck from Report Agent output | 4h | Template: title, key findings, data table, rec slide |
| 3.2 | FastAPI backend — wrap full pipeline as REST API | 3h | Already exists in FinAgent; extend to new agents |
| 3.3 | React/Next.js frontend — replace Streamlit (optional; highest resume lift) | 10h | Vercel deploy; shows full-stack capability |
| 3.4 | AWS Lambda + API Gateway deploy OR Docker + EC2 | 6h | Use `references/consulting/aws-quickstart.md` |
| 3.5 | GitHub Actions CI/CD — auto-test + redeploy on push | 3h | `.github/workflows/deploy.yml` |
| 3.6 | Security layer — API key auth, input sanitization, rate limiting | 2h | FastAPI `HTTPBearer` + middleware |

**Phase 3 subtotal: ~28 hours**

---

### Phase 4: Gaps That Matter to Firms (do these before interviews)
**Goal:** Close the deficiencies Gemini flagged — each one is an interview talking point

| Step | Task | Time | Priority |
|------|------|------|----------|
| 4.1 | RBAC / Row-Level Security — Supabase RLS for engagement ring-fencing | 2h | Deloitte, Accenture |
| 4.2 | Audit logging — who queried what, when (compliance demo) | 2h | McKinsey, BCG |
| 4.3 | XGBoost financial distress prediction — complement LLM with traditional ML | 4h | All firms: shows ML breadth |
| 4.4 | PII masking — scrub personal data from documents before vectorizing | 2h | Enterprise security narrative |
| 4.5 | RAGAS benchmark report — publish score card in README | 1h | Concrete evaluation = rare at student level |

**Phase 4 subtotal: ~11 hours**

---

## Total Time Estimate

| Phase | Hours |
|-------|-------|
| Phase 1: Data Pipeline | 18h |
| Phase 2: Orchestration | 23h |
| Phase 3: Output & Deploy | 28h |
| Phase 4: Firm-Specific Gaps | 11h |
| **Total** | **~80 hours** |

Realistic pace: 4h/day = **20 working days**. Can stop at Phase 2 and still have a strong resume artifact.

**Minimum viable version for resume (Phases 1+2 only): ~41 hours / 10 days**

---

## Resume Impact by Target Firm

| Firm | Fit Before | Fit After Full Build | Key Signal |
|------|-----------|---------------------|------------|
| **Deloitte Korea AI** | 80% | 92% | RAGAS eval + RBAC + Supabase RLS = enterprise AI governance narrative. Exact match for their AI audit and data governance practice. |
| **Accenture Song/AI** | 78% | 90% | React/Next.js + FastAPI + CI/CD shows full-stack delivery. pptx auto-generation = client-ready output, which Accenture emphasizes. |
| **McKinsey QuantumBlack** | 72% | 87% | Hybrid search + GraphRAG + XGBoost = quant-heavy AI stack. Audit logging + evaluation pipeline = production discipline. |
| **BCG Gamma** | 70% | 85% | DCF Valuation Agent + Chaebol Neo4j graph = domain depth. Supervisor + parallel execution = QuantumBlack/Gamma-style agent design. |
| **Upstage** | ~65% | 82% | RAGAS pipeline + DART integration + Korean market domain = direct product alignment. Upstage builds LLMs for Korean enterprises; this shows practical deployment experience. |

### What Moves the Needle Most Per Firm

**Deloitte** — Phase 4.1 (RBAC/RLS) + Phase 2.4 (RAGAS). Two sessions of work = +12% fit.
**Accenture** — Phase 3.3 (React frontend) + Phase 3.5 (CI/CD). Shows delivery, not just prototyping.
**McKinsey QB** — Phase 2.5 (parallel Send API) + Phase 4.3 (XGBoost). Quant rigor is the signal.
**BCG Gamma** — Phase 2.3 (Valuation Agent: DCF + comps). Consulting firms want finance modeling, not just data retrieval.
**Upstage** — Phase 2.4 (RAGAS eval) + Phase 1.2 (hybrid search). Product-level quality metrics + Korean data = hire signal.

---

## Recommended Build Order (time-constrained)

If applying to BCG in the next 2 weeks, do this:

1. **Step 2.3** — Valuation Agent (DCF + comps) — 6h — Highest BCG/McKinsey signal
2. **Step 2.4** — RAGAS pipeline — 4h — Differentiates from other student projects
3. **Step 1.1** — DART live data — 3h — Easy win; MCP already built
4. **Step 1.2** — Hybrid search — 4h — Replaces "custom VectorDB" with industry-standard approach
5. **Step 3.1** — pptx generation — 4h — Client-ready output = consulting DNA
6. **Step 3.4** — AWS deploy — 6h — Cloud = production. Streamlit is prototype.

**Total: 27 hours / 7 days at 4h/day** — Done before BCG deadline.

---

## Interview Talking Points (once built)

- "I emulated the data stack MBB firms use internally — hybrid retrieval, graph databases for Korean Chaebol structures, and a valuation agent that runs DCF models programmatically."
- "I added a RAGAS evaluation pipeline so I could quantify hallucination rate — that was the gap between a demo and something you could run in a client engagement."
- "The Supervisor Agent routes queries to specialized nodes in parallel using LangGraph's Send API — same pattern used in production agentic systems."

---

## File Structure (when built)

```
consulting-emulation/
├── README.md          ← this file
├── agents/
│   ├── supervisor.py
│   ├── sql_agent.py
│   ├── graphrag_agent.py
│   └── valuation_agent.py
├── data/
│   ├── dart_pipeline.py
│   ├── neo4j_schema.cypher
│   └── entity_extractor.py
├── eval/
│   └── ragas_benchmark.py
├── output/
│   └── pptx_generator.py
├── api.py
└── app.py (Streamlit or Next.js)
```

---

## Dependencies to Install (when starting)

```bash
pip install rank-bm25 neo4j ragas python-pptx xgboost scikit-learn
npm create next-app  # Phase 3 only
```

---

## Blockers Before Starting

- [ ] **Supabase restore** — needed for Postgres checkpointing (Phase 2.6)
- [ ] **DART API key** — needed for live data (Phase 1.1). Apply at dart.fss.or.kr
- [ ] **Neo4j install** — `brew install neo4j` or download from neo4j.com/download

---

## Evaluation (RAGAS)

Run: `pip install ragas datasets python-dotenv && python eval/ragas_benchmark.py`

Metrics: Answer Relevancy, Faithfulness, Context Precision, Answer Correctness
Benchmark: 15 questions across sql_only / rag_only / both routes
Results saved to: `eval/ragas_results.json`


---

### Hybrid Search Module (done)
- File: `data/hybrid_search.py`
- BM25 (rank_bm25) + Dense (OpenAI embeddings) + RRF fusion (k=60)
- Install: `pip install rank-bm25`
- Test: `python data/hybrid_search.py`

### PowerPoint Generator (done)
- File: `output/pptx_generator.py`
- Input: Report Agent markdown output + optional Valuation Agent result
- Output: 5-slide consulting deck (.pptx)
- Install: `pip install python-pptx`
- Test: `python output/pptx_generator.py` → generates `output/test_deck.pptx`

### AWS Lambda Deployment (done)
- Files: `deploy/` — lambda_handler.py, template.yaml, deploy.sh, README.md
- Runtime: Python 3.11 + Mangum (ASGI adapter)
- One-time setup: `aws configure` + `pip install aws-sam-cli`
- First deploy: `cd deploy/ && ./deploy.sh --guided`
- Subsequent deploys: `cd deploy/ && ./deploy.sh`
- Cost: ~$0 (AWS free tier covers portfolio-level traffic)
- Note: If package exceeds 250MB limit, move numpy/pandas to a Lambda Layer — see `deploy/README.md`
