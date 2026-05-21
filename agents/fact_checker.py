"""
agents/fact_checker.py - Checks factual claims against the memory/RAG knowledge base
"""
from core.llm import call_llm
from core.memory import BookMemory
from core.rag import BookRAG


SYSTEM_PROMPT = """You are a fact-checker for a book. Review the chapter text against the known facts provided.

Your job:
1. Flag any claims that contradict the known facts
2. Flag any specific numbers/statistics that seem implausible
3. Suggest corrections where possible
4. Note facts that could not be verified (mark as [UNVERIFIED])

Output format:
ISSUES FOUND: (list any problems, or "None found" if clean)
CORRECTIONS: (list suggested fixes, or "None needed")
VERIFIED FACTS: (list facts you confirmed are accurate)
CHAPTER STATUS: PASS or NEEDS_REVIEW
"""


def run(text: str, chapter_num: int, memory: BookMemory, rag: BookRAG, tracer=None) -> dict:
    """Fact-check a chapter. Returns a report dict."""
    known_facts = memory.all_facts_text()

    user_prompt = f"""
Chapter {chapter_num} text:
---
{text[:2000]}
---

Known facts from research:
{known_facts}
"""

    response = call_llm(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tracer=tracer,
        agent_name=f"FactChecker-Ch{chapter_num}",
        max_tokens=600
    )

    status = "PASS" if "PASS" in response.upper() else "NEEDS_REVIEW"
    return {
        "chapter": chapter_num,
        "status": status,
        "report": response
    }
