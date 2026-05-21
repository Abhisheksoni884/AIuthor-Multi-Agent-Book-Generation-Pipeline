"""
core/tracer.py - Per-run observability: agent traces, prompt logs, token/cost ledger
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

# GPT-4o-mini pricing (per 1K tokens, USD)
COST_PER_1K_INPUT = 0.000150
COST_PER_1K_OUTPUT = 0.000600


@dataclass
class AgentTrace:
    agent: str
    prompt: str
    response: str
    input_tokens: int
    output_tokens: int
    duration_sec: float
    cost_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""


class RunTracer:
    """Tracks all agent calls for a single book-generation run."""

    def __init__(self, run_id: str, traces_dir: str = "output/traces"):
        self.run_id = run_id
        self.traces: list[AgentTrace] = []
        self.traces_dir = traces_dir
        os.makedirs(traces_dir, exist_ok=True)
        self.start_time = time.time()

    def record(self, agent: str, prompt: str, response: str,
               input_tokens: int, output_tokens: int, duration: float, notes: str = ""):
        cost = (input_tokens / 1000 * COST_PER_1K_INPUT) + (output_tokens / 1000 * COST_PER_1K_OUTPUT)
        trace = AgentTrace(
            agent=agent,
            prompt=prompt[:500] + ("..." if len(prompt) > 500 else ""),
            response=response[:500] + ("..." if len(response) > 500 else ""),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_sec=round(duration, 2),
            cost_usd=round(cost, 6),
            notes=notes
        )
        self.traces.append(trace)
        console.print(f"  [dim]▸ {agent}[/dim] [green]{input_tokens}in/{output_tokens}out tokens[/green] [yellow]${cost:.4f}[/yellow]")

    def total_tokens(self):
        return sum(t.input_tokens + t.output_tokens for t in self.traces)

    def total_cost(self):
        return sum(t.cost_usd for t in self.traces)

    def save(self):
        path = os.path.join(self.traces_dir, f"{self.run_id}_trace.json")
        data = {
            "run_id": self.run_id,
            "total_tokens": self.total_tokens(),
            "total_cost_usd": round(self.total_cost(), 4),
            "total_duration_sec": round(time.time() - self.start_time, 2),
            "agents": [asdict(t) for t in self.traces]
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

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
