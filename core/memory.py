"""
core/memory.py - Cross-chapter memory: fact registry, concept bible, callback index
"""
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class Fact:
    key: str          # e.g. "compound_interest_rate"
    value: str        # e.g. "7% average annual stock market return"
    source: str       # e.g. "Chapter 2"
    chapter: int


@dataclass
class Concept:
    term: str
    definition: str
    first_introduced: int  # chapter number
    related_terms: list[str] = field(default_factory=list)


@dataclass
class Callback:
    reference: str      # e.g. "the story of Maria from Chapter 1"
    chapter_defined: int
    chapter_used: list[int] = field(default_factory=list)


class BookMemory:
    """Persistent cross-chapter memory for a book run."""

    def __init__(self):
        self.facts: dict[str, Fact] = {}
        self.concepts: dict[str, Concept] = {}
        self.callbacks: list[Callback] = []
        self.characters: dict[str, dict] = {}  # for fiction
        self.chapter_summaries: dict[int, str] = {}
        self.toc: list[dict] = []  # [{num, title, page_est}]
        # --- New fields ---
        self.tonality_fingerprint: dict[str, str] = {}  # chapter_num_str → observed tone signals
        self.decision_log: list[dict] = []              # [{chapter, agent, decision, rationale}]

    # --- Facts ---
    def add_fact(self, key: str, value: str, source: str, chapter: int, tracer=None, agent: str = ""):
        self.facts[key] = Fact(key=key, value=value, source=source, chapter=chapter)
        if tracer:
            tracer.log_memory_write(f"fact:{key}", value, chapter, agent or "unknown")

    def get_fact(self, key: str, tracer=None, agent: str = "", chapter: int = 0) -> Optional[str]:
        f = self.facts.get(key)
        val = f.value if f else None
        if tracer and val:
            tracer.log_memory_read(f"fact:{key}", val, chapter, agent or "unknown")
        return val

    def all_facts_text(self) -> str:
        if not self.facts:
            return "No facts registered yet."
        lines = [f"- {k}: {v.value} (Ch.{v.chapter})" for k, v in self.facts.items()]
        return "\n".join(lines)

    # --- Concepts ---
    def add_concept(self, term: str, definition: str, chapter: int, related: Optional[List[str]] = None, tracer=None, agent: str = ""):
        self.concepts[term.lower()] = Concept(
            term=term, definition=definition,
            first_introduced=chapter, related_terms=related or []
        )
        if tracer:
            tracer.log_memory_write(f"concept:{term}", definition, chapter, agent or "unknown")

    def get_glossary(self) -> list[dict]:
        return [{"term": c.term, "definition": c.definition}
                for c in sorted(self.concepts.values(), key=lambda x: x.term)]

    # --- Callbacks ---
    def add_callback(self, reference: str, chapter_defined: int, tracer=None, agent: str = ""):
        self.callbacks.append(Callback(reference=reference, chapter_defined=chapter_defined))
        if tracer:
            tracer.log_memory_write(f"callback:ch{chapter_defined}", reference, chapter_defined, agent or "unknown")

    def get_callbacks_for(self, chapter: int, tracer=None, agent: str = "") -> list[str]:
        refs = [cb.reference for cb in self.callbacks if cb.chapter_defined < chapter]
        if tracer and refs:
            tracer.log_memory_read(f"callbacks:up_to_ch{chapter}", str(refs)[:200], chapter, agent or "unknown")
        return refs

    # --- Characters (fiction) ---
    def add_character(self, name: str, description: str, first_chapter: int, tracer=None, agent: str = ""):
        self.characters[name] = {
            "description": description,
            "first_chapter": first_chapter,
            "appearances": [first_chapter]
        }
        if tracer:
            tracer.log_memory_write(f"character:{name}", description, first_chapter, agent or "unknown")

    def note_character_appearance(self, name: str, chapter: int):
        if name in self.characters:
            self.characters[name]["appearances"].append(chapter)

    def characters_summary(self) -> str:
        if not self.characters:
            return ""
        lines = [f"- {n}: {d['description']} (first in Ch.{d['first_chapter']})"
                 for n, d in self.characters.items()]
        return "\n".join(lines)

    # --- Chapter summaries ---
    def set_chapter_summary(self, chapter: int, summary: str, tracer=None, agent: str = ""):
        self.chapter_summaries[chapter] = summary
        if tracer:
            tracer.log_memory_write(f"summary:ch{chapter}", summary[:200], chapter, agent or "unknown")

    def get_prior_summaries(self, up_to_chapter: int, tracer=None, agent: str = "") -> str:
        lines = []
        for i in range(1, up_to_chapter):
            if i in self.chapter_summaries:
                lines.append(f"Chapter {i}: {self.chapter_summaries[i]}")
        result = "\n".join(lines) if lines else "No prior chapters."
        if tracer and lines:
            tracer.log_memory_read(f"summaries:up_to_ch{up_to_chapter}", result[:300], up_to_chapter, agent or "unknown")
        return result

    # --- Tonality fingerprint ---
    def set_tonality_fingerprint(self, chapter: int, signals: str, tracer=None, agent: str = ""):
        """Record detected tone signals for a chapter (for cross-chapter consistency checks)."""
        self.tonality_fingerprint[str(chapter)] = signals
        if tracer:
            tracer.log_memory_write(f"tone_fingerprint:ch{chapter}", signals, chapter, agent or "unknown")

    def get_tonality_fingerprint(self, chapter: int) -> str:
        return self.tonality_fingerprint.get(str(chapter), "")

    def get_all_tone_fingerprints(self) -> dict:
        return self.tonality_fingerprint

    # --- Decision log ---
    def log_decision(self, chapter: int, agent: str, decision: str, rationale: str):
        """Record a significant orchestration decision for the design log."""
        self.decision_log.append({
            "chapter": chapter,
            "agent": agent,
            "decision": decision,
            "rationale": rationale,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        })

    # --- TOC ---
    def set_toc(self, toc: list[dict]):
        self.toc = toc

    def get_toc_text(self) -> str:
        if not self.toc:
            return ""
        lines = [f"Chapter {item['num']}: {item['title']}" for item in self.toc]
        return "\n".join(lines)

    # --- Repair after insertion ---
    def repair_after_insert(self, inserted_at: int):
        """Re-number facts/summaries/toc/fingerprints after inserting a chapter."""
        new_facts = {}
        for k, v in self.facts.items():
            if v.chapter >= inserted_at:
                v.chapter += 1
            new_facts[k] = v
        self.facts = new_facts

        new_summaries = {}
        for ch, s in self.chapter_summaries.items():
            new_ch = ch + 1 if ch >= inserted_at else ch
            new_summaries[new_ch] = s
        self.chapter_summaries = new_summaries

        # Re-number tonality fingerprints
        new_fingerprints = {}
        for ch_str, signals in self.tonality_fingerprint.items():
            ch = int(ch_str)
            new_ch = ch + 1 if ch >= inserted_at else ch
            new_fingerprints[str(new_ch)] = signals
        self.tonality_fingerprint = new_fingerprints

        for item in self.toc:
            if item["num"] >= inserted_at:
                item["num"] += 1

    # --- Serialise ---
    def to_dict(self) -> dict:
        return {
            "facts": {k: asdict(v) for k, v in self.facts.items()},
            "concepts": {k: asdict(v) for k, v in self.concepts.items()},
            "callbacks": [asdict(c) for c in self.callbacks],
            "characters": self.characters,
            "chapter_summaries": self.chapter_summaries,
            "toc": self.toc,
            "tonality_fingerprint": self.tonality_fingerprint,
            "decision_log": self.decision_log,
        }

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "BookMemory":
        with open(path) as f:
            data = json.load(f)
        m = cls()
        for k, v in data.get("facts", {}).items():
            m.facts[k] = Fact(**v)
        for k, v in data.get("concepts", {}).items():
            m.concepts[k] = Concept(**v)
        for c in data.get("callbacks", []):
            m.callbacks.append(Callback(**c))
        m.characters = data.get("characters", {})
        m.chapter_summaries = {int(k): v for k, v in data.get("chapter_summaries", {}).items()}
        m.toc = data.get("toc", [])
        m.tonality_fingerprint = data.get("tonality_fingerprint", {})
        m.decision_log = data.get("decision_log", [])
        return m
