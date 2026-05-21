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
| `core/llm.py` | Thin OpenAI wrapper with token counting and tracer hook |
| `core/memory.py` | BookMemory: facts, concepts, callbacks, characters, TOC |
| `core/rag.py` | FAISS vector store; keyword fallback when no API key |
| `core/tracer.py` | RunTracer: records every LLM call with tokens/cost/timing |

### Agents

| Agent | File | LLM calls | Output |
|---|---|---|---|
| Planner | `agents/planner.py` | 1 | JSON book plan |
| Researcher | `agents/researcher.py` | 1 per chapter | Research brief dict |
| Writer | `agents/writer.py` | 1 per chapter + front/back matter | Markdown text |
| Humanizer | `agents/humanizer.py` | 1 per chapter (+ mechanical pass) | Cleaned text |
| Editor | `agents/editor.py` | 1 per chapter | Edited text |
| Fact Checker | `agents/fact_checker.py` | 1 per chapter | Report dict |
| Memory Keeper | `agents/memory_keeper.py` | 1 per chapter | Report dict |
| Assembler | `agents/assembler.py` | 0 (no LLM) | PDF + DOCX files |

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
                              title page, TOC, page numbers
  docx/
    BookTitle.docx          ← python-docx, heading styles, proper margins
  traces/
    {run_id}_trace.json     ← all agent calls with tokens/cost
    {run_id}_memory.json    ← full memory snapshot
    {run_id}_factcheck.json ← per-chapter fact-check reports
    {run_id}_result.json    ← book plan + chapter texts (for C/D tests)
    eval_report.json        ← automated eval scores
```

---

## Token Budget Estimate (gpt-4o-mini)

| Stage | Calls | Avg tokens | Total |
|---|---|---|---|
| Planner | 1 | 2,000 | 2,000 |
| Researcher (per ch) | N | 800 | 800N |
| Writer (per ch) | N | 3,000 | 3,000N |
| Humanizer (per ch) | N | 3,000 | 3,000N |
| Editor (per ch) | N | 3,000 | 3,000N |
| Fact Checker (per ch) | N | 600 | 600N |
| Memory Keeper (per ch) | N | 500 | 500N |
| Front/Back matter | ~8 | 500 | 4,000 |

**10-chapter book:** ~2,000 + (11,400 × 10) + 4,000 ≈ **120,000 tokens ≈ $0.07–$0.12**
