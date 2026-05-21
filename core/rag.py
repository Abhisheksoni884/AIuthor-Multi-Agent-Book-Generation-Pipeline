"""
core/rag.py - Simple in-memory vector store for grounded facts (RAG)
Uses FAISS + OpenAI embeddings.
"""
from __future__ import annotations
import os
from typing import Optional
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


# Seed knowledge base — facts to ground the agents
SEED_KNOWLEDGE = [
    # Personal finance
    "The 50/30/20 budgeting rule allocates 50% to needs, 30% to wants, and 20% to savings.",
    "Compound interest grows wealth exponentially; Einstein reportedly called it the eighth wonder of the world.",
    "An emergency fund should cover 3-6 months of living expenses.",
    "Index funds typically outperform actively managed funds over 10+ year periods.",
    "The average annual stock market return (S&P 500) is approximately 10% before inflation, ~7% after.",
    "High-interest debt (above 7%) should be paid before investing in the market.",
    "A 401(k) employer match is essentially free money; always contribute enough to get the full match.",
    "Dollar-cost averaging reduces the risk of investing a lump sum at the wrong time.",
    "The Rule of 72: divide 72 by annual interest rate to estimate years to double an investment.",
    "Net worth = total assets minus total liabilities.",
    "A credit score above 750 qualifies for the best loan rates.",
    "Term life insurance is generally cheaper and simpler than whole life insurance.",
    "Roth IRA contributions are made with after-tax dollars; withdrawals in retirement are tax-free.",
    "The 4% rule suggests retirees can withdraw 4% of their portfolio annually without running out of money.",
    "Inflation averages about 2-3% per year; cash savings lose purchasing power over time.",
    # General knowledge
    "The human brain has approximately 86 billion neurons.",
    "Water boils at 100°C (212°F) at sea level.",
    "The speed of light is approximately 299,792 km/s.",
]


class BookRAG:
    """Lightweight RAG: embed seed facts, retrieve relevant context for any query."""

    def __init__(self):
        self._store: Optional[FAISS] = None
        self._ready = False

    def build(self):
        """Build the vector store from seed knowledge."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key or api_key == "your_openai_api_key_here":
            # Fallback: keyword search
            self._ready = False
            return
        try:
            embeddings = OpenAIEmbeddings(api_key=api_key)
            docs = [Document(page_content=fact) for fact in SEED_KNOWLEDGE]
            self._store = FAISS.from_documents(docs, embeddings)
            self._ready = True
        except Exception:
            self._ready = False

    def retrieve(self, query: str, k: int = 3) -> str:
        """Return top-k relevant facts as a bullet list."""
        if self._ready and self._store:
            try:
                results = self._store.similarity_search(query, k=k)
                return "\n".join(f"• {r.page_content}" for r in results)
            except Exception:
                pass
        # Fallback: keyword match
        query_words = set(query.lower().split())
        scored = []
        for fact in SEED_KNOWLEDGE:
            fact_words = set(fact.lower().split())
            score = len(query_words & fact_words)
            scored.append((score, fact))
        scored.sort(reverse=True)
        top = [f for _, f in scored[:k] if _ > 0]
        return "\n".join(f"• {f}" for f in top) if top else "No specific facts found."
