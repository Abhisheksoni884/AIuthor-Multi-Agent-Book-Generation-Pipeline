"""
core/rlhf.py - Applied RLHF/DPO awareness module

Implements three concrete applied techniques without training a base model:

1. PreferenceCollector  — generates (chosen, rejected) pairs for Humanizer openings
2. TonalityRewardScorer — reward-model-lite: LLM-as-judge scoring for tonality fidelity
3. LLMJudge             — rubric-based evaluator that scores any text on multiple dimensions

At scale, these pairs feed into a real DPO/RLHF training loop:
  - Pairs → DPO dataset → fine-tune Writer/Humanizer on preference signal
  - Reward scorer → online RLHF: score generations, resample, prefer top-k
  - Judge → automated regression suite on every model update

References:
  - Rafailov et al., "Direct Preference Optimization" (2023)
  - Ouyang et al., "Training language models to follow instructions with human feedback" (2022)
  - Bai et al., "Constitutional AI: Harmlessness from AI Feedback" (2022)
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional
from core.llm import call_llm
from core.schemas import PreferencePair


# ────────────────────────────────────────────────────────────────────────────
# 1. Preference Collector (for Humanizer openings)
# ────────────────────────────────────────────────────────────────────────────

PREFERENCE_SYSTEM = """You are a preference labeller for a book-writing AI.
You will receive two opening paragraphs for the same chapter. One is better.

Score each on:
  - no_ai_tells (0-1): absence of banned AI phrases
  - human_voice (0-1): sounds like a real human author
  - hook_quality (0-1): grabs the reader's attention
  - tone_match (0-1): matches the specified tone

Output ONLY valid JSON:
{
  "chosen": "A" or "B",
  "scores_A": {"no_ai_tells": 0.0, "human_voice": 0.0, "hook_quality": 0.0, "tone_match": 0.0},
  "scores_B": {"no_ai_tells": 0.0, "human_voice": 0.0, "hook_quality": 0.0, "tone_match": 0.0},
  "rationale": "..."
}"""


def generate_preference_pair(
    chapter_num: int,
    tone: str,
    opening_a: str,
    opening_b: str,
    tracer=None
) -> PreferencePair:
    """
    Ask an LLM judge to label which opening paragraph is preferred.
    Returns a PreferencePair with rubric scores for both candidates.

    In a full DPO pipeline, these pairs are written to a dataset and used
    to fine-tune the Writer/Humanizer with the DPO loss:
        loss = -log σ(β log π_θ(y_chosen|x) / π_ref(y_chosen|x)
                     - β log π_θ(y_rejected|x) / π_ref(y_rejected|x))
    """
    user = f"""Tone: {tone}
Chapter: {chapter_num}

Opening A:
{opening_a[:600]}

Opening B:
{opening_b[:600]}

Which is better? Return JSON only."""

    raw = call_llm(
        system=PREFERENCE_SYSTEM,
        user=user,
        tracer=tracer,
        agent_name="EvalJudge",
        max_tokens=400,
        temperature=0.0
    )

    try:
        data = json.loads(raw)
    except Exception:
        # Fallback: default to A if parse fails
        data = {"chosen": "A", "scores_A": {}, "scores_B": {}, "rationale": "parse error"}

    chosen_text = opening_a if data.get("chosen") == "A" else opening_b
    rejected_text = opening_b if data.get("chosen") == "A" else opening_a

    return PreferencePair(
        context=f"Ch{chapter_num}:{tone}:humanizer_opening",
        chosen=chosen_text,
        rejected=rejected_text,
        rubric_scores={
            "chosen_scores": data.get("scores_A" if data.get("chosen") == "A" else "scores_B", {}),
            "rejected_scores": data.get("scores_B" if data.get("chosen") == "A" else "scores_A", {}),
        },
        rationale=data.get("rationale", "")
    )


# ────────────────────────────────────────────────────────────────────────────
# 2. Tonality Reward Scorer (reward-model-lite)
# ────────────────────────────────────────────────────────────────────────────

REWARD_SYSTEM = """You are a tonality fidelity scorer.
Given a text passage and a target tone, score how well the passage matches the tone.

Tones:
  - conversational: friendly, "you/we", contractions, short sentences
  - academic: rigorous, evidence-based, third person, formal vocabulary
  - storyteller: narrative, vivid, scene-setting, sensory detail
  - motivational: energetic, imperatives, short punchy sentences, empowering
  - witty: sharp, clever, unexpected analogies, dry observations

Output ONLY valid JSON:
{
  "tone_score": 0.0,
  "confidence": 0.0,
  "signals_found": ["..."],
  "signals_missing": ["..."],
  "verdict": "PASS" or "FAIL",
  "suggestion": "..."
}"""


@dataclass
class ToneScore:
    tone_score: float
    confidence: float
    signals_found: list
    signals_missing: list
    verdict: str
    suggestion: str


def score_tonality(text: str, expected_tone: str, tracer=None) -> ToneScore:
    """
    Score how well a text passage matches the target tone (0–1).
    This is the reward-model-lite: in a full RLHF loop, this score
    would be used as the reward signal to resample Writer outputs.

    Graduating to full RLHF:
      1. Collect (prompt, output, reward) triples across many runs
      2. Train a lightweight reward model (RM) on these triples
      3. Run PPO: use RM.score(x) as reward to update Writer policy
      4. Periodically distil RM improvements back into DPO pairs
    """
    user = f"""Target tone: {expected_tone}

Text passage (first 800 chars):
{text[:800]}

Score the tonality fidelity. Return JSON only."""

    raw = call_llm(
        system=REWARD_SYSTEM,
        user=user,
        tracer=tracer,
        agent_name="EvalJudge",
        max_tokens=300,
        temperature=0.0
    )

    try:
        d = json.loads(raw)
        return ToneScore(
            tone_score=float(d.get("tone_score", 0.5)),
            confidence=float(d.get("confidence", 0.5)),
            signals_found=d.get("signals_found", []),
            signals_missing=d.get("signals_missing", []),
            verdict=d.get("verdict", "PASS"),
            suggestion=d.get("suggestion", "")
        )
    except Exception:
        return ToneScore(0.5, 0.5, [], [], "PASS", "parse error")


# ────────────────────────────────────────────────────────────────────────────
# 3. LLM-as-Judge (full rubric evaluation)
# ────────────────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are a book quality judge. Evaluate the given chapter excerpt on these dimensions:

1. structural_completeness (0-1): has hook, sections, summary, takeaway
2. tonality_fidelity (0-1): matches the specified tone throughout
3. ai_tell_absence (0-1): free of AI clichés and banned phrases
4. human_voice (0-1): reads like a real human author
5. fact_grounding (0-1): specific facts/examples vs. generic claims
6. callback_integration (0-1): references prior chapters naturally (or N/A if ch1)

Output ONLY valid JSON:
{
  "structural_completeness": 0.0,
  "tonality_fidelity": 0.0,
  "ai_tell_absence": 0.0,
  "human_voice": 0.0,
  "fact_grounding": 0.0,
  "callback_integration": 0.0,
  "overall": 0.0,
  "failure_analysis": "...",
  "strengths": ["..."],
  "weaknesses": ["..."]
}"""


@dataclass
class JudgeScore:
    structural_completeness: float
    tonality_fidelity: float
    ai_tell_absence: float
    human_voice: float
    fact_grounding: float
    callback_integration: float
    overall: float
    failure_analysis: str
    strengths: list
    weaknesses: list


def judge_chapter(
    chapter_text: str,
    tone: str,
    chapter_num: int,
    tracer=None
) -> JudgeScore:
    """
    Full LLM-as-judge evaluation of a chapter with rubric scores.
    Returns a JudgeScore with per-dimension floats and failure analysis.
    """
    user = f"""Tone: {tone}
Chapter: {chapter_num}

Chapter text (first 1200 chars):
{chapter_text[:1200]}

Evaluate on all dimensions. Return JSON only."""

    raw = call_llm(
        system=JUDGE_SYSTEM,
        user=user,
        tracer=tracer,
        agent_name="EvalJudge",
        max_tokens=500,
        temperature=0.0
    )

    try:
        d = json.loads(raw)
        return JudgeScore(
            structural_completeness=float(d.get("structural_completeness", 0.5)),
            tonality_fidelity=float(d.get("tonality_fidelity", 0.5)),
            ai_tell_absence=float(d.get("ai_tell_absence", 0.5)),
            human_voice=float(d.get("human_voice", 0.5)),
            fact_grounding=float(d.get("fact_grounding", 0.5)),
            callback_integration=float(d.get("callback_integration", 0.5)),
            overall=float(d.get("overall", 0.5)),
            failure_analysis=d.get("failure_analysis", ""),
            strengths=d.get("strengths", []),
            weaknesses=d.get("weaknesses", [])
        )
    except Exception:
        return JudgeScore(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, "parse error", [], [])


# ────────────────────────────────────────────────────────────────────────────
# Preference pair file I/O
# ────────────────────────────────────────────────────────────────────────────

def save_preference_pairs(pairs: list[PreferencePair], path: str):
    """Save preference pairs as a JSONL dataset (ready for DPO training)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair.model_dump()) + "\n")


def load_preference_pairs(path: str) -> list[PreferencePair]:
    """Load preference pairs from a JSONL file."""
    pairs = []
    if not os.path.exists(path):
        return pairs
    with open(path) as f:
        for line in f:
            pairs.append(PreferencePair.model_validate(json.loads(line)))
    return pairs
