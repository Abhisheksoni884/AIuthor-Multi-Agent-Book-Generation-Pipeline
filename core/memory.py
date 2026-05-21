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

    # --- Facts ---
    def add_fact(self, key: str, value: str, source: str, chapter: int):
        self.facts[key] = Fact(key=key, value=value, source=source, chapter=chapter)

    def get_fact(self, key: str) -> Optional[str]:
        f = self.facts.get(key)
        return f.value if f else None

    def all_facts_text(self) -> str:
        if not self.facts:
            return "No facts registered yet."
        lines = [f"- {k}: {v.value} (Ch.{v.chapter})" for k, v in self.facts.items()]
        return "\n".join(lines)

    # --- Concepts ---
    def add_concept(self, term: str, definition: str, chapter: int, related: Optional[List[str]] = None):
        self.concepts[term.lower()] = Concept(
            term=term, definition=definition,
            first_introduced=chapter, related_terms=related or []
        )

    def get_glossary(self) -> list[dict]:
        return [{"term": c.term, "definition": c.definition}
                for c in sorted(self.concepts.values(), key=lambda x: x.term)]

    # --- Callbacks ---
    def add_callback(self, reference: str, chapter_defined: int):
        self.callbacks.append(Callback(reference=reference, chapter_defined=chapter_defined))

    def get_callbacks_for(self, chapter: int) -> list[str]:
        return [cb.reference for cb in self.callbacks if cb.chapter_defined < chapter]

    # --- Characters (fiction) ---
    def add_character(self, name: str, description: str, first_chapter: int):
        self.characters[name] = {
            "description": description,
            "first_chapter": first_chapter,
            "appearances": [first_chapter]
        }

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
    def set_chapter_summary(self, chapter: int, summary: str):
        self.chapter_summaries[chapter] = summary

    def get_prior_summaries(self, up_to_chapter: int) -> str:
        lines = []
        for i in range(1, up_to_chapter):
            if i in self.chapter_summaries:
                lines.append(f"Chapter {i}: {self.chapter_summaries[i]}")
        return "\n".join(lines) if lines else "No prior chapters."

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
        """Re-number facts/summaries/toc after inserting a chapter."""
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
            "toc": self.toc
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
        return m
