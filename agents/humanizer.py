"""
agents/humanizer.py - Removes AI-tell phrases, makes text feel genuinely human
"""
import re
from core.llm import call_llm
from core.config import BANNED_PHRASES


SYSTEM_PROMPT = """You are an expert editor who removes AI-sounding language from text.

Your job: rewrite the given text so it sounds like a real human author wrote it.

STRICT RULES:
1. NEVER use these phrases: delve into, it's important to note, landscape of, in today's world, 
   fast-paced world, ever-evolving, dive deep, unpack, let's explore, it goes without saying,
   at the end of the day, game-changer, paradigm shift, holistic approach, leverage (as verb),
   synergy, utilize, in the realm of, a testament to, stands as a beacon, crucial, vital, pivotal,
   groundbreaking, revolutionary, transformative, comprehensive, robust, cutting-edge, moreover,
   furthermore, in conclusion (at chapter start — fine at natural endings)
2. Break up any sentences longer than 30 words
3. Vary sentence length — mix short punchy sentences with longer ones
4. Replace passive voice with active where natural
5. Remove hedge phrases like "it should be noted that", "one could argue"
6. Keep all facts, headings, structure, and word count roughly the same
7. Output ONLY the rewritten text — no commentary, no explanation

Make the writing feel alive, specific, and human.
"""


def run(text: str, chapter_num: int, tracer=None) -> str:
    """Humanize a chapter. Returns cleaned text."""
    # First pass: mechanical replacement of worst offenders
    cleaned = _mechanical_clean(text)

    # Second pass: LLM humanization
    user_prompt = f"""Rewrite this chapter text to sound human and natural.
Keep all headings, facts, and structure. Same approximate length.

---
{cleaned}
---
"""
    result = call_llm(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tracer=tracer,
        agent_name=f"Humanizer-Ch{chapter_num}",
        max_tokens=3000
    )
    return result if result else cleaned


def _mechanical_clean(text: str) -> str:
    """Quick regex/string replacements for the most common AI tells."""
    replacements = {
        r"[Dd]elve into": "explore",
        r"[Ii]t'?s important to note(?: that)?": "Note that",
        r"[Ii]n the landscape of": "in",
        r"[Ii]n today'?s (fast-paced |ever-evolving )?world": "Today",
        r"[Ll]et'?s (explore|unpack|dive (into|deep))": "Here's",
        r"[Ii]t goes without saying(?: that)?": "",
        r"[Aa]t the end of the day": "Ultimately",
        r"[Gg]ame-changer": "significant shift",
        r"[Pp]aradigm shift": "major change",
        r"[Hh]olistic approach": "broad approach",
        r"[Ll]everage (the|your|our|this|that|these|those)": r"use \1",
        r"[Uu]tilize": "use",
        r"[Ii]n the realm of": "in",
        r"[Aa] testament to": "evidence of",
        r"[Ss]tands as a beacon": "serves as an example",
        r"[Cc]utting-edge": "modern",
        r"[Rr]obust": "strong",
        r"[Cc]omprehensive": "thorough",
        r"[Tt]ransformative": "significant",
        r"[Rr]evolutionary": "new",
        r"[Gg]roundbreaking": "notable",
        r"[Pp]ivotal": "key",
        r"[Vv]ital": "essential",
        r"[Cc]rucial": "important",
        r"[Ss]ynergy": "cooperation",
        r"\[DEMO MODE[^\]]*\]": "",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text


def check_banned(text: str) -> list[str]:
    """Return list of banned phrases found in text (for eval)."""
    found = []
    text_lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in text_lower:
            found.append(phrase)
    return found
