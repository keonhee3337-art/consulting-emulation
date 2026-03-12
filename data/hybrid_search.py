"""
Hybrid Search with Reciprocal Rank Fusion (RRF)
================================================

WHY HYBRID SEARCH?

Dense-only retrieval (FinAgent's current approach) uses OpenAI embeddings + cosine
similarity. It's great at conceptual matching — "competitive moat" will surface
documents about barriers to entry even if those exact words don't appear. But it
fails on exact terms: a query for "2023 revenue" may miss a document that literally
says "2023 revenue" if the embedding space doesn't cluster them tightly.

BM25 (Best Match 25) is the inverse: pure keyword/lexical matching. It ranks
documents by term frequency and inverse document frequency. It nails exact company
names, years, and financial line items — but has no semantic understanding.

Hybrid search runs both and fuses the results using Reciprocal Rank Fusion (RRF).
The intuition: if a document ranks highly in BOTH lists, it's almost certainly
relevant. If it only ranks in one, it may still be surfaced but deprioritized.
This is the standard approach at firms like Elastic, Cohere, and Weaviate —
and what McKinsey QuantumBlack / BCG Gamma use in enterprise RAG pipelines.

RRF FORMULA:
    score(doc) = sum over each ranking list of: 1 / (k + rank(doc))
    k = 60 is the standard constant (penalizes low-ranked docs steeply)
    Higher score = more relevant.

ARCHITECTURE:
    Query
      ├── BM25 (rank_bm25) → ranked list 1
      ├── Dense (OpenAI text-embedding-3-small + cosine similarity) → ranked list 2
      └── RRF fusion → final re-ranked list → top_k results
"""

import json
import numpy as np

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    raise ImportError(
        "rank_bm25 is not installed. Run: pip install rank-bm25"
    )

from openai import OpenAI

# RRF constant — 60 is the de facto standard from the original Cormack et al. paper.
# Higher k makes the formula more forgiving to lower-ranked docs.
RRF_K = 60

EMBEDDING_MODEL = "text-embedding-3-small"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Range -1 to 1 (higher = more similar)."""
    a_arr, b_arr = np.array(a), np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))


def _get_embedding(text: str, client: OpenAI) -> list[float]:
    """Embed text using OpenAI text-embedding-3-small (1536 dims)."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def _tokenize(text: str) -> list[str]:
    """
    Whitespace + lowercase tokenizer for BM25.
    Kept simple intentionally — no stopword removal or stemming.
    Adding stopwords would improve BM25 precision but adds complexity;
    for financial text (dense with proper nouns and figures), simple tokenization
    already works well.
    """
    return text.lower().split()


class HybridSearcher:
    """
    Combines BM25 (keyword) and dense (semantic) retrieval via RRF.

    Reads from the same vector_store.json format used by FinAgent's vector_store.py.
    Format per entry: {id, text, metadata, embedding}

    This is a standalone module — does NOT import from FinAgent. It reimplements
    the embedding and cosine logic so consulting-emulation has no dependency on
    FinAgent's file structure.
    """

    def __init__(self, vector_store_path: str, openai_client: OpenAI):
        """
        Args:
            vector_store_path: Absolute path to vector_store.json (FinAgent format).
            openai_client: Initialized OpenAI client with a valid API key.
        """
        self._client = openai_client

        # Load the vector store from disk
        with open(vector_store_path, "r", encoding="utf-8") as f:
            self._store = json.load(f)

        if not self._store:
            raise ValueError(f"Vector store at {vector_store_path} is empty.")

        # Build BM25 index from document texts.
        # BM25Okapi expects a list of token lists — one list per document.
        tokenized_corpus = [_tokenize(entry["text"]) for entry in self._store]
        self._bm25 = BM25Okapi(tokenized_corpus)

        # Pre-extract embeddings for dense search (already computed — no API call needed)
        self._embeddings = [entry["embedding"] for entry in self._store]

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Run hybrid search: BM25 + dense, fused with RRF.

        Args:
            query: Natural language query string.
            top_k: Number of results to return.

        Returns:
            List of dicts, each containing:
                text       — document text
                metadata   — original metadata dict (company, topic, year)
                score      — RRF fused score (higher = more relevant)
                bm25_rank  — rank in BM25-only list (1 = best). None if not in BM25 top.
                dense_rank — rank in dense-only list (1 = best). None if not in dense top.
        """
        n_docs = len(self._store)

        # --- Step 1: BM25 ranking ---
        # BM25 scores all docs; we rank them descending.
        bm25_scores = self._bm25.get_scores(_tokenize(query))
        # argsort ascending → reverse for descending rank
        bm25_ranked_indices = np.argsort(bm25_scores)[::-1].tolist()
        # Map: doc_index → bm25_rank (1-indexed)
        bm25_rank_map = {idx: rank + 1 for rank, idx in enumerate(bm25_ranked_indices)}

        # --- Step 2: Dense (semantic) ranking ---
        query_embedding = _get_embedding(query, self._client)
        dense_scores = [
            _cosine_similarity(query_embedding, emb) for emb in self._embeddings
        ]
        dense_ranked_indices = np.argsort(dense_scores)[::-1].tolist()
        # Map: doc_index → dense_rank (1-indexed)
        dense_rank_map = {idx: rank + 1 for rank, idx in enumerate(dense_ranked_indices)}

        # --- Step 3: RRF fusion ---
        # Every document gets a score from both lists.
        # score(doc) = 1/(k + bm25_rank) + 1/(k + dense_rank)
        rrf_scores = {}
        for idx in range(n_docs):
            bm25_r = bm25_rank_map.get(idx, n_docs)   # fallback: last rank
            dense_r = dense_rank_map.get(idx, n_docs)  # fallback: last rank
            rrf_scores[idx] = (1 / (RRF_K + bm25_r)) + (1 / (RRF_K + dense_r))

        # Sort by RRF score descending
        sorted_indices = sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True)

        # --- Step 4: Build results ---
        results = []
        for idx in sorted_indices[:top_k]:
            entry = self._store[idx]
            results.append({
                "text": entry["text"],
                "metadata": entry["metadata"],
                "score": round(rrf_scores[idx], 6),
                "bm25_rank": bm25_rank_map.get(idx),
                "dense_rank": dense_rank_map.get(idx),
            })

        return results


# ─────────────────────────────────────────────────────────────────────────────
# Test block
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    # Load API key from FinAgent's .env — same key, no duplication
    env_path = r"c:/Users/keonh/OneDrive/바탕 화면/FinAgent/.env"
    load_dotenv(env_path)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            f"OPENAI_API_KEY not found. Check that it is set in {env_path}"
        )

    client = OpenAI(api_key=api_key)

    # Point at FinAgent's existing vector store — no new data needed for this test
    vector_store_path = r"c:/Users/keonh/OneDrive/바탕 화면/FinAgent/data/vector_store.json"

    print("Initializing HybridSearcher...")
    searcher = HybridSearcher(vector_store_path=vector_store_path, openai_client=client)
    print(f"Loaded {len(searcher._store)} documents. BM25 index built.\n")

    # Three test queries designed to stress different retrieval modes:
    # 1. Keyword-heavy — BM25 should dominate (exact terms: company name + year + metric)
    # 2. Conceptual — Dense should dominate (no exact term "HBM" may be in all docs)
    # 3. Mixed — hybrid adds value (strategy concept + company name)
    test_queries = [
        ("keyword-heavy",  "Samsung revenue 2023"),
        ("conceptual",     "HBM competitive advantage"),
        ("mixed",          "SK Hynix recovery strategy"),
    ]

    TOP_K = 3

    for query_type, query in test_queries:
        print("=" * 70)
        print(f"Query [{query_type}]: \"{query}\"")
        print("=" * 70)

        results = searcher.search(query, top_k=TOP_K)

        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            bm25_r = r["bm25_rank"]
            dense_r = r["dense_rank"]

            # Agreement check: do both signals agree this doc is top-ranked?
            # Disagreement is where hybrid retrieval adds the most value —
            # one signal surfaces something the other would have missed.
            if bm25_r <= TOP_K and dense_r <= TOP_K:
                agreement = "AGREE (both signals rank this highly — strong signal)"
            elif bm25_r <= TOP_K:
                agreement = "DISAGREE — BM25 only (keyword match; dense missed it)"
            elif dense_r <= TOP_K:
                agreement = "DISAGREE — Dense only (semantic match; BM25 missed it)"
            else:
                agreement = "NEITHER in individual top-k (RRF surfaced via combined score)"

            print(f"\n  Result {i}:")
            print(f"    Company : {meta.get('company', '?')}  |  Topic: {meta.get('topic', '?')}  |  Year: {meta.get('year', '?')}")
            print(f"    BM25 rank  : {bm25_r}")
            print(f"    Dense rank : {dense_r}")
            print(f"    RRF score  : {r['score']}")
            print(f"    Signal     : {agreement}")
            print(f"    Text (100c): {r['text'][:100].strip()}...")

        print()
