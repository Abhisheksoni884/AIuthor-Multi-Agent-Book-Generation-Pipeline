# AIuthor — Design Decisions Log

Ten most consequential architectural and implementation choices, with rationale.

---

## Decision 1: Linear DAG Orchestration (not event-driven)

**Choice:** Orchestrate agents in a fixed linear sequence per chapter: Researcher → Writer → Humanizer → Editor → Fact-Checker → Memory Keeper. No dynamic re-routing.

**Alternatives considered:**
- Event-driven (agents publish/subscribe to topics)
- Parallel execution (Writer + Researcher for different chapters concurrently)

**Why we chose this:**
- Book chapters have strict sequential dependencies — later chapters need memory from earlier ones. Parallelism within a book run would break memory consistency.
- A fixed DAG is deterministic and debuggable. Traces map 1:1 to execution steps, which simplifies the observability story.
- Event-driven adds infrastructure complexity (message broker, idempotency) that doesn't buy us anything at this scale.
- The linear model is easy to extend: inserting a new agent is a single line in `pipeline.py`.

**Trade-off:** Slower wall-clock time for long books. Mitigation: can parallelise across independent books, not within a book.

---

## Decision 2: External JSON Memory (not a vector database)

**Choice:** `BookMemory` persists to a plain JSON file. No Redis, no Pinecone, no SQLite.

**Why:**
- The spec says "single context window does not count." We need durable, indexed memory — but a book run has a bounded number of facts (hundreds, not millions).
- JSON files are fully inspectable, diffable, and require zero infrastructure. They're the best "memory schema document" — you can open and read them.
- JSON load/save is synchronous, which keeps the pipeline simple.
- Includes: fact registry, concept bible, callback index, character registry, chapter summaries, TOC, tonality fingerprint, decision log.

**When to graduate:** At scale (1000s of books, millions of facts), replace with a vector-indexed document store (e.g., Weaviate or pgvector) with schema validation.

---

## Decision 3: Two-Pass Humanizer (Regex then LLM)

**Choice:** Humanizer runs a mechanical regex pass first, then an LLM rewrite pass.

**Why:**
- Regex is free, deterministic, and catches the worst offenders ("delve into", "utilize") with zero latency.
- The LLM pass catches contextual issues the regex can't (passive voice, monotone rhythm, hedge phrases) while benefiting from the pre-cleaned input.
- Two-pass means the LLM starts with already-improved text, giving it a smaller improvement delta to achieve — more reliable output.

**Trade-off:** Two API calls per chapter vs. one. Cost delta is minimal (regex has zero cost).

---

## Decision 4: Model Routing by Agent Role

**Choice:** Generation agents (Writer, Humanizer) use `gpt-4o`; extraction/review agents (Planner, Researcher, Editor, FactChecker, MemoryKeeper) use `gpt-4o-mini`. Judge calls also use `gpt-4o`.

**Why:**
- `gpt-4o` produces measurably better prose quality, richer metaphors, and more consistent tone — this matters only where the output is the final reader-facing text.
- `gpt-4o-mini` is 33× cheaper for input tokens and sufficient for structured extraction, JSON parsing, and fact-checking against known facts.
- Routing by agent role (not by prompt length or complexity) is simple to reason about and maintain.

**Cost impact:** ~40-50% cost reduction vs. using `gpt-4o` everywhere for a 10-chapter book.

---

## Decision 5: RAG with FAISS + Chunking + Reranking

**Choice:** Use FAISS flat index with OpenAI embeddings, chunk external documents (300 words, 50 overlap), and apply keyword-overlap reranking on top of dense retrieval.

**Why:**
- FAISS is fast, zero-infrastructure, and runs in-process — no separate vector DB to deploy.
- Chunking at 300 words balances retrieval precision (too large = noisy) vs. context loss (too small = fragmented).
- 50-word overlap prevents facts split across chunk boundaries from being missed.
- Reranking (even simple keyword overlap) improves precision over pure cosine similarity for short factual queries.

**Fallback:** When no API key is present, BM25-style keyword scoring over raw documents ensures the pipeline still produces grounded output.

**When to graduate:** Swap FAISS for a hosted index (Pinecone, Weaviate) for multi-user scenarios. Use a cross-encoder reranker (e.g., BGE-reranker) for better precision.

---

## Decision 6: Tone as a First-Class Cascade Parameter

**Choice:** Tone is not just a chapter-level parameter — it cascades through every surface: chapters, preface, foreword, acknowledgments, glossary definitions, about-the-author, back-cover copy.

**Why:**
- The spec is explicit: tone must cascade through "every surface," not just chapter bodies.
- A reader who picks up an Academic-tone book should find academic prose even in the acknowledgments — not generic "thank you" boilerplate.
- Implementation: each `write_front_matter` and `write_back_matter` call receives a tone-specific prompt variant. Glossary definitions are rewritten in the target tone by a separate LLM call.

**Trade-off:** More LLM calls for front/back matter. Cost is still small (<$0.02 for 10 extra calls at `gpt-4o-mini` rates).

---

## Decision 7: Applied RLHF Without Base Model Training

**Choice:** Implement RLHF-awareness through three concrete applied techniques: preference pair collection, reward-model-lite tonality scoring (LLM-as-judge), and rubric-based chapter evaluation.

**Why:**
- Training a base model in 3 days is impossible. But showing *applied awareness* — understanding how RLHF works and instrumenting for it — is exactly what the spec requires.
- Preference pairs (raw vs. humanized openings, labelled by a GPT-4o judge) are the direct input format for DPO training.
- The reward scorer produces a signal that, at scale, would drive PPO: keep generations with high tone fidelity, resample low-scoring ones.
- All pairs are saved as JSONL at `output/traces/{run_id}_preference_pairs.jsonl` — ready to feed into a DPO trainer with zero transformation.

**Graduation path to full DPO:**
1. Collect 1000+ preference pairs across diverse topics and tones
2. Fine-tune Writer/Humanizer using Hugging Face `trl` DPO trainer
3. Deploy reward model as a separate inference endpoint
4. Use PPO (via `trl.PPOTrainer`) with RM scores as reward signal

---

## Decision 8: Pydantic Schema Validation at Agent Boundaries

**Choice:** Every inter-agent data contract is defined as a Pydantic model in `core/schemas.py`. Planner output is validated via `validate_book_plan()` before any downstream agent uses it.

**Why:**
- The spec requires "structured outputs... enforced via JSON schema or typed outputs, not regex over prose." Pydantic is the idiomatic Python choice for this.
- Validation catches LLM hallucinations at the boundary (e.g., a `num` field that's a string instead of int) before they propagate into chapter generation.
- Pydantic models serve as living documentation of the inter-agent contract.

**Failure mode handling:** If Pydantic validation fails, the pipeline logs the error to the trace and continues with the raw dict (graceful degradation, not hard crash).

---

## Decision 9: Complete Prompt Logging (No Truncation)

**Choice:** Every LLM call logs the complete system prompt and user prompt to the trace JSON. No truncation.

**Why:**
- The spec is explicit: "Hidden or reconstructed prompts = rejection."
- Complete logs are essential for debugging tone drift, hallucinations, and unexpected outputs.
- Trace files are large (~5-10MB for a 10-chapter book) but this is acceptable given the observability requirement.

**Implementation:** `core/tracer.py` records `system_prompt` and `user_prompt` as separate full-text fields. The legacy `prompt` field is left empty to preserve backward compatibility with any tooling that reads the old format.

---

## Decision 10: Memory I/O Logging as a Separate Artifact

**Choice:** Every BookMemory read and write is logged to a separate `{run_id}_memory_io.json` file, distinct from the agent call trace.

**Why:**
- The spec requires "memory I/O log" as a distinct observable — not just the final memory snapshot.
- Separating memory I/O from agent traces makes it possible to audit: "what did the MemoryKeeper write to memory for Chapter 3?" without parsing full LLM responses.
- Read vs. write counts provide a quick sanity check: a chapter with zero memory reads is probably missing callbacks.

**Schema:** Each event has: `{operation: "read"|"write", key: "fact:...", value: "...", chapter: N, agent: "...", timestamp: "..."}`.
