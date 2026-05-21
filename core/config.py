"""
core/config.py - Central configuration for Book Factory
"""
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Tone presets
TONES = {
    "conversational": {
        "name": "Conversational",
        "description": "Friendly, direct, like talking to a knowledgeable friend. Use 'you' and 'we'. Short sentences. Contractions OK.",
        "avoid": "jargon, passive voice, overly formal phrases",
        "example_opener": "Let's talk about something that can genuinely change your life."
    },
    "academic": {
        "name": "Academic",
        "description": "Rigorous, precise, evidence-based. Third person preferred. Cite claims. Formal vocabulary.",
        "avoid": "colloquialisms, unsupported assertions, first-person casual remarks",
        "example_opener": "This chapter examines the foundational principles underlying the subject matter."
    },
    "storyteller": {
        "name": "Storyteller",
        "description": "Narrative-driven, vivid, immersive. Use scene-setting, characters, sensory detail. Draw readers in.",
        "avoid": "dry exposition, bullet lists, clinical language",
        "example_opener": "It was the kind of morning that changes everything — though she didn't know it yet."
    },
    "motivational": {
        "name": "Motivational",
        "description": "Energetic, empowering, action-oriented. Use imperatives. Believe in the reader. Short punchy sentences.",
        "avoid": "hedging, passive constructions, negativity framing",
        "example_opener": "You already have everything you need. Now it's time to use it."
    },
    "witty": {
        "name": "Witty",
        "description": "Sharp, clever, lightly humorous. Unexpected analogies. Dry observations. Smart but not smug.",
        "avoid": "forced jokes, sarcasm that stings, puns that don't land",
        "example_opener": "Money is a lot like a gym membership — everyone has good intentions and most people ignore it."
    }
}

# Anti-AI phrases to humanize
BANNED_PHRASES = [
    "delve into", "it's important to note", "landscape of", "in conclusion",
    "it is worth noting", "furthermore", "moreover", "in today's world",
    "fast-paced world", "ever-evolving", "dive deep", "unpack",
    "let's explore", "it goes without saying", "needless to say",
    "at the end of the day", "game-changer", "paradigm shift",
    "holistic approach", "leverage", "synergy", "utilize",
    "in the realm of", "a testament to", "stands as a beacon",
    "crucial", "vital", "pivotal", "groundbreaking", "revolutionary",
    "transformative", "comprehensive", "robust", "cutting-edge"
]

# Output paths
OUTPUT_DIR = "output"
PDF_DIR = f"{OUTPUT_DIR}/pdfs"
DOCX_DIR = f"{OUTPUT_DIR}/docx"
TRACES_DIR = f"{OUTPUT_DIR}/traces"

# Token budget per agent call (for cost tracking)
MAX_TOKENS_PER_CALL = 3000
