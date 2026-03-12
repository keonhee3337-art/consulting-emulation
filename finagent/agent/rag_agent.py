"""
RAG Agent — retrieves relevant financial documents from the custom VectorDB
and generates a grounded answer using GPT-4o.

The VectorDB is a JSON file of OpenAI embeddings with cosine similarity search.
This is exactly what ChromaDB, Pinecone, and Weaviate do under the hood.
"""

import os
from openai import OpenAI
from agent.vector_store import query_vector_store

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are a financial research analyst. Answer the user's question
using ONLY the provided document excerpts. Be specific and cite key figures where available.
If the documents don't contain enough information, say so clearly."""


def run_rag_agent(state: dict) -> dict:
    """LangGraph node: semantic search over VectorDB, then generate grounded answer."""
    query = state["query"]

    # Step 1: Retrieve top-3 most semantically similar documents
    results = query_vector_store(query, client, top_k=3)

    if not results:
        return {**state, "rag_result": "No relevant documents found in knowledge base."}

    # Step 2: Format retrieved context for the LLM
    context_blocks = []
    for i, result in enumerate(results, 1):
        meta = result["metadata"]
        score = result["score"]
        context_blocks.append(
            f"[Doc {i} — {meta.get('company', '?')}, {meta.get('topic', '?')} "
            f"(similarity: {score:.2f})]\n{result['text']}"
        )
    context = "\n\n".join(context_blocks)

    # Step 3: Generate answer grounded in retrieved docs
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {query}\n\nDocument excerpts:\n{context}"}
        ],
        temperature=0.3
    )

    answer = response.choices[0].message.content.strip()
    rag_result = f"Retrieved {len(results)} documents (cosine similarity search).\n\n{answer}"

    return {**state, "rag_result": rag_result}
