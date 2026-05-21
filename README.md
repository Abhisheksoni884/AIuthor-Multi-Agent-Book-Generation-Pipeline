# AIuthor — Multi-Agent Book Generation Pipeline

**A production-grade, agentic system that transforms a brief into publication-ready books with full front/back matter, cross-chapter memory, and human-quality prose.**
---

## Overview

AIuthor is an 8-agent orchestrated pipeline that generates complete, publication-ready books from a single user brief. The system demonstrates applied AI engineering through RAG-grounded research, structured outputs, cross-chapter memory, anti-AI humanization, and comprehensive observability.

**Key Features:**
- 8 specialized agents with clear separation of concerns
- 5 tone presets that cascade through all content (prose, front matter, back matter, glossary)
- Cross-chapter memory with fact registry, concept bible, and callback index
- RAG-based fact grounding using FAISS + OpenAI embeddings
- Two-pass humanization (mechanical + LLM) to eliminate AI-tell phrases
- Full observability: agent traces, prompt logs, token/cost tracking
- Publication-ready output: PDF (ReportLab) + DOCX (python-docx) with TOC, page numbers, proper formatting
- Self-healing chapter insertion with automatic TOC and callback repair

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API key
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...

# 3. Run interactive mode
python main.py

# 4. Or run a test case
python main.py --test A    # 10-chapter personal finance guide (Conversational)
python main.py --test B    # 5-chapter novella with recurring characters (Storyteller)
python main.py --test C    # Regenerate Ch.3 of Test A in 3 different tones
python main.py --test D    # Insert new chapter in Test A with self-healing

# 5. Run automated evaluations
python tests/evals.py
```

---

## Command-Line Interface

```bash
# Interactive mode (prompts for all inputs)
python main.py

# Custom book with specific parameters
python main.py --brief "A practical guide to urban gardening" \
               --tone conversational \
               --chapters 8 \
               --words 2500

# Run specific test case
python main.py --test A

Options:
  --brief      Book description/topic (required for custom books)
  --tone       conversational | academic | storyteller | motivational | witty
  --chapters   Number of chapters (default: 5)
  --words      Target words per chapter (default: 2000)
  --output     Output directory (default: output/)
  --test       A | B | C | D (predefined test cases)
```

---

## Demo Mode

Without an OpenAI API key, the pipeline runs in demo mode with placeholder LLM outputs. All orchestration, memory management, RAG retrieval (keyword fallback), tracing, and file assembly work normally. Set `OPENAI_API_KEY` in `.env` for full generation.

---

## Architecture

### The 8-Agent Pipeline

The system uses a linear orchestration pattern where each agent has a single, well-defined responsibility:

| # | Agent | Responsibility | LLM Calls | Key Outputs |
|---|---|---|---|---|
| **1** | **Planner** | Transforms user brief into structured book plan | 1 | JSON book plan with chapters, characters, glossary terms, front/back matter sections |
| **2** | **Researcher** | Retrieves grounded facts via RAG, identifies concepts and callbacks | 1 per chapter | Research brief with facts, concepts, callback opportunities |
| **3** | **Writer** | Generates full chapter content in specified tone with consistent structure | 1 per chapter + front/back matter | Markdown chapter text (~2000-2500 words) |
| **4** | **Humanizer** | Strips AI-tell phrases using mechanical regex + LLM rewrite | 1 per chapter | Cleaned, human-sounding text |
| **5** | **Editor** | Ensures tone consistency, fixes grammar, improves flow | 1 per chapter | Polished, publication-ready text |
| **6** | **Fact Checker** | Cross-checks claims against memory and RAG knowledge base | 1 per chapter | Fact-check report with status (PASS/NEEDS_REVIEW) |
| **7** | **Memory Keeper** | Maintains cross-chapter consistency, repairs numbering on insertion | 1 per chapter + repairs | Consistency report, updated memory |
| **8** | **Assembler** | Combines all content into PDF and DOCX with proper formatting | 0 (no LLM) | PDF + DOCX files with TOC, page numbers |

**Orchestration Pattern:** Linear pipeline with per-chapter loops. Each chapter goes through agents 2-7 sequentially before moving to the next chapter.

**Data Flow:** Brief → Book Plan → [Per Chapter: Research → Write → Humanize → Edit → Fact-check → Memory Update] → Front Matter → Back Matter → Assembly

### Cross-Cutting Systems

**BookMemory** — Persistent cross-chapter state:
- Fact registry (keyed facts with chapter attribution)
- Concept bible (term definitions with first introduction)
- Callback index (cross-chapter references)
- Character registry (for fiction: name, description, appearances)
- Chapter summaries (first 200 chars of each chapter)
- TOC (current chapter list with numbers)

**BookRAG** — FAISS vector store with OpenAI embeddings:
- 17 seed facts covering personal finance and general knowledge
- Top-k similarity search for grounded research
- Keyword fallback when no API key (demo mode)

**RunTracer** — Complete observability per run:
- Every LLM call logged with truncated prompt/response
- Token counts (input/output) and cost per call
- Duration tracking
- Saved to JSON with summary table

---

## 5 Tone Presets

Tones cascade through **all** content surfaces: chapter prose, front matter, back matter, glossary definitions, about-the-author, and back-cover copy.

| Tone | Description | Characteristics | Avoid |
|---|---|---|---|
| **Conversational** | Friendly, direct, like talking to a knowledgeable friend | "you/we", contractions, short sentences | Jargon, passive voice, overly formal phrases |
| **Academic** | Rigorous, precise, evidence-based | Third person, formal vocabulary, cited claims | Colloquialisms, unsupported assertions, casual remarks |
| **Storyteller** | Narrative-driven, vivid, immersive | Scene-setting, sensory detail, character focus | Dry exposition, bullet lists, clinical language |
| **Motivational** | Energetic, empowering, action-oriented | Imperatives, short punchy sentences, belief in reader | Hedging, passive constructions, negativity |
| **Witty** | Sharp, clever, lightly humorous | Unexpected analogies, dry observations, smart but not smug | Forced jokes, stinging sarcasm, puns that don't land |

---

## Humanization Strategy

The Humanizer agent uses a **two-pass approach** to eliminate AI-tell phrases:

**Pass 1: Mechanical Cleaning** (regex-based, deterministic)
- Fast pattern matching for 30+ banned phrases
- Replacements: "delve into" → "explore", "utilize" → "use", "at the end of the day" → "ultimately"
- Removes common AI tells like "it's important to note", "in today's fast-paced world", "paradigm shift"

**Pass 2: LLM Rewrite** (contextual, nuanced)
- System prompt with strict rules: vary sentence length, break up 30+ word sentences, replace passive voice
- Preserves facts, headings, structure, and word count
- Focuses on making prose feel genuinely human-written

**Banned Phrase List (30 phrases):**
delve into · it's important to note · landscape of · in today's world · fast-paced world · ever-evolving · dive deep · unpack · let's explore · it goes without saying · at the end of the day · game-changer · paradigm shift · holistic approach · leverage (verb) · synergy · utilize · in the realm of · a testament to · stands as a beacon · crucial · vital · pivotal · groundbreaking · revolutionary · transformative · comprehensive · robust · cutting-edge · furthermore

---

## Memory & Self-Healing

**Cross-Chapter Memory:**
- Facts are registered with chapter attribution and retrieved for later chapters
- Concepts are defined once and added to the glossary
- Callbacks create narrative continuity (e.g., "the story of Maria from Chapter 1")
- Characters (fiction) track appearances across chapters

**Chapter Insertion with Self-Healing (Test D):**
1. Insert new chapter at specified position
2. Shift all subsequent chapter numbers in book plan
3. Shift all chapter numbers in existing chapter texts
4. Update fact registry chapter attributions
5. Update chapter summaries dictionary
6. Rebuild TOC with correct numbering
7. Repair cross-references in adjacent chapters (e.g., "Chapter 5" → "Chapter 6")

The Memory Keeper agent handles all repairs automatically when `insert_chapter()` is called.

---

## Output Files

```
output/
├── pdfs/
│   └── BookTitle.pdf              # ReportLab PDF with title page, TOC, page numbers
├── docx/
│   └── BookTitle.docx             # python-docx with heading styles, proper margins
└── traces/
    ├── {run_id}_trace.json        # Complete agent trace with tokens/cost/timing
    ├── {run_id}_memory.json       # Memory snapshot: facts, concepts, callbacks, TOC
    ├── {run_id}_factcheck.json    # Per-chapter fact-check reports
    ├── {run_id}_result.json       # Book plan + chapter texts (for Test C/D)
    └── eval_report.json           # Automated evaluation scores
```

**PDF Features:**
- Letter size (8.5" × 11"), 1.25" margins
- Title page with book title, subtitle, author
- Table of contents with chapter listings
- Page numbers on all pages
- Custom styles for headings and body text

**DOCX Features:**
- Proper heading styles (Heading 1, Heading 2)
- 1.25" margins, readable fonts
- Working table of contents
- Paragraph spacing and formatting

---

## Test Cases

The system includes 4 predefined test cases that demonstrate different capabilities:

**Test A: Personal Finance Guide**
- 10 chapters, Conversational tone, ~2,500 words/chapter
- Topic: Practical personal finance (budgeting, saving, investing, debt, wealth building)
- Tests: Multi-chapter consistency, fact grounding, conversational tone

**Test B: Coastal Mystery Novella**
- 5 chapters, Storyteller tone, ~2,000 words/chapter
- Characters: Maya (fearless, curious) and Daniel (careful, methodical)
- Topic: Two friends investigating a mysterious lighthouse in a coastal town
- Tests: Character consistency across chapters, narrative tone, fiction callbacks

**Test C: Multi-Tone Regeneration**
- Prerequisite: Run Test A first
- Regenerates Chapter 3 of Test A in three different tones: Academic, Motivational, Wit

- Tests: Tone flexibility, same content with different voice

**Test D: Chapter Insertion + Self-Healing**
- Prerequisite: Run Test A first
- Inserts new chapter between Chapter 4 and 5: "The Psychology of Spending"
- Tests: TOC repair, callback updates, chapter number shifting, memory consistency

---

## Automated Evaluations

Run `python tests/evals.py` to execute automated quality checks:

**Per-Chapter Checks:**
1. **No Banned Phrases** — Deducts 0.1 per AI-tell phrase found (target: 1.0)
2. **Word Count** — Within ±30% of target word count (target: 1.0)
3. **Structure** — Has H1 heading, 2+ subheadings, 3+ paragraphs (target: 1.0)
4. **No Repetition** — Same sentence doesn't appear twice (target: 1.0)
5. **Tone Consi---
Key tone signals present (target: 1.0)

**Scoring:**
- Each check returns 0.0 to 1.0
- Average score per chapter
- Overall average across all chapters
- Color-coded output: green (≥0.8), yellow (≥0.5), red (<0.5)

**Output:**
- Rich table with per-chapter scores
- File existence checks (pdfs/, docx/, traces/)
- Saved to `output/traces/eval_report.json`
## Project Structure

```
book_factory/
├── main.py               ← entry point
├── pipeline.py           ← orchestrator
├── requirements.txt
├── .env.example
├── agents/
│   ├── planner.py
│   ├── researcher.py
│   ├── writer.py
│   ├── humanizer.py
│   ├── editor.py
│   ├── fact_checker.py
│   ├── memory_keeper.py
│   └── assembler.py
├── core/
│   ├── config.py         ← tones, banned phrases, settings
│   ├── llm.py            ← OpenAI wrapper + token tracking
│   ├── memory.py         ← BookMemory
│   ├── rag.py            ← FAISS vector search
│   └── tracer.py         ← RunTracer observability
├── docs/
│   ├── architecture.md
│   └── prompts_dossier.md
├── tests/
│   └── evals.py
└── output/               ← generated (gitignored)
    ├── pdfs/
    ├── docx/
    └── traces/
```

---

## Cost Estimate (gpt-4o-mini)

| Book | Chapters | Approx Cost |
|---|---|---|
| Short (5 ch) | 5 | ~$0.04 |
| Medium (10 ch) | 10 | ~$0.08 |
| Long (20 ch) | 20 | ~$0.16 |

---

## Extending

- **Add a new tone:** Add entry to `TONES` dict in `core/config.py`
- **Add a new agent:** Create `agents/my_agent.py`, call `call_llm()`, wire into `pipeline.py`
- **Expand RAG knowledge:** Add to `SEED_KNOWLEDGE` in `core/rag.py`
- **Custom output format:** Add new assembler function in `agents/assembler.py`
