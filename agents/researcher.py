"""
agents/researcher.py - Gathers grounded facts for each chapter using RAG
"""
from core.llm import call_llm
from core.rag import BookRAG
from core.memory import BookMemory


SYSTEM_PROMPT = """You are a research assistant for a book author.
Given a chapter brief and some reference facts, produce:
1. A list of 3-5 concrete facts or statistics to include (drawn from or consistent with the reference facts)
2. 2-3 key concepts that should be defined for the reader
3. Any callback opportunities (references back to prior chapters)

Output as plain text with clear section headers:
FACTS:
- ...

CONCEPTS:
- term: definition

CALLBACKS:
- ...
"""


def run(chapter_plan: dict, book_plan: dict, rag: BookRAG, memory: BookMemory, tracer=None) -> dict:
    """Research a single chapter. Returns a research brief dict."""
    ch_num = chapter_plan["num"]
    ch_title = chapter_plan["title"]
    ch_summary = chapter_plan.get("summary", "")
    key_points = chapter_plan.get("key_points", [])

    # RAG retrieval
    query = f"{book_plan.get('title', '')} {ch_title} {ch_summary}"
    retrieved_facts = rag.retrieve(query, k=4)

    # Prior chapter summaries for callbacks
    prior = memory.get_prior_summaries(ch_num)
    callbacks_available = memory.get_callbacks_for(ch_num)

    user_prompt = f"""
Book: {book_plan.get('title', 'Untitled')}
Chapter {ch_num}: {ch_title}
Summary: {ch_summary}
Key points to cover: {', '.join(key_points)}

Reference facts from knowledge base:
{retrieved_facts}

Prior chapters:
{prior}

Available callbacks: {', '.join(callbacks_available) if callbacks_available else 'None yet'}
"""

    response = call_llm(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tracer=tracer,
        agent_name=f"Researcher-Ch{ch_num}",
        max_tokens=800
    )

    # Parse sections
    facts = _extract_section(response, "FACTS")
    concepts = _extract_section(response, "CONCEPTS")
    callbacks = _extract_section(response, "CALLBACKS")

    # Store concepts in memory
    for line in concepts:
        if ":" in line:
            term, _, defn = line.partition(":")
            memory.add_concept(term.strip("- ").strip(), defn.strip(), ch_num)

    # Store retrieved facts
    for i, fact in enumerate(facts):
        memory.add_fact(f"ch{ch_num}_fact{i}", fact.strip("- ").strip(), f"Chapter {ch_num}", ch_num)

    # Store callback references
    for cb in callbacks:
        cb_clean = cb.strip("- ").strip()
        if cb_clean and cb_clean.lower() not in ("none yet", "n/a", "none"):
            memory.add_callback(cb_clean, ch_num)

    return {
        "chapter": ch_num,
        "facts": facts,
        "concepts": concepts,
        "callbacks": callbacks,
        "retrieved_facts": retrieved_facts,
        "raw": response
    }


def _extract_section(text: str, header: str) -> list[str]:
    """Extract bullet lines under a section header."""
    lines = text.split("\n")
    in_section = False
    results = []
    for line in lines:
        if header + ":" in line.upper():
            in_section = True
            continue
        if in_section:
            if line.strip() and line.strip()[0].isalpha() and line.strip().endswith(":"):
                break  # Next section header
            if line.strip().startswith("-") or (line.strip() and in_section):
                results.append(line.strip())
    return [r for r in results if r and r != "-"]
