# AIuthor — Memory Schema

Concrete data models for `BookMemory`, with example records.

---

## Overview

`BookMemory` is a plain Python object that persists to JSON at `output/traces/{run_id}_memory.json`.
It is loaded/saved via `BookMemory.save()` / `BookMemory.load()`.

---

## Schema

```json
{
  "facts": {
    "<fact_key>": {
      "key": "string",
      "value": "string",
      "source": "string",
      "chapter": 0
    }
  },
  "concepts": {
    "<term_lowercase>": {
      "term": "string",
      "definition": "string",
      "first_introduced": 0,
      "related_terms": ["string"]
    }
  },
  "callbacks": [
    {
      "reference": "string",
      "chapter_defined": 0,
      "chapter_used": [0]
    }
  ],
  "characters": {
    "<name>": {
      "description": "string",
      "first_chapter": 0,
      "appearances": [0]
    }
  },
  "chapter_summaries": {
    "<chapter_num_str>": "string"
  },
  "toc": [
    {
      "num": 0,
      "title": "string",
      "page_est": 0
    }
  ],
  "tonality_fingerprint": {
    "<chapter_num_str>": "string"
  },
  "decision_log": [
    {
      "chapter": 0,
      "agent": "string",
      "decision": "string",
      "rationale": "string",
      "timestamp": "ISO8601 string"
    }
  ]
}
```

---

## Example Record — Personal Finance Book (Test A, after Chapter 2)

```json
{
  "facts": {
    "ch1_fact0": {
      "key": "ch1_fact0",
      "value": "The 50/30/20 rule allocates 50% to needs, 30% to wants, 20% to savings",
      "source": "Chapter 1",
      "chapter": 1
    },
    "ch1_fact1": {
      "key": "ch1_fact1",
      "value": "An emergency fund should cover 3-6 months of living expenses",
      "source": "Chapter 1",
      "chapter": 1
    },
    "ch2_fact0": {
      "key": "ch2_fact0",
      "value": "Compound interest at 7% annually doubles money in approximately 10 years (Rule of 72)",
      "source": "Chapter 2",
      "chapter": 2
    }
  },
  "concepts": {
    "compound interest": {
      "term": "Compound Interest",
      "definition": "Interest calculated on both the principal and the accumulated interest from previous periods",
      "first_introduced": 2,
      "related_terms": ["interest rate", "principal", "time horizon"]
    },
    "emergency fund": {
      "term": "Emergency Fund",
      "definition": "A dedicated savings buffer covering 3-6 months of living expenses for unexpected events",
      "first_introduced": 1,
      "related_terms": ["savings", "liquidity", "financial safety net"]
    }
  },
  "callbacks": [
    {
      "reference": "the budgeting foundation we built in Chapter 1",
      "chapter_defined": 2,
      "chapter_used": []
    }
  ],
  "characters": {},
  "chapter_summaries": {
    "1": "Money is not just a numbers game. The 50/30/20 rule gives you a simple framework to start",
    "2": "Compound interest is the engine of long-term wealth. Starting with just $100/month at 22"
  },
  "toc": [
    {"num": 1, "title": "The Money Mindset: Why Most People Stay Broke", "page_est": 0},
    {"num": 2, "title": "Compound Interest: The Eighth Wonder", "page_est": 0},
    {"num": 3, "title": "Building Your Budget That Actually Works", "page_est": 0}
  ],
  "tonality_fingerprint": {
    "1": "uses 'you' 23 times, contractions throughout, short punchy sentences, informal register",
    "2": "uses 'you' 18 times, conversational metaphors, numbered lists avoided, anecdote-led"
  },
  "decision_log": [
    {
      "chapter": 0,
      "agent": "Planner",
      "decision": "Book plan created: 'Your Money, Your Future' (10 chapters, conversational tone)",
      "rationale": "Planner agent transforms user brief into a structured JSON plan with full front/back matter",
      "timestamp": "2025-01-15T10:23:41.123456"
    },
    {
      "chapter": 2,
      "agent": "MemoryKeeper",
      "decision": "Tone fingerprint recorded: uses 'you' 18 times, conversational metaphors",
      "rationale": "Tracking per-chapter tone signals enables cross-chapter consistency checks",
      "timestamp": "2025-01-15T10:31:02.654321"
    }
  ]
}
```

---

## Example Record — Fiction Novella (Test B, after Chapter 1)

```json
{
  "facts": {},
  "concepts": {
    "the lighthouse": {
      "term": "The Lighthouse",
      "definition": "The decommissioned Harrow Point lighthouse that went dark at the start of the story",
      "first_introduced": 1,
      "related_terms": ["Harrow Point", "Maya", "mystery"]
    }
  },
  "callbacks": [
    {
      "reference": "the night Maya first saw the lighthouse go dark",
      "chapter_defined": 1,
      "chapter_used": []
    }
  ],
  "characters": {
    "Maya": {
      "description": "Fearless, curious 16-year-old who discovers the lighthouse mystery. Brown hair, quick reflexes.",
      "first_chapter": 1,
      "appearances": [1]
    },
    "Daniel": {
      "description": "Careful, methodical best friend of Maya. Cautious but loyal. Carries a worn notebook everywhere.",
      "first_chapter": 1,
      "appearances": [1]
    }
  },
  "chapter_summaries": {
    "1": "It was the kind of night that changes everything. Maya stood at the edge of Harrow Point"
  },
  "toc": [
    {"num": 1, "title": "The Night the Light Went Out", "page_est": 0},
    {"num": 2, "title": "What the Tide Brought In", "page_est": 0}
  ],
  "tonality_fingerprint": {
    "1": "third-person close, past tense, sensory details (smell of salt, cold stone), scene-setting opener"
  },
  "decision_log": [
    {
      "chapter": 0,
      "agent": "Planner",
      "decision": "Book plan created: 'The Dark at Harrow Point' (5 chapters, storyteller tone)",
      "rationale": "Planner agent transforms user brief into a structured JSON plan with full front/back matter",
      "timestamp": "2025-01-15T11:00:00.000000"
    }
  ]
}
```

---

## Memory Operations

| Operation | Method | Tracer key format |
|---|---|---|
| Add fact | `memory.add_fact(key, value, source, chapter)` | `fact:{key}` |
| Read fact | `memory.get_fact(key)` | `fact:{key}` |
| Add concept | `memory.add_concept(term, definition, chapter)` | `concept:{term}` |
| Add callback | `memory.add_callback(reference, chapter_defined)` | `callback:ch{N}` |
| Get callbacks | `memory.get_callbacks_for(chapter)` | `callbacks:up_to_ch{N}` |
| Add character | `memory.add_character(name, description, chapter)` | `character:{name}` |
| Set summary | `memory.set_chapter_summary(chapter, summary)` | `summary:ch{N}` |
| Get summaries | `memory.get_prior_summaries(up_to_chapter)` | `summaries:up_to_ch{N}` |
| Set tone fingerprint | `memory.set_tonality_fingerprint(chapter, signals)` | `tone_fingerprint:ch{N}` |
| Log decision | `memory.log_decision(chapter, agent, decision, rationale)` | — (append-only list) |
| Insert repair | `memory.repair_after_insert(inserted_at)` | — (re-numbers all keys ≥ N) |

---

## Chapter Insert Repair Behaviour

When `insert_chapter()` is called to insert at position N:

1. `memory.repair_after_insert(N)` increments all fact/summary/fingerprint chapter numbers ≥ N
2. `memory_keeper.repair_for_insert()` fixes cross-reference text in adjacent chapters (Ch N-1 and Ch N+1)
3. The glossary is automatically consistent — it is rebuilt from `memory.get_glossary()` at assembly time, which returns concepts sorted alphabetically with their correct (now re-numbered) `first_introduced` values
4. The TOC in memory is re-numbered; the PDF/DOCX TOC is regenerated from scratch by the Assembler
