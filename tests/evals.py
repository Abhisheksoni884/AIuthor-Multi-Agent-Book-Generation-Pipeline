"""
tests/evals.py - Automated evaluation checks with scores

Run: python tests/evals.py --output output/
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
import json
import argparse
from rich.console import Console
from rich.table import Table

console = Console()

# ---- Eval checks ----

def check_no_banned_phrases(text: str) -> tuple[float, list[str]]:
    """Score: 1.0 if zero banned phrases, else deduct per phrase."""
    from agents.humanizer import check_banned
    found = check_banned(text)
    score = max(0.0, 1.0 - (len(found) * 0.1))
    return round(score, 2), found


def check_word_count(text: str, target: int = 2000, tolerance: float = 0.3) -> tuple[float, str]:
    """Score: 1.0 if within ±30% of target."""
    words = len(text.split())
    low = target * (1 - tolerance)
    high = target * (1 + tolerance)
    score = 1.0 if low <= words <= high else max(0.0, 1.0 - abs(words - target) / target)
    return round(score, 2), f"{words} words (target {target})"


def check_has_structure(text: str) -> tuple[float, str]:
    """Score: 1.0 if chapter has heading + 2+ subheadings + body paragraphs."""
    has_h1 = bool(re.search(r'^## ', text, re.MULTILINE))
    subheadings = len(re.findall(r'^### ', text, re.MULTILINE))
    paragraphs = len([p for p in text.split('\n\n') if len(p.strip()) > 50])
    score = 0.0
    notes = []
    if has_h1:
        score += 0.33
        notes.append("has H1")
    if subheadings >= 2:
        score += 0.33
        notes.append(f"{subheadings} subheadings")
    if paragraphs >= 3:
        score += 0.34
        notes.append(f"{paragraphs} paragraphs")
    return round(score, 2), ", ".join(notes)


def check_no_repetition(text: str) -> tuple[float, str]:
    """Rough check: same sentence shouldn't appear twice."""
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 40]
    if not sentences:
        return 1.0, "OK"
    seen = set()
    dupes = []
    for s in sentences:
        norm = re.sub(r'\s+', ' ', s.lower())
        if norm in seen:
            dupes.append(s[:60])
        seen.add(norm)
    score = max(0.0, 1.0 - len(dupes) * 0.15)
    return round(score, 2), f"{len(dupes)} duplicates found"


def check_tone_consistency(text: str, tone: str) -> tuple[float, str]:
    """Heuristic tone checks."""
    tone_signals = {
        "conversational": ["you", "your", "we", "let's", "'re", "'ve", "'ll"],
        "academic": ["therefore", "whereas", "analysis", "evidence", "study", "research"],
        "storyteller": ["she", "he", "they", "suddenly", "looked", "felt", "heard"],
        "motivational": ["you can", "start", "now", "action", "step", "commit", "decide"],
        "witty": ["actually", "turns out", "ironically", "funny enough", "—"]
    }
    signals = tone_signals.get(tone, [])
    text_lower = text.lower()
    found = sum(1 for s in signals if s in text_lower)
    score = min(1.0, found / max(len(signals) * 0.5, 1))
    return round(score, 2), f"{found}/{len(signals)} tone signals found"


def check_files_exist(output_dir: str) -> list[tuple[str, bool]]:
    """Check required output files exist."""
    checks = []
    for subdir in ["pdfs", "docx", "traces"]:
        path = os.path.join(output_dir, subdir)
        checks.append((f"{subdir}/ directory", os.path.isdir(path)))
    return checks


# ---- Runner ----

def run_evals(output_dir: str = "output", run_id: str = None):
    """Run all evals against generated output."""
    results = []

    # Find trace files
    traces_dir = os.path.join(output_dir, "traces")
    if not os.path.isdir(traces_dir):
        console.print("[red]No traces directory found. Run the pipeline first.[/red]")
        return

    # Find result files
    result_files = [f for f in os.listdir(traces_dir) if f.endswith("_result.json")]
    if not result_files:
        console.print("[yellow]No result files found yet. Run pipeline first (or use demo mode).[/yellow]")
        # Demo: create fake passing scores
        result_files = []

    all_scores = []

    for rf in result_files:
        run_name = rf.replace("_result.json", "")
        path = os.path.join(traces_dir, rf)
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue

        chapters = data.get("chapters", {})
        book_plan = data.get("book_plan", {})
        tone = book_plan.get("tone", "conversational")

        for ch_num_str, ch_text in chapters.items():
            ch_num = int(ch_num_str)
            row = {"run": run_name, "chapter": ch_num}

            s1, d1 = check_no_banned_phrases(ch_text)
            row["no_banned"] = s1

            s2, d2 = check_word_count(ch_text, 2000)
            row["word_count"] = s2

            s3, d3 = check_has_structure(ch_text)
            row["structure"] = s3

            s4, d4 = check_no_repetition(ch_text)
            row["no_repeat"] = s4

            s5, d5 = check_tone_consistency(ch_text, tone)
            row["tone_consistency"] = s5

            row["avg"] = round(sum([s1, s2, s3, s4, s5]) / 5, 2)
            row["details"] = f"banned:{d1} | {d2} | {d3} | {d4} | {d5}"
            results.append(row)
            all_scores.append(row["avg"])

    # Print table
    table = Table(title="Eval Report", show_lines=True)
    table.add_column("Run", style="cyan")
    table.add_column("Ch", justify="right")
    table.add_column("No Banned", justify="right")
    table.add_column("Word Count", justify="right")
    table.add_column("Structure", justify="right")
    table.add_column("No Repeat", justify="right")
    table.add_column("Tone", justify="right")
    table.add_column("AVG", justify="right", style="bold green")

    for r in results:
        table.add_row(
            r["run"], str(r["chapter"]),
            _score_str(r["no_banned"]),
            _score_str(r["word_count"]),
            _score_str(r["structure"]),
            _score_str(r["no_repeat"]),
            _score_str(r["tone_consistency"]),
            _score_str(r["avg"])
        )

    if results:
        overall = sum(all_scores) / len(all_scores)
        table.add_row(
            "[bold]OVERALL[/bold]", "", "", "", "", "", "",
            f"[bold]{overall:.2f}[/bold]"
        )

    console.print(table)

    # File existence checks
    console.print("\n[bold]File Checks:[/bold]")
    for label, exists in check_files_exist(output_dir):
        icon = "[green]✓[/green]" if exists else "[red]✗[/red]"
        console.print(f"  {icon} {label}")

    # Save report
    report_path = os.path.join(traces_dir, "eval_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    console.print(f"\n[dim]Report saved: {report_path}[/dim]")

    return results


def _score_str(score: float) -> str:
    color = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "red"
    return f"[{color}]{score:.2f}[/{color}]"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="output")
    parser.add_argument("--run", default=None)
    args = parser.parse_args()
    run_evals(args.output, args.run)
