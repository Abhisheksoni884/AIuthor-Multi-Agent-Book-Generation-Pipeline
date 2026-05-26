"""
core/rag.py - Grounded retrieval using FAISS + OpenAI embeddings.

Supports:
  - Seed knowledge base (built-in facts)
  - External document ingestion (add_documents / ingest_file)
  - Hybrid retrieval: dense (embedding) + BM25-style keyword fallback
  - Top-k with optional simple reranking by query overlap
"""
from __future__ import annotations
import os
import re
from typing import Optional
from collections import defaultdict

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


# ─────────────────────────────────────────────────────────────────────────────
# Seed knowledge base — grounded facts for non-fiction chapters
# ─────────────────────────────────────────────────────────────────────────────
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
    "Diversification across asset classes reduces portfolio volatility without sacrificing expected returns.",
    "The average American household carries approximately $6,000–$8,000 in credit card debt.",
    "Paying yourself first (automating savings before spending) is one of the most effective wealth-building habits.",
    # General knowledge
    "The human brain has approximately 86 billion neurons.",
    "Water boils at 100°C (212°F) at sea level.",
    "The speed of light is approximately 299,792 km/s.",
    "The global literacy rate is approximately 87% as of 2023.",
    "Climate science consensus: global average temperature has risen ~1.1°C since pre-industrial times.",
]


def _chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """
    Split a document into overlapping chunks of ~chunk_size words.
    Overlap ensures context is not lost at chunk boundaries.
    """
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


class BookRAG:
    """
    Grounded RAG: embeds seed facts + any ingested documents.
    Uses FAISS for dense retrieval + BM25-style keyword fallback.
    Supports simple reranking by query-overlap score.
    """

    def __init__(self):
        self._store: Optional[FAISS] = None
        self._ready = False
        self._raw_docs: list[str] = list(SEED_KNOWLEDGE)  # for BM25 fallback
        self._embeddings = None

    def build(self):
        """Build the FAISS vector store from seed knowledge."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key or api_key == "your_openai_api_key_here":
            self._ready = False
            return
        try:
            self._embeddings = OpenAIEmbeddings(api_key=api_key)
            docs = [Document(page_content=fact, metadata={"source": "seed"})
                    for fact in SEED_KNOWLEDGE]
            self._store = FAISS.from_documents(docs, self._embeddings)
            self._ready = True
        except Exception as e:
            self._ready = False

    def add_documents(self, texts: list[str], source: str = "user"):
        """
        Ingest new documents into the vector store.
        Each text is chunked before embedding.

        Args:
            texts: list of raw document strings
            source: provenance label (e.g. filename or "user")
        """
        new_chunks = []
        for text in texts:
            chunks = _chunk_text(text)
            self._raw_docs.extend(chunks)
            for chunk in chunks:
                new_chunks.append(Document(page_content=chunk, metadata={"source": source}))

        if not self._ready or self._store is None:
            # Can't embed — store for keyword fallback only
            return

        try:
            self._store.add_documents(new_chunks)
        except Exception:
            pass

    def ingest_file(self, filepath: str):
        """
        Read a text file and add its contents to the RAG index.
        Chunks the file before embedding.
        """
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        source = os.path.basename(filepath)
        self.add_documents([text], source=source)

    def retrieve(self, query: str, k: int = 4, rerank: bool = True) -> str:
        """
        Return top-k relevant facts as a bullet list.

        Strategy:
        1. Dense retrieval (FAISS cosine similarity) if embeddings are available
        2. BM25-style keyword fallback otherwise
        3. Optional reranking by keyword overlap on top of dense results
        """
        if self._ready and self._store:
            try:
                # Dense retrieval
                results = self._store.similarity_search(query, k=k * 2)
                candidates = [r.page_content for r in results]

                if rerank:
                    candidates = self._rerank(query, candidates, top_k=k)
                else:
                    candidates = candidates[:k]

                return "\n".join(f"• {c}" for c in candidates)
            except Exception:
                pass

        # BM25-style keyword fallback
        return self._keyword_retrieve(query, k=k)

    def _rerank(self, query: str, candidates: list[str], top_k: int) -> list[str]:
        """
        Simple reranking: score candidates by unigram overlap with query.
        In production, replace with a cross-encoder or ColBERT reranker.
        """
        query_tokens = set(re.findall(r'\w+', query.lower()))
        scored = []
        for c in candidates:
            doc_tokens = set(re.findall(r'\w+', c.lower()))
            overlap = len(query_tokens & doc_tokens)
            scored.append((overlap, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def _keyword_retrieve(self, query: str, k: int) -> str:
        """BM25-style keyword scoring over raw_docs."""
        query_words = set(re.findall(r'\w+', query.lower()))
        scored = []
        for doc in self._raw_docs:
            doc_words = set(re.findall(r'\w+', doc.lower()))
            score = len(query_words & doc_words)
            scored.append((score, doc))
        scored.sort(reverse=True)
        top = [d for s, d in scored[:k] if s > 0]
        return "\n".join(f"• {d}" for d in top) if top else "No specific facts found."

    @property
    def doc_count(self) -> int:
        return len(self._raw_docs)
