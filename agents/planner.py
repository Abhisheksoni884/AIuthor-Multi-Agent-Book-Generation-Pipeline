"""
agents/planner.py - Plans the full book structure from a user brief
"""
from core.llm import call_llm
from core.config import TONES
from core.memory import BookMemory
from core.schemas import validate_book_plan
import json
import re


SYSTEM_PROMPT = """You are a professional book planner. Given a brief, you produce a complete book outline.
Output ONLY valid JSON. No markdown fences, no preamble.

The JSON must have this shape:
{
  "title": "...",
  "subtitle": "...",
  "genre": "...",
  "tone": "...",
  "author_name": "...",
  "tagline": "...",
  "target_audience": "...",
  "back_cover_theme": "...",
  "chapters": [
    {"num": 1, "title": "...", "summary": "...", "key_points": ["...", "...", "..."]}
  ],
  "glossary_terms": ["term1", "term2"],
  "characters": [{"name": "...", "description": "..."}],
  "front_matter": ["half_title", "copyright", "dedication", "epigraph", "foreword", "preface", "acknowledgments", "introduction", "toc"],
  "back_matter": ["afterword", "appendix", "glossary", "references", "about_author", "back_cover"]
}
"""


def run(brief: str, tone: str, num_chapters: int, memory: BookMemory, tracer=None) -> dict:
    """Generate a full book plan from a brief. Returns a validated plan dict."""
    tone_info = TONES.get(tone, TONES["conversational"])

    user_prompt = f"""
Brief: {brief}
Tone: {tone_info['name']} — {tone_info['description']}
Number of chapters: {num_chapters}
Target words per chapter: ~2000-2500

Plan the complete book. Each chapter needs a clear title, one-sentence summary, and 3-5 key points.
Include appropriate glossary terms for the subject matter.

Front matter MUST include in this order:
half_title, copyright, dedication, epigraph, foreword, preface, acknowledgments, introduction, toc

Back matter MUST include:
afterword, appendix, glossary, references, about_author, back_cover
"""

    response = call_llm(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tracer=tracer,
        agent_name="Planner",
        max_tokens=2000
    )

    # Parse JSON
    plan = _parse_json(response, brief=brief)

    # Enforce required fields
    plan.setdefault("tone", tone)
    plan.setdefault("author_name", "The Author")
    plan.setdefault("characters", [])
    plan.setdefault("glossary_terms", [])
    plan["front_matter"] = [
        "half_title", "copyright", "dedication", "epigraph",
        "foreword", "preface", "acknowledgments", "introduction", "toc"
    ]
    plan["back_matter"] = [
        "afterword", "appendix", "glossary", "references", "about_author", "back_cover"
    ]

    # Validate through Pydantic schema (raises ValidationError on bad data)
    try:
        validated = validate_book_plan(plan)
        plan = validated.model_dump()
    except Exception as e:
        # Log but continue with raw plan if validation fails
        if tracer:
            tracer.record(agent="Planner", prompt="schema_validation", response=str(e),
                          input_tokens=0, output_tokens=0, duration=0, notes="schema validation warning")

    # Seed memory with TOC
    toc = [{"num": ch["num"], "title": ch["title"], "page_est": 0}
           for ch in plan.get("chapters", [])]
    memory.set_toc(toc)

    # Seed characters for fiction
    for char in plan.get("characters", []):
        memory.add_character(char["name"], char.get("description", ""), 1)

    # Log the planning decision
    memory.log_decision(
        chapter=0, agent="Planner",
        decision=f"Book plan created: '{plan.get('title')}' ({len(plan.get('chapters', []))} chapters, {tone} tone)",
        rationale="Planner agent transforms user brief into a structured JSON plan with full front/back matter"
    )

    return plan


def _parse_json(text: str, brief: str = "") -> dict:
    """Safely parse JSON from LLM output, with fallback extraction."""
    # Strip markdown fences if present
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        # Attempt to find JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        
        # Extract title from brief if available
        extracted_title = "Untitled Book"
        if brief:
            # Try to extract first meaningful phrase from brief
            words = brief.split()
            if len(words) > 0:
                # Take first 5 words as potential title
                extracted_title = " ".join(words[:5])
                if extracted_title.lower().startswith("a "):
                    extracted_title = extracted_title[2:].title()
                else:
                    extracted_title = extracted_title.title()
        
        # Return a minimal fallback plan
        return {
            "title": extracted_title,
            "subtitle": brief[:100] if brief else "",
            "genre": "Non-fiction",
            "tone": "conversational",
            "author_name": "The Author",
            "tagline": "",
            "target_audience": "General readers",
            "back_cover_theme": "",
            "chapters": [{"num": i, "title": f"Chapter {i}", "summary": f"Chapter {i} content", "key_points": []} for i in range(1, 6)],
            "glossary_terms": [],
            "characters": [],
            "front_matter": ["half_title", "copyright", "dedication", "epigraph",
                              "foreword", "preface", "acknowledgments", "introduction", "toc"],
            "back_matter": ["afterword", "appendix", "glossary", "references", "about_author", "back_cover"]
        }
