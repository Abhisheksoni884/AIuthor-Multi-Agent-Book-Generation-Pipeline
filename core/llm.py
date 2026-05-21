"""
core/llm.py - Thin wrapper around OpenAI with token counting and tracer integration
"""
import time
import os
from openai import OpenAI
from core.config import OPENAI_MODEL, MAX_TOKENS_PER_CALL


def call_llm(
    system: str,
    user: str,
    tracer=None,
    agent_name: str = "unknown",
    max_tokens: int = MAX_TOKENS_PER_CALL,
    notes: str = ""
) -> str:
    """
    Call OpenAI chat completion.
    Returns the assistant's text response.
    Optionally records to a RunTracer.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_openai_api_key_here":
        # Demo mode: return a placeholder
        return f"[DEMO MODE — set OPENAI_API_KEY] {agent_name} would generate content here for: {user[:100]}"

    client = OpenAI(api_key=api_key)
    start = time.time()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
    )

    duration = time.time() - start
    text = response.choices[0].message.content or ""
    in_tok = response.usage.prompt_tokens
    out_tok = response.usage.completion_tokens

    if tracer:
        tracer.record(
            agent=agent_name,
            prompt=f"SYS: {system[:200]}\nUSER: {user[:200]}",
            response=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            duration=duration,
            notes=notes
        )
    return text
