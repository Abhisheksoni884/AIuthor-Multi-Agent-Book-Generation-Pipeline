"""
pipeline.py - Main orchestrator: runs all 8 agents in sequence
"""
import os
import json
import time
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.config import TONES
from core.memory import BookMemory
from core.rag import BookRAG
from core.tracer import RunTracer
from core.rlhf import judge_chapter, score_tonality, generate_preference_pair, save_preference_pairs
from core.schemas import PreferencePair

from agents import planner, researcher, writer, humanizer, editor, fact_checker, memory_keeper, assembler

console = Console()


def generate_book(
    brief: str,
    tone: str = "conversational",
    num_chapters: int = 5,
    target_words_per_chapter: int = 2000,
    output_dir: str = "output",
    run_id: str = None
) -> dict:
    """
    Full pipeline: brief → publication-ready book (PDF + DOCX).
    Returns dict with output file paths and metadata.
    """
    if tone not in TONES:
        raise ValueError(f"Unknown tone '{tone}'. Choose from: {list(TONES.keys())}")

    run_id = run_id or f"book_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    console.print(Panel(f"[bold blue]Book Factory[/bold blue]\nRun: {run_id}\nTone: {TONES[tone]['name']}\nChapters: {num_chapters}", expand=False))

    tracer = RunTracer(run_id=run_id, traces_dir=f"{output_dir}/traces")
    memory = BookMemory()
    rag = BookRAG()

    # Build RAG index
    console.print("\n[bold]▸ Building RAG index...[/bold]")
    rag.build()

    # ─────────────────────────────────────────
    # AGENT 1: PLANNER
    # ─────────────────────────────────────────
    console.print("\n[bold cyan]▸ Agent 1: Planner[/bold cyan]")
    book_plan = planner.run(brief=brief, tone=tone, num_chapters=num_chapters,
                             memory=memory, tracer=tracer)
    console.print(f"  Title: [bold]{book_plan.get('title')}[/bold]")
    console.print(f"  Chapters planned: {len(book_plan.get('chapters', []))}")

    # ─────────────────────────────────────────
    # CHAPTER LOOP: Research → Write → Humanize → Edit → Fact-check → Memory
    # ─────────────────────────────────────────
    chapters_text = {}
    fact_check_reports = []
    judge_scores = []
    preference_pairs: list[PreferencePair] = []

    for ch_plan in book_plan.get("chapters", []):
        ch_num = ch_plan["num"]
        console.print(f"\n[bold green]▸ Chapter {ch_num}: {ch_plan['title']}[/bold green]")

        # AGENT 2: RESEARCHER
        console.print("  [dim]Agent 2: Researcher[/dim]")
        research = researcher.run(chapter_plan=ch_plan, book_plan=book_plan,
                                   rag=rag, memory=memory, tracer=tracer)

        # AGENT 3: WRITER
        console.print("  [dim]Agent 3: Writer[/dim]")
        raw_text = writer.run(chapter_plan=ch_plan, research=research, book_plan=book_plan,
                               tone=tone, memory=memory, target_words=target_words_per_chapter,
                               tracer=tracer)

        # AGENT 4: HUMANIZER
        console.print("  [dim]Agent 4: Humanizer[/dim]")
        human_text = humanizer.run(text=raw_text, chapter_num=ch_num, tracer=tracer)

        # AGENT 5: EDITOR
        console.print("  [dim]Agent 5: Editor[/dim]")
        edited_text = editor.run(text=human_text, tone=tone, chapter_num=ch_num,
                                  chapter_title=ch_plan["title"], tracer=tracer)

        # AGENT 6: FACT CHECKER
        console.print("  [dim]Agent 6: Fact Checker[/dim]")
        fc_report = fact_checker.run(text=edited_text, chapter_num=ch_num,
                                      memory=memory, rag=rag, tracer=tracer)
        fact_check_reports.append(fc_report)

        # AGENT 7: MEMORY KEEPER
        console.print("  [dim]Agent 7: Memory Keeper[/dim]")
        _ = memory_keeper.run(text=edited_text, chapter_num=ch_num,
                               memory=memory, tracer=tracer)  # updates memory + tone fingerprint

        # RLHF: Preference pair (raw vs. humanized) + LLM-as-judge score
        console.print("  [dim]RLHF: Preference pair + judge score[/dim]")
        try:
            pair = generate_preference_pair(
                chapter_num=ch_num, tone=tone,
                opening_a=raw_text[:600],
                opening_b=human_text[:600],
                tracer=tracer
            )
            preference_pairs.append(pair)
        except Exception:
            pass

        try:
            j_score = judge_chapter(edited_text, tone, ch_num, tracer=tracer)
            judge_scores.append({"chapter": ch_num, **j_score.__dict__})
        except Exception:
            pass

        chapters_text[ch_num] = edited_text

    # ─────────────────────────────────────────
    # FRONT MATTER
    # ─────────────────────────────────────────
    console.print("\n[bold cyan]▸ Writing front matter...[/bold cyan]")
    front_matter = {}
    for section in book_plan.get("front_matter", []):
        if section != "toc":
            front_matter[section] = writer.write_front_matter(section, book_plan, tone, tracer=tracer)

    # ─────────────────────────────────────────
    # BACK MATTER
    # ─────────────────────────────────────────
    console.print("[bold cyan]▸ Writing back matter...[/bold cyan]")
    back_matter = {}
    for section in book_plan.get("back_matter", []):
        back_matter[section] = writer.write_back_matter(section, book_plan, memory, tone, tracer=tracer)

    # ─────────────────────────────────────────
    # AGENT 8: ASSEMBLER
    # ─────────────────────────────────────────
    console.print("\n[bold cyan]▸ Agent 8: Assembler[/bold cyan]")
    result = assembler.run(
        book_plan=book_plan,
        front_matter=front_matter,
        chapters=chapters_text,
        back_matter=back_matter,
        memory=memory,
        output_dir=output_dir
    )

    # Save memory snapshot
    memory_path = f"{output_dir}/traces/{run_id}_memory.json"
    memory.save(memory_path)

    # Save full data for test C/D reuse
    full_result_path = f"{output_dir}/traces/{run_id}_result.json"
    with open(full_result_path, "w") as f:
        json.dump({
            "book_plan": book_plan,
            "chapters": {str(k): v for k, v in chapters_text.items()}
        }, f, indent=2)

    # Save trace + memory I/O log
    trace_path = tracer.save()
    tracer.print_summary()

    # Save fact-check reports
    fc_path = f"{output_dir}/traces/{run_id}_factcheck.json"
    with open(fc_path, "w") as f:
        json.dump(fact_check_reports, f, indent=2)

    # Save RLHF judge scores
    judge_path = f"{output_dir}/traces/{run_id}_judge_scores.json"
    with open(judge_path, "w") as f:
        json.dump(judge_scores, f, indent=2)

    # Save preference pairs (JSONL for DPO training)
    pref_path = f"{output_dir}/traces/{run_id}_preference_pairs.jsonl"
    save_preference_pairs(preference_pairs, pref_path)

    # Save design decision log
    decision_log_path = f"{output_dir}/traces/{run_id}_decisions.json"
    with open(decision_log_path, "w") as f:
        json.dump(memory.decision_log, f, indent=2)

    console.print(f"\n[bold green]✓ Book generated![/bold green]")
    console.print(f"  PDF:  {result['pdf']}")
    console.print(f"  DOCX: {result['docx']}")

    return {
        "run_id": run_id,
        "title": result["title"],
        "pdf": result["pdf"],
        "docx": result["docx"],
        "trace": trace_path,
        "memory": memory_path,
        "fact_checks": fc_path,
        "judge_scores": judge_path,
        "preference_pairs": pref_path,
        "decision_log": decision_log_path,
        "chapters": len(chapters_text),
        "total_tokens": tracer.total_tokens(),
        "total_cost_usd": tracer.total_cost()
    }


def regenerate_chapter(
    existing_memory_path: str,
    existing_chapters: dict,
    book_plan: dict,
    chapter_num: int,
    new_tone: str,
    output_dir: str = "output",
    run_id: str = None
) -> str:
    """
    Regenerate a single chapter in a new tone, using existing memory.
    Returns the new chapter text.
    """
    run_id = run_id or f"regen_ch{chapter_num}_{datetime.now().strftime('%H%M%S')}"
    tracer = RunTracer(run_id=run_id, traces_dir=f"{output_dir}/traces")
    memory = BookMemory.load(existing_memory_path)
    rag = BookRAG()
    rag.build()

    # Find the chapter plan
    ch_plan = next((c for c in book_plan.get("chapters", []) if c["num"] == chapter_num), None)
    if not ch_plan:
        raise ValueError(f"Chapter {chapter_num} not found in plan")

    console.print(f"\n[bold yellow]▸ Regenerating Chapter {chapter_num} in {TONES[new_tone]['name']} tone[/bold yellow]")

    research = researcher.run(ch_plan, book_plan, rag, memory, tracer)
    raw = writer.run(ch_plan, research, book_plan, new_tone, memory, tracer=tracer)
    human = humanizer.run(raw, chapter_num, tracer)
    final = editor.run(human, new_tone, chapter_num, ch_plan["title"], tracer)

    tracer.save()
    return final


def insert_chapter(
    existing_memory_path: str,
    chapters_text: dict,
    book_plan: dict,
    insert_after: int,
    new_chapter_brief: str,
    tone: str,
    output_dir: str = "output"
) -> tuple[dict, dict]:
    """
    Insert a new chapter after `insert_after`, then self-heal TOC + callbacks.
    Returns (updated_chapters_dict, updated_book_plan).
    """
    run_id = f"insert_ch_{datetime.now().strftime('%H%M%S')}"
    tracer = RunTracer(run_id=run_id, traces_dir=f"{output_dir}/traces")
    memory = BookMemory.load(existing_memory_path)
    rag = BookRAG()
    rag.build()

    insert_at = insert_after + 1

    # Shift existing chapters
    new_chapters = {}
    for num, text in chapters_text.items():
        new_num = num + 1 if num >= insert_at else num
        new_chapters[new_num] = text

    # Shift book plan chapters
    for ch in book_plan["chapters"]:
        if ch["num"] >= insert_at:
            ch["num"] += 1

    # Create new chapter plan
    new_ch_plan = {
        "num": insert_at,
        "title": new_chapter_brief[:60],
        "summary": new_chapter_brief,
        "key_points": [new_chapter_brief]
    }
    book_plan["chapters"].insert(insert_at - 1, new_ch_plan)

    console.print(f"\n[bold yellow]▸ Inserting new chapter at position {insert_at}[/bold yellow]")

    research = researcher.run(new_ch_plan, book_plan, rag, memory, tracer)
    raw = writer.run(new_ch_plan, research, book_plan, tone, memory, tracer=tracer)
    human = humanizer.run(raw, insert_at, tracer)
    final = editor.run(human, tone, insert_at, new_ch_plan["title"], tracer)

    new_chapters[insert_at] = final

    # Repair adjacent chapters
    console.print("  [dim]Repairing cross-references...[/dim]")
    repaired = memory_keeper.repair_for_insert(new_chapters, insert_at, memory, tracer)
    new_chapters.update(repaired)

    # Update TOC in memory
    toc = [{"num": ch["num"], "title": ch["title"], "page_est": 0} for ch in book_plan["chapters"]]
    memory.set_toc(toc)
    memory.save(existing_memory_path)
    tracer.save()

    return new_chapters, book_plan
