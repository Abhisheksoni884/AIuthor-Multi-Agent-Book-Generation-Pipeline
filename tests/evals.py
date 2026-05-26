"""
tests/evals.py - Automated evaluation suite with rubric, LLM-judge scoring, and failure analysis.

Run:
  python tests/evals.py --output output/
  python tests/evals.py --output output/ --judge   # include LLM-as-judge (costs tokens)

Dimensions evaluated:
  1. no_banned_phrases      - AI-tell detection
  2. word_count             - structural completeness
  3. structure              - hook, sections, summary, takeaway
  4. no_repetition          - uniqueness of sentences
  5. tone_consistency       - heuristic keyword signals
  6. fact_coverage          - fraction of registered facts mentioned
  7. callback_recall        - fraction of available callbacks used
  8. llm_judge_overall      - LLM-as-judge rubric (optional, costs tokens)

Failure analysis is appended to the report for any chapter scoring below 0.7 overall.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
import json
import argparse
from rich.console import Console
from rich.table import Table

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Eval checks
# ─────────────────────────────────────────────────────────────────────────────

def check_no_banned_phrases(text: str) -> tuple[float, list[str]]:
    """Score: 1.0 if zero banned phrases, deduct 0.1 per phrase found."""
    from agents.humanizer import check_banned
    found = check_banned(text)
    score = max(0.0, 1.0 - (len(found) * 0.1))
    return round(score, 2), found


def check_word_count(text: str, target: int = 2000, tolerance: float = 0.3) -> tuple[float, str]:
    """Score: 1.0 if within ±30% of target word count."""
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
    return round(score, 2), ", ".join(notes) if notes else "missing structure"


def check_no_repetition(text: str) -> tuple[float, str]:
    """Rough check: same sentence should not appear twice."""
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
    return round(score, 2), f"{len(dupes)} duplicate sentences found"


def check_tone_consistency(text: str, tone: str) -> tuple[float, str]:
    """Heuristic: count tone-signal words/phrases present in text."""
    tone_signals = {
        "conversational": ["you", "your", "we", "let's", "'re", "'ve", "'ll", "honestly", "think about"],
        "academic":       ["therefore", "whereas", "analysis", "evidence", "study", "research", "demonstrates", "findings"],
        "storyteller":    ["she", "he", "they", "suddenly", "looked", "felt", "heard", "whispered", "silence"],
        "motivational":   ["you can", "start", "now", "action", "step", "commit", "decide", "you are", "choose"],
        "witty":          ["actually", "turns out", "ironically", "funny enough", "—", "somehow", "apparently"],
    }
    signals = tone_signals.get(tone, [])
    text_lower = text.lower()
    found = sum(1 for s in signals if s in text_lower)
    score = min(1.0, found / max(len(signals) * 0.5, 1))
    return round(score, 2), f"{found}/{len(signals)} tone signals found"


def check_fact_coverage(chapter_text: str, memory_data: dict) -> tuple[float, str]:
    """
    Score: fraction of registered facts (for this chapter) mentioned in the text.
    A fact is 'mentioned' if a key keyword from its value appears in the chapter text.
    """
    facts = memory_data.get("facts", {})
    if not facts:
        return 1.0, "no facts registered (OK for early chapters)"

    text_lower = chapter_text.lower()
    found = 0
    total = 0
    for fact in facts.values():
        # Extract key numbers or nouns from the fact value as check tokens
        tokens = re.findall(r'\b\d[\d,.%]*\b|\b[A-Z][a-z]+\b', fact.get("value", ""))
        if not tokens:
            continue
        total += 1
        if any(t.lower() in text_lower for t in tokens):
            found += 1

    if total == 0:
        return 1.0, "no verifiable fact tokens"
    score = found / total
    return round(score, 2), f"{found}/{total} facts mentioned"


def check_callback_recall(chapter_text: str, chapter_num: int, memory_data: dict) -> tuple[float, str]:
    """
    Score: fraction of available callbacks (from earlier chapters) referenced in this chapter.
    A callback is 'recalled' if a key phrase from it appears in the chapter text.
    """
    callbacks = memory_data.get("callbacks", [])
    available = [c for c in callbacks if c.get("chapter_defined", 999) < chapter_num]
    if not available:
        return 1.0, "no callbacks available yet"

    text_lower = chapter_text.lower()
    recalled = 0
    for cb in available:
        ref = cb.get("reference", "")
        # Check if any 3-word window from the reference appears in the text
        words = ref.lower().split()
        for i in range(len(words) - 2):
            phrase = " ".join(words[i:i+3])
            if len(phrase) > 5 and phrase in text_lower:
                recalled += 1
                break

    score = recalled / len(available)
    return round(score, 2), f"{recalled}/{len(available)} callbacks recalled"


def check_files_exist(output_dir: str) -> list[tuple[str, bool]]:
    """Check required output files exist."""
    checks = []
    for subdir in ["pdfs", "docx", "traces"]:
        path = os.path.join(output_dir, subdir)
        checks.append((f"{subdir}/ directory", os.path.isdir(path)))
    # Check for specific trace file types
    traces_dir = os.path.join(output_dir, "traces")
    if os.path.isdir(traces_dir):
        files = os.listdir(traces_dir)
        checks.append(("_trace.json exists", any("_trace.json" in f for f in files)))
        checks.append(("_memory.json exists", any("_memory.json" in f for f in files)))
        checks.append(("_memory_io.json exists", any("_memory_io.json" in f for f in files)))
        checks.append(("_factcheck.json exists", any("_factcheck.json" in f for f in files)))
        checks.append(("_judge_scores.json exists", any("_judge_scores.json" in f for f in files)))
        checks.append(("_preference_pairs.jsonl exists", any("_preference_pairs.jsonl" in f for f in files)))
        checks.append(("_decisions.json exists", any("_decisions.json" in f for f in files)))
    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_evals(output_dir: str = "output", run_id: str = None, use_llm_judge: bool = False):
    """
    Run all evals against generated output.
    Returns list of per-chapter result dicts.
    """
    results = []
    failure_analysis = []

    # Find trace files
    traces_dir = os.path.join(output_dir, "traces")
    if not os.path.isdir(traces_dir):
        console.print("[red]No traces directory found. Run the pipeline first.[/red]")
        return []

    # Find result files
    result_files = [f for f in os.listdir(traces_dir) if f.endswith("_result.json")]
    if run_id:
        result_files = [f for f in result_files if f.startswith(run_id)]

    if not result_files:
        console.print("[yellow]No result files found yet. Run pipeline first.[/yellow]")
        return []

    all_scores = []

    for rf in result_files:
        run_name = rf.replace("_result.json", "")
        path = os.path.join(traces_dir, rf)

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue

        # Load memory snapshot for fact coverage + callback recall
        memory_path = os.path.join(traces_dir, f"{run_name}_memory.json")
        memory_data = {}
        if os.path.exists(memory_path):
            try:
                with open(memory_path) as f:
                    memory_data = json.load(f)
            except Exception:
                pass

        # Load LLM judge scores if available
        judge_path = os.path.join(traces_dir, f"{run_name}_judge_scores.json")
        judge_scores_by_ch = {}
        if os.path.exists(judge_path):
            try:
                with open(judge_path) as f:
                    for js in json.load(f):
                        judge_scores_by_ch[js["chapter"]] = js
            except Exception:
                pass

        chapters = data.get("chapters", {})
        book_plan = data.get("book_plan", {})
        tone = book_plan.get("tone", "conversational")
        target_words = 2000  # default

        for ch_num_str, ch_text in chapters.items():
            ch_num = int(ch_num_str)
            row = {"run": run_name, "chapter": ch_num}

            s1, d1 = check_no_banned_phrases(ch_text)
            row["no_banned"] = s1

            s2, d2 = check_word_count(ch_text, target_words)
            row["word_count"] = s2

            s3, d3 = check_has_structure(ch_text)
            row["structure"] = s3

            s4, d4 = check_no_repetition(ch_text)
            row["no_repeat"] = s4

            s5, d5 = check_tone_consistency(ch_text, tone)
            row["tone_consistency"] = s5

            s6, d6 = check_fact_coverage(ch_text, memory_data)
            row["fact_coverage"] = s6

            s7, d7 = check_callback_recall(ch_text, ch_num, memory_data)
            row["callback_recall"] = s7

            # LLM judge overall score (from saved scores, or run now if --judge flag)
            llm_overall = None
            if ch_num in judge_scores_by_ch:
                llm_overall = judge_scores_by_ch[ch_num].get("overall", None)
            elif use_llm_judge:
                try:
                    from core.rlhf import judge_chapter
                    j = judge_chapter(ch_text, tone, ch_num)
                    llm_overall = j.overall
                    if ch_num not in judge_scores_by_ch:
                        judge_scores_by_ch[ch_num] = j.__dict__
                except Exception:
                    pass

            row["llm_judge"] = round(llm_overall, 2) if llm_overall is not None else None

            # Compute average (excluding LLM judge if not available)
            core_scores = [s1, s2, s3, s4, s5, s6, s7]
            if llm_overall is not None:
                core_scores.append(llm_overall)
            row["avg"] = round(sum(core_scores) / len(core_scores), 2)

            row["details"] = (
                f"banned:{d1} | {d2} | {d3} | no_repeat:{d4} | tone:{d5} | "
                f"facts:{d6} | callbacks:{d7}"
            )
            results.append(row)
            all_scores.append(row["avg"])

            # Flag for failure analysis
            if row["avg"] < 0.7:
                failure_analysis.append({
                    "run": run_name,
                    "chapter": ch_num,
                    "avg": row["avg"],
                    "low_scores": {
                        k: v for k, v in {
                            "no_banned": s1, "word_count": s2, "structure": s3,
                            "no_repeat": s4, "tone": s5, "fact_coverage": s6,
                            "callback_recall": s7
                        }.items() if v < 0.7
                    },
                    "details": row["details"]
                })

    # ── Print main eval table
    table = Table(title="Eval Report", show_lines=True)
    table.add_column("Run", style="cyan")
    table.add_column("Ch", justify="right")
    table.add_column("No Banned", justify="right")
    table.add_column("Words", justify="right")
    table.add_column("Structure", justify="right")
    table.add_column("No Repeat", justify="right")
    table.add_column("Tone", justify="right")
    table.add_column("Facts", justify="right")
    table.add_column("Callbacks", justify="right")
    table.add_column("LLM Judge", justify="right")
    table.add_column("AVG", justify="right", style="bold green")

    for r in results:
        judge_str = _score_str(r["llm_judge"]) if r["llm_judge"] is not None else "[dim]N/A[/dim]"
        table.add_row(
            r["run"], str(r["chapter"]),
            _score_str(r["no_banned"]),
            _score_str(r["word_count"]),
            _score_str(r["structure"]),
            _score_str(r["no_repeat"]),
            _score_str(r["tone_consistency"]),
            _score_str(r["fact_coverage"]),
            _score_str(r["callback_recall"]),
            judge_str,
            _score_str(r["avg"])
        )

    if results:
        overall = sum(all_scores) / len(all_scores)
        table.add_row(
            "[bold]OVERALL[/bold]", "", "", "", "", "", "", "", "", "",
            f"[bold]{overall:.2f}[/bold]"
        )

    console.print(table)

    # ── Failure analysis
    if failure_analysis:
        console.print("\n[bold red]Failure Analysis (chapters scoring < 0.70):[/bold red]")
        for fa in failure_analysis:
            console.print(f"  [yellow]Run {fa['run']} Ch{fa['chapter']}[/yellow] (avg={fa['avg']:.2f})")
            for dim, score in fa["low_scores"].items():
                console.print(f"    ✗ {dim}: {score:.2f} — {_failure_hint(dim)}")
    else:
        console.print("\n[bold green]✓ No chapters below 0.70 threshold.[/bold green]")

    # ── File existence checks
    console.print("\n[bold]File Checks:[/bold]")
    for label, exists in check_files_exist(output_dir):
        icon = "[green]✓[/green]" if exists else "[red]✗[/red]"
        console.print(f"  {icon} {label}")

    # ── Save full report
    report_path = os.path.join(traces_dir, "eval_report.json")
    report = {
        "overall_avg": round(sum(all_scores) / len(all_scores), 2) if all_scores else 0,
        "chapters": results,
        "failure_analysis": failure_analysis,
        "rubric": {
            "no_banned_phrases":   "1.0 = zero banned AI phrases; -0.1 per phrase found",
            "word_count":          "1.0 = within ±30% of target; linear decay outside",
            "structure":           "1.0 = has H1 + 2+ subheadings + 3+ paragraphs",
            "no_repetition":       "1.0 = no duplicate sentences; -0.15 per duplicate",
            "tone_consistency":    "1.0 = all tone-signal words present; heuristic keyword count",
            "fact_coverage":       "1.0 = all registered facts mentioned in chapter",
            "callback_recall":     "1.0 = all prior callbacks referenced",
            "llm_judge_overall":   "0-1 rubric from gpt-4o judge across 6 dimensions",
            "threshold":           "< 0.70 triggers failure analysis"
        }
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    console.print(f"\n[dim]Full report saved: {report_path}[/dim]")

    return results


def _score_str(score: float) -> str:
    if score is None:
        return "[dim]N/A[/dim]"
    color = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "red"
    return f"[{color}]{score:.2f}[/{color}]"


def _failure_hint(dimension: str) -> str:
    hints = {
        "no_banned": "Humanizer may have missed phrases; re-run humanizer or check regex patterns",
        "word_count": "Chapter too short/long; adjust target_words or Writer max_tokens",
        "structure": "Missing H1/subheadings/paragraphs; check Writer prompt structure requirements",
        "no_repeat": "Repeated sentences found; Editor should cut repetition",
        "tone": "Tone signals low; check tone parameter and Writer tone guidance",
        "fact_coverage": "Facts not mentioned in chapter; Researcher may not have retrieved relevant facts",
        "callback_recall": "Callbacks not used; Writer should reference prior chapters explicitly",
    }
    return hints.get(dimension, "Review agent output for this dimension")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Book Factory Evaluation Suite")
    parser.add_argument("--output", default="output")
    parser.add_argument("--run", default=None, help="Specific run ID to evaluate")
    parser.add_argument("--judge", action="store_true", help="Run LLM-as-judge (costs tokens)")
    args = parser.parse_args()
    run_evals(args.output, args.run, use_llm_judge=args.judge)
