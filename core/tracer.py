"""
core/tracer.py - Per-run observability: agent traces, complete prompt logs, memory I/O log, token/cost ledger
"""
import json
import time
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
from rich.console import Console
from rich.table import Table

console = Console()

# Model pricing table (per 1K tokens, USD)
MODEL_PRICING = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.000150, "output": 0.000600},
    "gpt-4-turbo": {"input": 0.010, "output": 0.030},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}
# fallback
DEFAULT_COST_INPUT = 0.000150
DEFAULT_COST_OUTPUT = 0.000600


@dataclass
class AgentTrace:
    agent: str
    system_prompt: str       # FULL system prompt — no truncation
    user_prompt: str         # FULL user prompt — no truncation
    response: str            # FULL response — no truncation
    model: str
    input_tokens: int
    output_tokens: int
    duration_sec: float
    cost_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""


@dataclass
class MemoryIOEvent:
    """Records every read or write to BookMemory."""
    operation: str        # "read" or "write"
    key: str              # e.g. "fact:compound_interest", "concept:index_fund", "summary:ch3"
    value: str            # the data read or written (summary)
    chapter: int
    agent: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class RunTracer:
    """Tracks all agent calls and memory I/O for a single book-generation run."""

    def __init__(self, run_id: str, traces_dir: str = "output/traces"):
        self.run_id = run_id
        self.traces: list[AgentTrace] = []
        self.memory_io: list[MemoryIOEvent] = []
        self.traces_dir = traces_dir
        os.makedirs(traces_dir, exist_ok=True)
        self.start_time = time.time()

    def record(
        self,
        agent: str,
        prompt: str,          # kept for backward compat — use system/user instead
        response: str,
        input_tokens: int,
        output_tokens: int,
        duration: float,
        notes: str = "",
        system_prompt: str = "",
        user_prompt: str = "",
        model: str = "gpt-4o-mini"
    ):
        pricing = MODEL_PRICING.get(model, {})
        cost_in = pricing.get("input", DEFAULT_COST_INPUT)
        cost_out = pricing.get("output", DEFAULT_COST_OUTPUT)
        cost = (input_tokens / 1000 * cost_in) + (output_tokens / 1000 * cost_out)

        # Use explicit system/user if provided; otherwise split legacy prompt
        sys_p = system_prompt if system_prompt else prompt
        usr_p = user_prompt if user_prompt else ""

        trace = AgentTrace(
            agent=agent,
            system_prompt=sys_p,      # FULL — no truncation
            user_prompt=usr_p,        # FULL — no truncation
            response=response,        # FULL — no truncation
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_sec=round(duration, 2),
            cost_usd=round(cost, 6),
            notes=notes
        )
        self.traces.append(trace)
        console.print(f"  [dim]▸ {agent}[/dim] [green]{input_tokens}in/{output_tokens}out tokens[/green] [yellow]${cost:.4f}[/yellow]")

    def log_memory_read(self, key: str, value: str, chapter: int, agent: str):
        """Record a memory read event."""
        self.memory_io.append(MemoryIOEvent(
            operation="read", key=key, value=str(value)[:500], chapter=chapter, agent=agent
        ))

    def log_memory_write(self, key: str, value: str, chapter: int, agent: str):
        """Record a memory write event."""
        self.memory_io.append(MemoryIOEvent(
            operation="write", key=key, value=str(value)[:500], chapter=chapter, agent=agent
        ))

    def total_tokens(self):
        return sum(t.input_tokens + t.output_tokens for t in self.traces)

    def total_cost(self):
        return sum(t.cost_usd for t in self.traces)

    def save(self):
        # Save full agent trace (complete prompts, no truncation)
        trace_path = os.path.join(self.traces_dir, f"{self.run_id}_trace.json")
        trace_data = {
            "run_id": self.run_id,
            "total_tokens": self.total_tokens(),
            "total_cost_usd": round(self.total_cost(), 4),
            "total_duration_sec": round(time.time() - self.start_time, 2),
            "agents": [asdict(t) for t in self.traces]
        }
        with open(trace_path, "w") as f:
            json.dump(trace_data, f, indent=2)

        # Save memory I/O log separately
        mem_io_path = os.path.join(self.traces_dir, f"{self.run_id}_memory_io.json")
        mem_io_data = {
            "run_id": self.run_id,
            "total_events": len(self.memory_io),
            "reads": sum(1 for e in self.memory_io if e.operation == "read"),
            "writes": sum(1 for e in self.memory_io if e.operation == "write"),
            "events": [asdict(e) for e in self.memory_io]
        }
        with open(mem_io_path, "w") as f:
            json.dump(mem_io_data, f, indent=2)

        return trace_path

    def print_summary(self):
        table = Table(title=f"Run: {self.run_id}", show_lines=True)
        table.add_column("Agent", style="cyan")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost (USD)", justify="right", style="yellow")
        table.add_column("Duration", justify="right")
        for t in self.traces:
            table.add_row(
                t.agent,
                str(t.input_tokens + t.output_tokens),
                f"${t.cost_usd:.4f}",
                f"{t.duration_sec}s"
            )
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{self.total_tokens()}[/bold]",
            f"[bold]${self.total_cost():.4f}[/bold]",
            f"[bold]{round(time.time() - self.start_time, 1)}s[/bold]"
        )
        console.print(table)
