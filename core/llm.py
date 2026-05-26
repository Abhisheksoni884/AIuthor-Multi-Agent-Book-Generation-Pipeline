"""
core/llm.py - OpenAI wrapper with full prompt logging, model routing, and tracer integration

Model routing strategy:
  - GENERATION agents (Writer, Humanizer)   → gpt-4o  (best prose quality)
  - EXTRACTION agents (Researcher, Planner) → gpt-4o-mini (structured JSON, cheaper)
  - REVIEW agents (Editor, FactChecker, MemoryKeeper) → gpt-4o-mini (fast, sufficient)
  - JUDGE calls (LLM-as-judge in evals)     → gpt-4o (better rubric adherence)
"""
import time
import os
from openai import OpenAI
from core.config import OPENAI_MODEL, MAX_TOKENS_PER_CALL

# Agent → model routing table
# Override per-call with `model=` parameter; this table provides smart defaults.
AGENT_MODEL_ROUTING = {
    # Generation — highest quality
    "Writer":       "gpt-4o-mini",
    "Humanizer":    "gpt-4o-mini",
    # Extraction / planning — cheaper, fast
    "Planner":      "gpt-4o-mini",
    "Researcher":   "gpt-4o-mini",
    # Review / judgement — mini is sufficient
    "Editor":       "gpt-4o-mini",
    "FactChecker":  "gpt-4o-mini",
    "MemoryKeeper": "gpt-4o-mini",
    # Eval judge — needs rubric adherence
    "EvalJudge":    "gpt-4o-mini",
    # Default fallback
    "default":      OPENAI_MODEL,
}


def _route_model(agent_name: str, model_override: str = None) -> str:
    """Return the appropriate model for a given agent, respecting overrides."""
    if model_override:
        return model_override
    # Match on prefix (e.g. "Writer-Ch3" → "Writer")
    for prefix, model in AGENT_MODEL_ROUTING.items():
        if agent_name.startswith(prefix):
            return model
    return AGENT_MODEL_ROUTING["default"]


def call_llm(
    system: str,
    user: str,
    tracer=None,
    agent_name: str = "unknown",
    max_tokens: int = MAX_TOKENS_PER_CALL,
    notes: str = "",
    model: str = None,          # explicit override; None = auto-route
    temperature: float = 0.7,
) -> str:
    """
    Call OpenAI chat completion with automatic model routing.
    Logs the COMPLETE system + user prompt (no truncation) to the tracer.
    Returns the assistant's text response.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_openai_api_key_here":
        # Demo mode: return a placeholder
        return f"[DEMO MODE — set OPENAI_API_KEY] {agent_name} would generate content here for: {user[:100]}"

    selected_model = _route_model(agent_name, model)
    client = OpenAI(api_key=api_key)
    start = time.time()

    response = client.chat.completions.create(
        model=selected_model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ]
    )

    duration = time.time() - start
    text = response.choices[0].message.content or ""
    in_tok = response.usage.prompt_tokens
    out_tok = response.usage.completion_tokens

    if tracer:
        tracer.record(
            agent=agent_name,
            prompt="",               # legacy field — left empty; use system/user below
            response=text,           # FULL response
            input_tokens=in_tok,
            output_tokens=out_tok,
            duration=duration,
            notes=notes,
            system_prompt=system,    # FULL system prompt
            user_prompt=user,        # FULL user prompt
            model=selected_model,
        )
    return text
