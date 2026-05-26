# AIuthor — Multi-Agent Book Generation Pipeline

> **A production-grade, agentic system that transforms a one-line brief into a publication-ready book — with full front/back matter, cross-chapter memory, tone-consistent prose, and complete observability.**

---

## What it does

Give AIuthor a brief like _"a practical guide to personal finance for millennials"_ and it produces:

- A complete **PDF + DOCX** book with title page, 9 front matter sections, all chapters, and 6 back matter sections
- **Human-quality prose** — two-pass AI-tell elimination (regex + LLM)
- **Tone-consistent writing** across every surface (chapters, preface, glossary, back-cover copy)
- **Grounded facts** via RAG retrieval with FAISS + OpenAI embeddings
- **Cross-chapter memory** — facts, character arcs, and callbacks persist through the book
- **Full observability** — complete prompt logs, memory I/O log, token/cost ledger, LLM-as-judge scores
- **Applied RLHF** — preference pair collection and tonality reward scoring wired into every run

---

## Quick Start

```bash
# 1. Activate the book_env environment
pyenv activate book_env      # or: source ~/.pyenv/versions/book_env/bin/activate

# 2. Install dependencies (already done in book_env)
pip install -r requirements.txt

# 3. Configure API key
cp .env.example .env
# Edit .env → set OPENAI_API_KEY=sk-...

# 4. Run interactive mode
python main.py

# 5. Or run a predefined test case
python main.py --test A    # 10-chapter personal finance guide (Conversational)
python main.py --test B    # 5-chapter novella with recurring characters (Storyteller)
python main.py --test C    # Regenerate Ch.3 of Test A in 3 different tones
python main.py --test D    # Insert new chapter with self-healing repair

# 6. Run automated evaluations
python tests/evals.py
python tests/evals.py --judge   # include LLM-as-judge scores (costs tokens)
```

**Demo mode:** Without an API key, the pipeline runs fully — orchestration, memory, RAG keyword fallback, tracing, and file assembly all work. Set `OPENAI_API_KEY` for live generation.

---

## Command-Line Interface

```bash
python main.py [OPTIONS]

Options:
  --brief      Book description / topic
  --tone       conversational | academic | storyteller | motivational | witty
  --chapters   Number of chapters (default: 5)
  --words      Target words per chapter (default: 2000)
  --output     Output directory (default: output/)
  --test       A | B | C | D  (predefined test cases)

Examples:
  python main.py --brief "Urban gardening for beginners" --tone conversational --chapters 8
  python main.py --test A
  python main.py --test D    # requires Test A to have been run first
```

---

## Architecture

### The 8-Agent Pipeline

Linear DAG: each chapter flows through all agents sequentially. Cross-chapter dependencies are handled through **BookMemory** (persistent JSON state).

```
Brief
  └─► Planner (1 call)
        └─► For each chapter:
              Researcher → Writer → Humanizer → Editor → Fact Checker → Memory Keeper
                                                                            │
                                                                     RLHF Judge (preference pair + rubric score)
        └─► Front Matter (9 sections, tone-matched)
        └─► Back Matter  (6 sections, tone-matched)
        └─► Assembler (no LLM — deterministic)
              └─► PDF  (roman-numeral front matter, arabic body pages)
              └─► DOCX (Word-native TOC field, heading styles)
```

| # | Agent | Model | Responsibility |
|---|---|---|---|
| 1 | **Planner** | gpt-4o-mini | Brief → validated `BookPlan` JSON with full front/back matter structure |
| 2 | **Researcher** | gpt-4o-mini | RAG retrieval + concept extraction + callback identification per chapter |
| 3 | **Writer** | **gpt-4o** | Full chapter text + all 15 front/back matter sections in the target tone |
| 4 | **Humanizer** | **gpt-4o** | 2-pass AI-tell elimination: regex mechanical pass → LLM rewrite |
| 5 | **Editor** | gpt-4o-mini | Grammar, tone consistency, flow, structure enforcement |
| 6 | **Fact Checker** | gpt-4o-mini | Cross-checks against memory + RAG; flags `[UNVERIFIED]` claims |
| 7 | **Memory Keeper** | gpt-4o-mini | Consistency check + tonality fingerprint extraction per chapter |
| 8 | **Assembler** | _no LLM_ | PDF + DOCX with roman/arabic dual pagination, Word TOC field |
| — | **EvalJudge** | **gpt-4o** | RLHF preference labelling + 6-dimension rubric scoring per chapter |

### Core Modules

| Module | What it does |
|---|---|
| `core/llm.py` | OpenAI wrapper with **model routing** + full prompt logging (zero truncation) |
| `core/memory.py` | BookMemory: facts, concepts, callbacks, characters, TOC, **tonality fingerprint**, **decision log** |
| `core/rag.py` | FAISS + OpenAI embeddings; **document ingestion** (`add_documents`/`ingest_file`); keyword reranking; BM25 fallback |
| `core/tracer.py` | RunTracer: complete prompt logs, **memory I/O log**, token/cost ledger per call |
| `core/schemas.py` | **Pydantic models** for all inter-agent data contracts (`BookPlan`, `ResearchBrief`, `FactCheckReport`, `PreferencePair`) |
| `core/rlhf.py` | **Applied RLHF**: preference pair collector, tonality reward scorer, LLM-as-judge (6-dimension rubric) |

---

## 5 Tone Presets

Tone cascades through **every surface** — chapter prose, preface, foreword, acknowledgments, glossary definitions, about-the-author, and back-cover copy.

| Tone | Feel | Characteristics | Avoid |
|---|---|---|---|
| **Conversational** | Talking to a knowledgeable friend | "you/we", contractions, short sentences | Jargon, passive voice, formal phrases |
| **Academic** | Rigorous, evidence-based | Third person, formal vocabulary, cited claims | Colloquialisms, unsupported assertions |
| **Storyteller** | Narrative, vivid, immersive | Scene-setting, sensory detail, character focus | Dry exposition, bullet lists |
| **Motivational** | Energetic, empowering | Imperatives, short punchy sentences, belief in reader | Hedging, passive constructions |
| **Witty** | Sharp, clever, dry | Unexpected analogies, dry observations | Forced jokes, sarcasm |

---

## Humanization Strategy

**Two-pass anti-AI-tell system:**

**Pass 1 — Mechanical clean** (regex, zero cost, deterministic)
Eliminates 30 banned phrases: `delve into` · `robust` · `paradigm shift` · `utilize` · `groundbreaking` · `it's important to note` · `in today's world` · `game-changer` · `synergy` · `cutting-edge` · `leverage` (as verb) · and 19 more.

**Pass 2 — LLM rewrite** (`gpt-4o`, contextual)
Enforces: varied sentence length, active voice, no hedge phrases, human rhythm. Preserves facts, headings, and word count.

**RLHF hook:** For every chapter, the raw Writer output and humanized output are submitted to the LLM judge. The preferred opening is recorded as a (chosen, rejected) preference pair — saved as JSONL for DPO fine-tuning.

---

## Memory & Self-Healing

**BookMemory** persists at `output/traces/{run_id}_memory.json`:

```
Facts          → keyed fact registry with chapter attribution
Concepts       → glossary source of truth (term, definition, first_introduced)
Callbacks      → cross-chapter narrative references
Characters     → name, description, appearance list (fiction)
Summaries      → first 200 chars of each chapter (for context injection)
TOC            → live chapter list
Tonality FP    → per-chapter tone signal fingerprint (new)
Decision Log   → every significant agent decision with rationale (new)
```

**Chapter Insertion (Test D) — Self-Healing:**
1. Writer generates the new chapter
2. `memory.repair_after_insert(N)` re-numbers all facts, summaries, TOC, and **tonality fingerprints** ≥ N
3. Memory Keeper repairs cross-references in adjacent chapters (Ch N-1, Ch N+1)
4. Glossary self-heals: rebuilt from `memory.get_glossary()` at assembly time — always correct

---

## Observability — Trace Artifacts

Every run produces these files in `output/traces/`:

| File | Contents |
|---|---|
| `{run_id}_trace.json` | Every LLM call: **complete** system prompt + user prompt + response (no truncation), tokens, cost, duration |
| `{run_id}_memory.json` | Full memory snapshot after run: facts, concepts, fingerprints, decision log |
| `{run_id}_memory_io.json` | Every memory read/write event: key, value, chapter, agent, timestamp |
| `{run_id}_factcheck.json` | Per-chapter fact-check report: issues, corrections, PASS/NEEDS_REVIEW status |
| `{run_id}_judge_scores.json` | LLM-as-judge rubric scores per chapter: structure, tone, human voice, fact grounding, callbacks |
| `{run_id}_preference_pairs.jsonl` | RLHF preference pairs (chosen vs rejected openings) — JSONL, ready for DPO training |
| `{run_id}_decisions.json` | Design decision log: every agent decision with chapter, rationale, timestamp |
| `{run_id}_result.json` | Full book plan + chapter texts (used for Test C/D re-runs) |
| `eval_report.json` | Automated eval scores across 8 dimensions with failure analysis |

---

## Output Files

```
output/
├── pdfs/
│   └── BookTitle.pdf     # Letter, 1.25" margins, roman-numeral front matter (i, ii, iii...),
│                         # arabic page numbers from Introduction (1, 2, 3...)
├── docx/
│   └── BookTitle.docx    # Word-native TOC field (auto-updates in Word), heading styles
└── traces/
    └── {run_id}_*.json / *.jsonl    # full observability suite (see above)
```

> **Note:** Open the DOCX in Word and press `Ctrl+A → F9` (Windows) or `Cmd+A → Fn+F9` (Mac) to update the TOC field with real page numbers.

---

## Automated Evaluations

```bash
python tests/evals.py                    # heuristic-only (free)
python tests/evals.py --judge            # + LLM-as-judge (costs tokens)
python tests/evals.py --run <run_id>     # evaluate a specific run
```

**8 evaluation dimensions (0.0 → 1.0):**

| Dimension | What it measures | How |
|---|---|---|
| **No Banned Phrases** | AI-tell absence | -0.1 per banned phrase found |
| **Word Count** | Structural completeness | Within ±30% of target |
| **Structure** | Hook + subheadings + paragraphs | Regex check |
| **No Repetition** | Unique sentences | Sentence deduplication |
| **Tone Consistency** | Tone-signal keyword presence | Heuristic keyword count |
| **Fact Coverage** | Registered facts mentioned in chapter | Keyword overlap |
| **Callback Recall** | Prior callbacks referenced | Phrase matching |
| **LLM Judge Overall** | 6-dimension rubric (gpt-4o) | structure, tone, human voice, fact grounding, callbacks |

Chapters scoring **< 0.70** get a **failure analysis** with actionable hints per dimension.

---

## Applied RLHF / DPO Awareness

`core/rlhf.py` implements three concrete applied techniques:

1. **Preference Pair Collector** — LLM judge labels (chosen, rejected) pairs for raw vs. humanized chapter openings. Saved as JSONL at `_preference_pairs.jsonl`.

2. **Tonality Reward Scorer** — Scores any text's tone fidelity (0–1) with signals found/missing. This is the reward-model-lite: at scale it becomes the PPO reward signal.

3. **LLM-as-Judge (EvalJudge)** — Full 6-dimension rubric: structural completeness, tonality fidelity, AI-tell absence, human voice, fact grounding, callback integration.

**Graduation path to full DPO/PPO:**
```
Current:  collect preference pairs → label with judge → save JSONL
Next:     fine-tune Writer/Humanizer using HuggingFace trl.DPOTrainer on the JSONL
Then:     train reward model on (prompt, output, score) triples
Finally:  PPO online loop — RM.score() as reward signal, resample low-scoring generations
```

---

## Test Cases

| Test | Description | Demonstrates |
|---|---|---|
| **A** | 10-chapter personal finance guide, Conversational tone, 2500 words/ch | Multi-chapter memory, RAG grounding, full pipeline |
| **B** | 5-chapter coastal mystery novella, Storyteller tone, 2000 words/ch | Character consistency, fiction callbacks, narrative tone |
| **C** | Regenerate Ch.3 of Test A in Academic, Motivational, and Witty tones | Tone flexibility, same content / different voice |
| **D** | Insert "The Psychology of Spending" between Ch.4 and Ch.5 of Test A | Self-healing: TOC, glossary, callbacks, fingerprints all repaired |

---

## Project Structure

```
AI-Book-Generation-Agent/
├── main.py                     ← entry point (interactive + test modes)
├── pipeline.py                 ← orchestrator: 8-agent linear DAG + RLHF loop
├── requirements.txt
├── .env.example
├── agents/
│   ├── planner.py              ← brief → validated BookPlan JSON
│   ├── researcher.py           ← RAG retrieval + concept/callback extraction
│   ├── writer.py               ← chapter + front/back matter (tone-cascaded)
│   ├── humanizer.py            ← 2-pass AI-tell elimination
│   ├── editor.py               ← tone, grammar, flow, structure
│   ├── fact_checker.py         ← fact cross-check vs memory + RAG
│   ├── memory_keeper.py        ← consistency, tone fingerprint, insert repair
│   └── assembler.py            ← PDF (roman/arabic pagination) + DOCX (TOC field)
├── core/
│   ├── config.py               ← tone presets, banned phrases, model settings
│   ├── llm.py                  ← OpenAI wrapper + model routing + full prompt log
│   ├── memory.py               ← BookMemory: facts, concepts, fingerprints, decision log
│   ├── rag.py                  ← FAISS + chunking + reranking + BM25 fallback
│   ├── schemas.py              ← Pydantic inter-agent contracts (new)
│   ├── tracer.py               ← RunTracer: full logs + memory I/O log
│   └── rlhf.py                 ← Applied RLHF: preference pairs, reward scorer, judge (new)
├── docs/
│   ├── architecture.md         ← full system design
│   ├── prompts_dossier.md      ← every prompt with rationale + failure modes
│   ├── design_decisions.md     ← 10 architectural decisions with trade-offs (new)
│   └── memory_schema.md        ← BookMemory JSON schema + example records (new)
├── tests/
│   └── evals.py                ← 8-dimension eval suite with failure analysis
└── output/                     ← generated (gitignored)
    ├── pdfs/
    ├── docx/
    └── traces/
```

---

## Cost Estimate (mixed model routing)

| Book | Chapters | gpt-4o (gen) | gpt-4o-mini (rest) | Est. Total |
|---|---|---|---|---|
| Short | 5 | ~$0.40 | ~$0.02 | **~$0.42** |
| Medium | 10 | ~$0.75 | ~$0.04 | **~$0.79** |
| Long | 20 | ~$1.50 | ~$0.08 | **~$1.58** |

Vs. all-gpt-4o: ~2–3×. Mixed routing saves ~50% with no quality loss for extraction tasks.

---

## Extending

```python
# Add a new tone
TONES["philosophical"] = {"name": "Philosophical", "description": "...", ...}   # core/config.py

# Add a new agent
# 1. Create agents/my_agent.py with a run() function
# 2. Call call_llm() for LLM interaction
# 3. Wire into pipeline.py between existing steps

# Ingest external documents into RAG
rag.ingest_file("my_reference_doc.txt")   # chunked + embedded automatically

# Expand seed knowledge
SEED_KNOWLEDGE.append("Your new fact here.")   # core/rag.py
```

---

## Docs

| Document | Purpose |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Full system design, data flows, module breakdown |
| [`docs/design_decisions.md`](docs/design_decisions.md) | 10 architectural decisions with alternatives + trade-offs |
| [`docs/prompts_dossier.md`](docs/prompts_dossier.md) | Every agent prompt with rationale and failure modes |
| [`docs/memory_schema.md`](docs/memory_schema.md) | BookMemory JSON schema with example records |
