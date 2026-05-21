"""
agents/memory_keeper.py - Maintains cross-chapter consistency; repairs on chapter insert
"""
from core.llm import call_llm
from core.memory import BookMemory


SYSTEM_PROMPT = """You are a continuity editor for a multi-chapter book.
Given a chapter and the book's memory (facts, concepts, characters), 
identify any consistency issues and suggest inline fixes.

Output:
CONSISTENCY_ISSUES: (list issues or "None")
SUGGESTED_FIXES: (list fixes or "None needed")
"""


def run(text: str, chapter_num: int, memory: BookMemory, tracer=None) -> dict:
    """Check cross-chapter consistency for a chapter."""
    context = f"""
Known facts: {memory.all_facts_text()}
Characters: {memory.characters_summary()}
TOC: {memory.get_toc_text()}
"""
    user_prompt = f"Chapter {chapter_num}:\n{text[:1500]}\n\nMemory:\n{context}"

    response = call_llm(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tracer=tracer,
        agent_name=f"MemoryKeeper-Ch{chapter_num}",
        max_tokens=500
    )
    return {"chapter": chapter_num, "report": response}


def repair_for_insert(chapters: dict, insert_at: int, memory: BookMemory, tracer=None) -> dict:
    """
    After inserting a chapter, repair TOC references and callbacks in adjacent chapters.
    Returns dict of chapter_num -> repaired_text for chapters that needed fixing.
    """
    memory.repair_after_insert(insert_at)
    repaired = {}

    # Check chapters immediately before and after the insertion point
    for ch_num in [insert_at - 1, insert_at + 1]:
        if ch_num in chapters:
            text = chapters[ch_num]
            system = """You are fixing chapter cross-references after a new chapter was inserted.
Update any references like 'Chapter N' to correct numbering if needed.
Output ONLY the corrected text."""
            user = f"A new chapter was inserted at position {insert_at}. Fix any chapter number references in this text:\n\n{text[:2000]}"
            fixed = call_llm(
                system=system, user=user,
                tracer=tracer, agent_name=f"MemoryKeeper-Repair-{ch_num}",
                max_tokens=2500
            )
            repaired[ch_num] = fixed

    return repaired
