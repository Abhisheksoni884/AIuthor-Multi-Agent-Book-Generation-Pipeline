"""
agents/memory_keeper.py - Maintains cross-chapter consistency; repairs on chapter insert.

Also records tonality fingerprints per chapter for cross-chapter tone consistency tracking.
"""
from core.llm import call_llm
from core.memory import BookMemory


SYSTEM_PROMPT = """You are a continuity editor for a multi-chapter book.
Given a chapter and the book's memory (facts, concepts, characters),
identify any consistency issues and suggest inline fixes.

Also extract the tonality fingerprint: list the specific words, phrases, and stylistic
patterns this chapter uses that define its tone (e.g., second-person usage, contraction rate,
sentence rhythm, specific recurring phrases).

Output:
CONSISTENCY_ISSUES: (list issues or "None")
SUGGESTED_FIXES: (list fixes or "None needed")
TONALITY_SIGNALS: (comma-separated list of observed tone markers, e.g. "uses 'you', short sentences, no jargon")
"""


def run(text: str, chapter_num: int, memory: BookMemory, tracer=None) -> dict:
    """Check cross-chapter consistency and record tonality fingerprint."""
    context = f"""
Known facts: {memory.all_facts_text()}
Characters: {memory.characters_summary()}
TOC: {memory.get_toc_text()}
Prior tone fingerprints: {memory.get_all_tone_fingerprints()}
"""
    user_prompt = f"Chapter {chapter_num}:\n{text[:1500]}\n\nMemory:\n{context}"

    response = call_llm(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tracer=tracer,
        agent_name=f"MemoryKeeper-Ch{chapter_num}",
        max_tokens=600
    )

    # Extract and store tonality fingerprint
    tone_signals = _extract_section(response, "TONALITY_SIGNALS")
    if tone_signals:
        fingerprint = ", ".join(tone_signals)
        memory.set_tonality_fingerprint(chapter_num, fingerprint, tracer=tracer, agent=f"MemoryKeeper-Ch{chapter_num}")
        memory.log_decision(
            chapter=chapter_num, agent="MemoryKeeper",
            decision=f"Tone fingerprint recorded: {fingerprint[:100]}",
            rationale="Tracking per-chapter tone signals enables cross-chapter consistency checks"
        )

    return {"chapter": chapter_num, "report": response}


def repair_for_insert(chapters: dict, insert_at: int, memory: BookMemory, tracer=None) -> dict:
    """
    After inserting a chapter, repair:
    1. TOC references and callbacks in adjacent chapters
    2. Memory re-numbering (facts, summaries, callbacks)
    3. Glossary: remove concepts from now-renumbered chapters and re-register them
    Returns dict of chapter_num -> repaired_text for chapters that needed fixing.
    """
    # Step 1: Re-number everything in memory
    memory.repair_after_insert(insert_at)

    repaired = {}

    # Step 2: Repair adjacent chapter text (cross-reference numbers)
    for ch_num in [insert_at - 1, insert_at + 1]:
        if ch_num in chapters:
            text = chapters[ch_num]
            system = """You are fixing chapter cross-references after a new chapter was inserted.
Update any references like 'Chapter N' to correct numbering if needed.
Output ONLY the corrected text."""
            user = (
                f"A new chapter was inserted at position {insert_at}. "
                f"Fix any chapter number references in this text:\n\n{text[:2000]}"
            )
            fixed = call_llm(
                system=system, user=user,
                tracer=tracer, agent_name=f"MemoryKeeper-Repair-{ch_num}",
                max_tokens=2500
            )
            repaired[ch_num] = fixed

    # Step 3: Glossary self-heal — rebuild from current memory concepts (already re-numbered)
    # Concepts in memory retain correct chapter attribution after repair_after_insert().
    # No further action needed for glossary terms themselves; the Writer will rebuild
    # the glossary section from memory.get_glossary() which is already correct.
    # Log this explicitly for the design log.
    memory.log_decision(
        chapter=insert_at, agent="MemoryKeeper",
        decision=f"Chapter insert repair: re-numbered facts/summaries/fingerprints at ch{insert_at}; repaired adjacent chapter refs",
        rationale="After chapter insertion, all memory indices >= insert_at are incremented, and adjacent chapters get cross-reference text fixes"
    )

    return repaired


def _extract_section(text: str, header: str) -> list[str]:
    """Extract bullet lines under a section header."""
    lines = text.split("\n")
    in_section = False
    results = []
    for line in lines:
        if header + ":" in line.upper():
            in_section = True
            # Inline content on same line
            inline = line.split(":", 1)[-1].strip()
            if inline and inline.lower() not in ("none", "none needed", "n/a"):
                results.append(inline)
            continue
        if in_section:
            upper = line.strip().upper()
            if upper.startswith("CONSISTENCY") or upper.startswith("SUGGESTED") or upper.startswith("TONALITY"):
                break
            if line.strip() and line.strip().lower() not in ("none", "none needed", "n/a"):
                results.append(line.strip().lstrip("- "))
    return [r for r in results if r]
