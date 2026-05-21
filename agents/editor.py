"""
agents/editor.py - Consistency, tone-check, and structural polish
"""
from core.llm import call_llm
from core.config import TONES


SYSTEM_PROMPT = """You are a senior copy editor reviewing a book chapter.

Your tasks:
1. Fix any grammar, spelling, or punctuation issues
2. Ensure the tone is consistent throughout (check the specified tone)
3. Make sure paragraphs flow logically — add transitions if missing
4. Verify the chapter has: opening hook, 3 sections, summary, takeaway
5. Cut repetition — if a point is made twice, keep the better version
6. Ensure subheadings are compelling, not boring

Output the improved chapter text ONLY. No notes, no commentary.
Keep the same markdown formatting (## for chapter title, ### for sections).
"""


def run(text: str, tone: str, chapter_num: int, chapter_title: str, tracer=None) -> str:
    """Edit a chapter for consistency and quality. Returns edited text."""
    tone_info = TONES.get(tone, TONES["conversational"])

    user_prompt = f"""
Tone: {tone_info['name']} — {tone_info['description']}
Chapter {chapter_num}: {chapter_title}

Edit this chapter:

---
{text}
---
"""
    result = call_llm(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tracer=tracer,
        agent_name=f"Editor-Ch{chapter_num}",
        max_tokens=3000
    )
    return result if result else text
