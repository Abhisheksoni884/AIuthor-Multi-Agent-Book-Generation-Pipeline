# Book Factory — Architecture

## System Overview

Book Factory is a linear multi-agent pipeline that transforms a user brief into a publication-ready book (PDF + DOCX). Eight specialized agents each own one responsibility; shared memory and observability run across all of them.

---

## Architecture Diagram

```
                         USER BRIEF
                             │
                    ┌────────▼────────┐
                    │   1. PLANNER    │  → book_plan (JSON)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  RAG INDEX      │  FAISS + OpenAI embeddings
                    │  (seed facts)   │  keyword fallback if no API key
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │     PER-CHAPTER LOOP         │
              │                             │
              │  ┌─────────────────────┐    │
              │  │  2. RESEARCHER      │ ◄──┼── RAG retrieval
              │  └──────────┬──────────┘    │   + BookMemory
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │  3. WRITER          │ ◄──┼── tone preset
              │  └──────────┬──────────┘    │   + memory context
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │  4. HUMANIZER       │    │   mechanical + LLM
              │  └──────────┬──────────┘    │   removes AI-tells
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │  5. EDITOR          │    │   tone + grammar
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │  6. FACT CHECKER    │ ◄──┼── BookMemory facts
              │  └──────────┬──────────┘    │
              │             │               │
              │  ┌──────────▼──────────┐    │
              │  │  7. MEMORY KEEPER   │ ──►┼── writes to BookMemory
              │  └─────────────────────┘    │
              └──────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │ FRONT MATTER    │  copyright, dedication,
                    │ GENERATION      │  foreword, preface
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ BACK MATTER     │  afterword, glossary,
                    │ GENERATION      │  references, about_author,
                    └────────┬────────┘  back_cover
                             │
                    ┌────────▼────────┐
                    │  8. ASSEMBLER   │  → PDF (ReportLab)
                    └─────────────────┘  → DOCX (python-docx)


  CROSS-CUTTING CONCERNS
  ┌────────────────────────────────────────────┐
  │  BookMemory: facts · concepts · callbacks  │
  │              characters · chapter summaries│
  │              TOC                           │
  ├────────────────────────────────────────────┤
  │  RunTracer: per-call logs · token ledger   │
  │             cost tracking · timing         │
  └────────────────────────────────────────────┘
```

---

## Component Descriptions

### Core Modules

| Module | Responsibility |
|---|---|
| `core/config.py` | Tone presets, banned phrases, model settings |
| `core/llm.py` | OpenAI wrapper with **model routing**, full prompt logging, tracer hook |
| `core/memory.py` | BookMemory: facts, concepts, callbacks, characters, TOC, **tonality fingerprint**, **decision log** |
| `core/rag.py` | FAISS vector store; **document ingestion**; **keyword reranking**; BM25 keyword fallback |
| `core/tracer.py` | RunTracer: full prompt logs (no truncation), **memory I/O log**, token/cost ledger |
| `core/schemas.py` | **Pydantic models** for all inter-agent data contracts (BookPlan, ResearchBrief, etc.) |
| `core/rlhf.py` | **Applied RLHF**: preference pair collection, tonality reward scorer, LLM-as-judge |

### Agents

| Agent | File | Model | LLM calls | Output |
|---|---|---|---|---|
| Planner | `agents/planner.py` | gpt-4o-mini | 1 | Validated `BookPlan` JSON |
| Researcher | `agents/researcher.py` | gpt-4o-mini | 1 per chapter | Research brief dict |
| Writer | `agents/writer.py` | **gpt-4o** | 1 per chapter + front/back matter | Markdown text |
| Humanizer | `agents/humanizer.py` | **gpt-4o** | 1 per chapter (+ mechanical pass) | Cleaned text |
| Editor | `agents/editor.py` | gpt-4o-mini | 1 per chapter | Edited text |
| Fact Checker | `agents/fact_checker.py` | gpt-4o-mini | 1 per chapter | Report dict |
| Memory Keeper | `agents/memory_keeper.py` | gpt-4o-mini | 1 per chapter | Report + **tone fingerprint** |
| Assembler | `agents/assembler.py` | 0 (no LLM) | 0 | PDF + DOCX files |
| EvalJudge | `core/rlhf.py` | **gpt-4o** | 1 per chapter | Preference pair + judge score |

---

## Data Flow

```
brief (str)
  → book_plan (dict, JSON)
    → [per chapter] chapter_plan (dict)
      → research (dict: facts, concepts, callbacks)
        → raw_text (str, markdown)
          → human_text (str)
            → edited_text (str)
              → fact_check_report (dict)
              → memory_update (side effect)
  → front_matter (dict: section → str)
  → back_matter (dict: section → str)
    → PDF (file)
    → DOCX (file)
    → trace.json (file)
    → memory.json (file)
    → factcheck.json (file)
```

---

## Memory System

`BookMemory` is a plain Python object (no database) that persists to JSON:

- **Fact registry** — keyed facts with chapter attribution  
- **Concept bible** — term → definition, first introduced chapter  
- **Callback index** — cross-chapter references  
- **Character registry** — name, description, appearance list (fiction)  
- **Chapter summaries** — first 200 chars of each chapter  
- **TOC** — current chapter list with numbers

On chapter insertion, `repair_after_insert(n)` re-numbers all facts, summaries, and TOC entries with `chapter >= n`.

---

## RAG Design

Seed knowledge (~17 facts) is embedded with OpenAI embeddings into a FAISS flat index at run start. Each Researcher call retrieves top-3 by cosine similarity. Falls back to keyword overlap when no API key is present (demo mode).

---

## Observability

`RunTracer` records every `call_llm()` invocation:
- Agent name
- Truncated prompt (500 chars)
- Truncated response (500 chars)
- Input / output token counts
- Duration (seconds)
- Cost (USD, per-call and total)

Saved to `output/traces/{run_id}_trace.json`. Printed as a Rich table at end of run.

---

## Output Files

```
output/
  pdfs/
    BookTitle.pdf           ← ReportLab, letter size, 1.25" margins,
                              title page, roman-numeral front matter (i, ii, iii...),
                              arabic page numbers from Introduction (1, 2, 3...)
  docx/
    BookTitle.docx          ← python-docx, Word-native TOC field, heading styles
  traces/
    {run_id}_trace.json          ← all agent calls with FULL prompts (no truncation)
    {run_id}_memory.json         ← full memory snapshot (facts, concepts, fingerprints, decisions)
    {run_id}_memory_io.json      ← every memory read/write event (new)
    {run_id}_factcheck.json      ← per-chapter fact-check reports
    {run_id}_judge_scores.json   ← LLM-as-judge rubric scores per chapter (new)
    {run_id}_preference_pairs.jsonl ← RLHF preference pairs (new, JSONL for DPO training)
    {run_id}_decisions.json      ← design decision log from memory (new)
    {run_id}_result.json         ← book plan + chapter texts (for C/D tests)
    eval_report.json             ← automated eval scores with failure analysis
```

---

## Token Budget Estimate

### gpt-4o (generation) + gpt-4o-mini (extraction/review)

| Stage | Model | Calls | Avg tokens | Total |
|---|---|---|---|---|
| Planner | gpt-4o-mini | 1 | 2,000 | 2,000 |
| Researcher (per ch) | gpt-4o-mini | N | 800 | 800N |
| Writer (per ch) | **gpt-4o** | N | 3,500 | 3,500N |
| Humanizer (per ch) | **gpt-4o** | N | 3,500 | 3,500N |
| Editor (per ch) | gpt-4o-mini | N | 3,000 | 3,000N |
| Fact Checker (per ch) | gpt-4o-mini | N | 600 | 600N |
| Memory Keeper (per ch) | gpt-4o-mini | N | 600 | 600N |
| RLHF Judge (per ch) | **gpt-4o** | N | 500 | 500N |
| Front/Back matter | gpt-4o-mini | ~12 | 600 | 7,200 |

**10-chapter book (mixed models):**
~2,000 + (12,500 × 10) + 7,200 ≈ **134,000 tokens**
- gpt-4o tokens (Writer+Humanizer+Judge): ~75,000 → ~$0.75–$1.50
- gpt-4o-mini tokens (rest): ~59,000 → ~$0.04
- **Total estimated cost: ~$0.80–$1.55 per book**

Vs. all gpt-4o: ~$2.00–$3.00. Mixed routing saves ~50%.
