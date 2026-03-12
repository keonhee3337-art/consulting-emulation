"""
Custom VectorDB — built from scratch using OpenAI embeddings + cosine similarity.

This is the core of what a VectorDB like ChromaDB or Pinecone does internally:
1. Embed each document into a high-dimensional vector using an embedding model
2. Store vectors alongside the original text
3. At query time, embed the query and find the closest stored vectors (cosine similarity)
4. Return the top-k most similar documents

Built from scratch here so the implementation is fully transparent and Python 3.14 compatible.
"""

import json
import os
import numpy as np
from openai import OpenAI

STORE_PATH = os.path.join(os.path.dirname(__file__), "../data/vector_store.json")
EMBEDDING_MODEL = "text-embedding-3-small"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Range: -1 to 1 (higher = more similar)."""
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def get_embedding(text: str, client: OpenAI) -> list[float]:
    """Call OpenAI embeddings API to convert text to a vector."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def build_vector_store(documents: list[dict], api_key: str):
    """
    Embed all documents and save to disk as JSON.
    Each entry: {id, text, metadata, embedding}
    """
    client = OpenAI(api_key=api_key)
    store = []

    for doc in documents:
        print(f"Embedding: {doc['id']}...")
        embedding = get_embedding(doc["text"], client)
        store.append({
            "id": doc["id"],
            "text": doc["text"],
            "metadata": doc["metadata"],
            "embedding": embedding
        })

    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f)

    print(f"Vector store saved: {len(store)} documents at {STORE_PATH}")


_vector_store_cache = None


def get_vector_store() -> list[dict]:
    """Load vector store from disk once and cache it in memory."""
    global _vector_store_cache
    if _vector_store_cache is None:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            _vector_store_cache = json.load(f)
    return _vector_store_cache


def query_vector_store(query: str, client: OpenAI, top_k: int = 3) -> list[dict]:
    """
    Embed the query, compute cosine similarity against all stored vectors,
    and return the top_k most similar documents.
    """
    store = get_vector_store()

    query_embedding = get_embedding(query, client)

    # Score every document
    scored = [
        {
            "text": entry["text"],
            "metadata": entry["metadata"],
            "score": cosine_similarity(query_embedding, entry["embedding"])
        }
        for entry in store
    ]

    # Sort by similarity descending, return top_k
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
