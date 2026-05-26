# Book Factory — Prompts Dossier

Every agent prompt in the pipeline, documented with purpose, inputs, outputs, known failure modes, and rationale.

---

## Agent 1: Planner

**Purpose:** Transforms a user brief into a complete, structured book plan.

**Why this prompt:** The planner needs to output structured JSON that every downstream agent depends on. Asking for JSON-only output (no markdown fences, no preamble) eliminates the most common LLM failure mode — wrapping JSON in prose. The explicit schema in the prompt is a contract: if the LLM deviates, `_parse_json()` catches it and Pydantic validates the result.

**System Prompt:**
```
You are a professional book planner. Given a brief, you produce a complete book outline.
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
```

**User Prompt Variables:**
- `{brief}` — user's book description
- `{tone_name}` / `{tone_description}` — selected tone info
- `{num_chapters}` — requested chapter count

**Output:** Validated `BookPlan` Pydantic model, serialised to dict.

**Known failure modes:**
- LLM wraps JSON in markdown fences → handled by `_parse_json()` regex strip
- LLM hallucinates extra fields → Pydantic model ignores unknown fields
- LLM returns fewer chapters than requested → pipeline uses what's returned; no crash
- LLM outputs invalid JSON → fallback hardcoded plan kicks in
- Chapter `key_points` returned as string instead of list → Pydantic coerces or rejects with clear error

**Model:** `gpt-4o-mini` (structured extraction, not prose generation)

---

## Agent 2: Researcher

**Purpose:** For each chapter, retrieves grounded facts via RAG and identifies concepts and callbacks.

**Why this prompt:** The three-section output (FACTS / CONCEPTS / CALLBACKS) gives downstream agents precisely structured information without requiring JSON from the LLM. Plain text with labelled sections is more robust than JSON for this task — the LLM is less likely to hallucinate format than with nested JSON. The `_extract_section()` parser handles messy outputs gracefully.

**System Prompt:**
```
You are a research assistant for a book author.
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
```

**User Prompt Variables:**
- `{chapter_num}`, `{chapter_title}`, `{chapter_summary}`
- `{retrieved_facts}` — from RAG vector search (top-4 by cosine similarity, reranked)
- `{prior_summaries}` — from BookMemory
- `{callbacks_available}` — existing callbacks in memory

**Output:** `ResearchBrief` dict with facts, concepts, callbacks, and raw response.

**Known failure modes:**
- RAG retrieves irrelevant facts for niche topics → keyword fallback reduces but doesn't eliminate this
- LLM fabricates facts not in the retrieved set → Fact Checker catches this downstream
- CONCEPTS section outputs "None" → section parser returns empty list, memory gets no new concepts
- Callbacks invented for Chapter 1 (no prior chapters) → parser filters "None yet" / "N/A" strings
- LLM merges sections (e.g., facts bleed into concepts) → `_extract_section()` stops at next header

**Model:** `gpt-4o-mini` (structured extraction from retrieved context)

---

## Agent 3: Writer

**Purpose:** Writes a complete chapter in the specified tone with consistent structure.

**Why this prompt:** Explicit structure requirements (hook → 3 sections → summary → takeaway) prevent formless prose dumps. Including `example_opener` per tone gives the LLM a concrete stylistic anchor rather than an abstract description. The `Avoid:` field is critical — it tells the LLM what NOT to do, which is more reliable than purely positive instructions. Second-person usage is conditioned on tone to avoid "you"-heavy text in Academic chapters.

**System Prompt:**
```
You are a professional book author. Write full chapter content.

Structure every chapter as:
1. Opening hook (2-3 sentences)
2. Section 1 with clear subheading
3. Section 2 with clear subheading
4. Section 3 with clear subheading
5. Chapter summary (3-4 sentences)
6. One actionable takeaway or reflection question

Use markdown for subheadings (## for chapter title, ### for sections).
Write naturally and engagingly. Do NOT use bullet lists for the main content — write in prose.
Aim for the target word count. Be specific, not generic.
```

**User Prompt Variables:**
- `{book_title}`, `{chapter_num}`, `{chapter_title}`, `{chapter_summary}`
- `{tone_name}`, `{tone_guidance}`, `{example_opener}`, `{tone_avoid}`
- `{second_person_guidance}` — "YES — address reader directly" (conversational/motivational) or "sparingly"
- `{facts_text}` — from Researcher
- `{callbacks_text}` — cross-chapter references
- `{prior_summaries}` — from Memory
- `{characters}` — for fiction consistency
- `{target_words}`

**Output:** Markdown chapter text (~2000-3500 words).

**Known failure modes:**
- Word count too low (<1500) → Editor does not pad; Humanizer doesn't add content → final chapter is short
- LLM ignores tone instruction and defaults to conversational → Editor catches inconsistencies; MemoryKeeper records the actual tone fingerprint
- Characters inconsistent between chapters → memory `characters_summary()` passed in prompt; LLM may still drift
- Section structure missing (no ###) → evals `check_has_structure()` will flag this
- LLM adds bullet lists despite instruction → Editor removes or Humanizer converts to prose

**Model:** `gpt-4o` (prose generation — highest quality required)

### Writer: Front Matter Tone-Specific Sub-Prompts

Each section has a dedicated prompt variant per tone. Key examples:

| Section | Conversational | Academic | Storyteller | Motivational | Witty |
|---|---|---|---|---|---|
| dedication | "warm, personal, 'you' OK" | "dignified and sincere" | "2-3 lines, heartfelt" | "inspiring, brief" | "clever twist welcome" |
| preface | "personal anecdote, 'you'" | "formal, first person" | "set a scene" | "energetic, empowering" | "self-aware, dry" |
| acknowledgments | "warm, personal" | "formal, brief" | "weave in a story" | "energetic, grateful" | "dry observation on writing process" |
| about_author | "warm, approachable" | "credential-focused, formal" | "small story about background" | "energetic, inspiring" | "unexpected detail" |
| back_cover | "address reader as 'you'" | "formal, evidence-based" | "narrative hook" | "'you' language, action-oriented" | "clever, 'you' language" |

### Writer: Back Matter Sub-Prompts

| Section | Prompt Summary |
|---|---|
| afterword | 200-250 word closing reflection, tone-specific voice |
| appendix | 200-300 word practical reference tables/lists |
| glossary | Definitions rewritten in target tone via separate LLM call |
| references | 8-10 plausible further reading items |
| about_author | 120-150 word credible author bio, tone-matched |
| back_cover | 100-150 word sales copy with tagline, tone-matched |

---

## Agent 4: Humanizer

**Purpose:** Strips AI-tell phrases and makes the writing feel genuinely human.

**Why this prompt:** Two-pass design: mechanical regex first (deterministic, free), LLM second (contextual, nuanced). The explicit banned phrases list in the system prompt doubles as both an instruction and a cross-check — the LLM is less likely to use a phrase it's just been told to never use. Rule 7 ("Output ONLY the rewritten text") prevents the LLM from adding meta-commentary that breaks downstream parsing.

**System Prompt:**
```
You are an expert editor who removes AI-sounding language from text.

Your job: rewrite the given text so it sounds like a real human author wrote it.

STRICT RULES:
1. NEVER use these phrases: delve into, it's important to note, landscape of, in today's world,
   fast-paced world, ever-evolving, dive deep, unpack, let's explore, it goes without saying,
   at the end of the day, game-changer, paradigm shift, holistic approach, leverage (as verb),
   synergy, utilize, in the realm of, a testament to, stands as a beacon, crucial, vital, pivotal,
   groundbreaking, revolutionary, transformative, comprehensive, robust, cutting-edge, moreover,
   furthermore, in conclusion (at chapter start)
2. Break up any sentences longer than 30 words
3. Vary sentence length — mix short punchy sentences with longer ones
4. Replace passive voice with active where natural
5. Remove hedge phrases like "it should be noted that", "one could argue"
6. Keep all facts, headings, structure, and word count roughly the same
7. Output ONLY the rewritten text — no commentary, no explanation

Make the writing feel alive, specific, and human.
```

**Two-pass approach:**
1. Mechanical regex replacements — `_mechanical_clean()` (fast, zero cost)
2. LLM rewrite pass — full humanisation (contextual)

**Known failure modes:**
- LLM re-introduces banned phrases after regex removes them → `check_banned()` in evals will flag
- LLM significantly shortens the text (loses facts) → word count eval will flag
- LLM adds new AI tells not in the ban list → LLM-as-judge `ai_tell_absence` score catches this
- LLM changes section headings → Editor and assembler can handle most heading variations
- LLM produces output shorter than 500 words for a long chapter → returns `cleaned` (pre-LLM) as fallback

**Model:** `gpt-4o` (rewriting prose — quality matters)

**RLHF hook:** For every chapter, the raw Writer opening and humanized opening are submitted to `generate_preference_pair()`. The judge labels which is preferred and scores both. These pairs are saved as JSONL for DPO training.

---

## Agent 5: Editor

**Purpose:** Ensures tone consistency, fixes grammar, checks structure, improves flow.

**Why this prompt:** The editor's role is narrow and well-defined — it should NOT rewrite content, only polish it. The task list (grammar → tone → flow → structure → repetition → subheadings) maps directly to the spec's requirements. "Output the improved chapter text ONLY" prevents the LLM from adding edit notes that would end up in the final book.

**System Prompt:**
```
You are a senior copy editor reviewing a book chapter.

Your tasks:
1. Fix any grammar, spelling, or punctuation issues
2. Ensure the tone is consistent throughout (check the specified tone)
3. Make sure paragraphs flow logically — add transitions if missing
4. Verify the chapter has: opening hook, 3 sections, summary, takeaway
5. Cut repetition — if a point is made twice, keep the better version
6. Ensure subheadings are compelling, not boring

Output the improved chapter text ONLY. No notes, no commentary.
Keep the same markdown formatting (## for chapter title, ### for sections).
```

**Known failure modes:**
- Editor changes tone dramatically (e.g., makes conversational academic) → MemoryKeeper tone fingerprint will diverge from baseline; evals flag tone inconsistency
- Editor removes the chapter summary or takeaway → structure eval will flag
- Editor significantly expands text beyond max_tokens → text is truncated at 3000 tokens, which may cut the ending
- Editor returns empty string (rare API error) → pipeline falls back to unedited `human_text`

**Model:** `gpt-4o-mini` (polish task, not generation — mini is sufficient)

---

## Agent 6: Fact Checker

**Purpose:** Cross-checks chapter content against known facts in memory and RAG.

**Why this prompt:** The structured output format (ISSUES / CORRECTIONS / VERIFIED FACTS / CHAPTER STATUS) makes machine-parseable fact-check reports easy without requiring full JSON. The `[UNVERIFIED]` tag implements the spec's "abstention rule" — claims that can't be verified are flagged rather than silently passed. The "PASS or NEEDS_REVIEW" binary verdict enables automated pipeline decisions.

**System Prompt:**
```
You are a fact-checker for a book. Review the chapter text against the known facts provided.

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
```

**Known failure modes:**
- Chapter text is truncated to 2000 chars → may miss fact errors in later paragraphs
- Memory has no facts yet (Chapter 1) → only RAG facts available; known-fact cross-check is weak
- LLM marks genuine facts as [UNVERIFIED] due to lack of training data → creates false negatives
- LLM marks plausible fabrications as VERIFIED → this is the hardest failure mode; mitigated by RAG grounding
- CHAPTER STATUS line missing → parser defaults to "NEEDS_REVIEW" conservatively

**Hallucination control:** The citation-or-soften rule is implemented implicitly: the Writer is told to use only facts from the Researcher's output, which are grounded in RAG. The Fact Checker flags deviations. Future work: when NEEDS_REVIEW, automatically re-prompt Writer with corrections before final assembly.

**Model:** `gpt-4o-mini` (comparison task, not generation)

---

## Agent 7: Memory Keeper

**Purpose:** Maintains cross-chapter consistency; extracts tonality fingerprint; repairs on chapter insert.

**Why this prompt:** Two modes — standard review (consistency + tone fingerprint) and repair mode (post-insertion). The TONALITY_SIGNALS section is new: it extracts observable tone markers that can be compared across chapters. This builds the tonality fingerprint stored in memory, enabling both cross-chapter consistency checks and RLHF reward signal computation.

**System Prompt (standard):**
```
You are a continuity editor for a multi-chapter book.
Given a chapter and the book's memory (facts, concepts, characters),
identify any consistency issues and suggest inline fixes.

Also extract the tonality fingerprint: list the specific words, phrases, and stylistic
patterns this chapter uses that define its tone.

Output:
CONSISTENCY_ISSUES: (list issues or "None")
SUGGESTED_FIXES: (list fixes or "None needed")
TONALITY_SIGNALS: (comma-separated list of observed tone markers)
```

**System Prompt (repair mode — post chapter insert):**
```
You are fixing chapter cross-references after a new chapter was inserted.
Update any references like 'Chapter N' to correct numbering if needed.
Output ONLY the corrected text.
```

**Known failure modes:**
- Chapter text truncated to 1500 chars → consistency issues in later paragraphs missed
- TONALITY_SIGNALS empty or "None" → fingerprint not stored; tone consistency tracking fails for this chapter
- Repair mode changes more than cross-references → rare; LLM may rewrite prose; max_tokens=2500 limits damage
- Memory has no facts (early chapters) → only TOC/character consistency can be checked

**Model:** `gpt-4o-mini` (review task, not generation)

---

## Agent 8: Assembler

**Purpose:** Combines all content into publication-ready PDF and DOCX files.

**Why no LLM:** Assembly is deterministic — it converts structured data (section texts, chapter order, TOC entries) into formatted documents. Using an LLM here would add cost and non-determinism with zero benefit.

**PDF features:**
- ReportLab with custom styles
- Roman-numeral pagination for front matter (i, ii, iii…)
- Arabic page numbering starting from Introduction (page 1)
- Title page, TOC, front matter, chapters, back matter — all in spec-required order

**DOCX features:**
- python-docx with heading styles
- Word-native TOC field (auto-updates to real page numbers when opened in Word)
- Proper 1.25" margins

**Known failure modes:**
- Long chapter text overflows ReportLab max paragraph size → handled by line-by-line parsing
- Markdown bold inside a line not parsed correctly → regex `**...**` → `<b>...</b>` handles most cases
- DOCX TOC field requires "Update Fields" in Word to show page numbers → this is expected Word behaviour; stated in README
- Emoji or non-ASCII in chapter text causes ReportLab encoding error → text is passed through without transformation; user should avoid unusual characters in briefs

---

## Tone Presets Reference

| Tone | Description | Avoid | Example Opener |
|---|---|---|---|
| Conversational | Friendly, direct, "you/we", contractions OK | Jargon, passive voice, formal phrases | "Let's talk about something that can genuinely change your life." |
| Academic | Rigorous, evidence-based, formal vocabulary | Colloquialisms, unsupported assertions | "This chapter examines the foundational principles underlying the subject matter." |
| Storyteller | Narrative-driven, vivid, scene-setting | Dry exposition, bullet lists | "It was the kind of morning that changes everything — though she didn't know it yet." |
| Motivational | Energetic, imperatives, short punchy sentences | Hedging, passive constructions, negativity | "You already have everything you need. Now it's time to use it." |
| Witty | Sharp, clever, dry observations, unexpected analogies | Forced jokes, stinging sarcasm | "Money is a lot like a gym membership — everyone has good intentions and most people ignore it." |

---

## Anti-AI Banned Phrase List (30 phrases)

These are banned at the Humanizer level via regex + LLM instruction, and detected at eval time via `check_banned()`:

delve into · it's important to note · landscape of · in today's world · fast-paced world ·
ever-evolving · dive deep · unpack · let's explore · it goes without saying ·
at the end of the day · game-changer · paradigm shift · holistic approach · leverage (verb) ·
synergy · utilize · in the realm of · a testament to · stands as a beacon ·
crucial · vital · pivotal · groundbreaking · revolutionary ·
transformative · comprehensive · robust · cutting-edge · furthermore

---

## RLHF / Evaluation Prompts

### LLM-as-Judge (EvalJudge agent — `gpt-4o`)

**Preference Labeller Prompt:**
```
You are a preference labeller for a book-writing AI.
You will receive two opening paragraphs for the same chapter. One is better.

Score each on:
  - no_ai_tells (0-1): absence of banned AI phrases
  - human_voice (0-1): sounds like a real human author
  - hook_quality (0-1): grabs the reader's attention
  - tone_match (0-1): matches the specified tone

Output ONLY valid JSON:
{
  "chosen": "A" or "B",
  "scores_A": {...},
  "scores_B": {...},
  "rationale": "..."
}
```

**Tonality Reward Scorer Prompt:**
```
You are a tonality fidelity scorer.
Given a text passage and a target tone, score how well the passage matches the tone.
[tone definitions...]
Output ONLY valid JSON:
{
  "tone_score": 0.0,
  "confidence": 0.0,
  "signals_found": ["..."],
  "signals_missing": ["..."],
  "verdict": "PASS" or "FAIL",
  "suggestion": "..."
}
```

**Chapter Quality Judge Prompt:**
```
You are a book quality judge. Evaluate the given chapter excerpt on:
1. structural_completeness (0-1)
2. tonality_fidelity (0-1)
3. ai_tell_absence (0-1)
4. human_voice (0-1)
5. fact_grounding (0-1)
6. callback_integration (0-1)

Output ONLY valid JSON with all scores, overall, failure_analysis, strengths, weaknesses.
```

**Why `gpt-4o` for judge calls:** Rubric adherence — correctly applying a multi-dimensional scoring rubric requires stronger instruction following than `gpt-4o-mini` reliably provides. The judge is called infrequently (once per chapter), so the cost premium is acceptable.
