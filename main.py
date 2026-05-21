#!/usr/bin/env python3
"""
main.py - One-command entry point for Book Factory

Usage:
  python main.py                          # Interactive mode
  python main.py --test A                 # Run test case A
  python main.py --test B
  python main.py --test C
  python main.py --test D
  python main.py --brief "My book" --tone conversational --chapters 5
"""
import argparse
import json
import os
import sys
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.panel import Panel
from dotenv import load_dotenv

load_dotenv()
console = Console()

# Test cases
TEST_CASES = {
    "A": {
        "brief": "A practical personal finance guide that helps everyday people understand budgeting, saving, investing, debt management, and building long-term wealth. Include real strategies anyone can implement starting this week.",
        "tone": "conversational",
        "num_chapters": 10,
        "target_words": 2500,
        "name": "Test A: Personal Finance Guide"
    },
    "B": {
        "brief": "A coming-of-age novella about two friends, Maya and Daniel, navigating a small coastal town after a mysterious lighthouse goes dark. Themes of friendship, courage, and hidden family secrets. Maya is fearless and curious; Daniel is careful and methodical.",
        "tone": "storyteller",
        "num_chapters": 5,
        "target_words": 2000,
        "name": "Test B: Coastal Mystery Novella"
    }
}


def main():
    parser = argparse.ArgumentParser(description="Book Factory - AI Multi-Agent Book Generator")
    parser.add_argument("--test", choices=["A", "B", "C", "D"], help="Run a test case")
    parser.add_argument("--brief", type=str, help="Book brief")
    parser.add_argument("--tone", choices=["conversational", "academic", "storyteller", "motivational", "witty"],
                        default="conversational")
    parser.add_argument("--chapters", type=int, default=5)
    parser.add_argument("--words", type=int, default=2000)
    parser.add_argument("--output", type=str, default="output")
    args = parser.parse_args()

    # Create output dirs
    for d in ["output/pdfs", "output/docx", "output/traces"]:
        os.makedirs(d, exist_ok=True)

    from pipeline import generate_book, regenerate_chapter, insert_chapter

    if args.test == "A":
        tc = TEST_CASES["A"]
        console.print(Panel(f"[bold]{tc['name']}[/bold]", expand=False))
        result = generate_book(
            brief=tc["brief"], tone=tc["tone"],
            num_chapters=tc["num_chapters"], target_words_per_chapter=tc["target_words"],
            output_dir=args.output, run_id="test_A"
        )
        _save_result(result, "test_A")

    elif args.test == "B":
        tc = TEST_CASES["B"]
        console.print(Panel(f"[bold]{tc['name']}[/bold]", expand=False))
        result = generate_book(
            brief=tc["brief"], tone=tc["tone"],
            num_chapters=tc["num_chapters"], target_words_per_chapter=tc["target_words"],
            output_dir=args.output, run_id="test_B"
        )
        _save_result(result, "test_B")

    elif args.test == "C":
        _run_test_c(args.output)

    elif args.test == "D":
        _run_test_d(args.output)

    elif args.brief:
        result = generate_book(
            brief=args.brief, tone=args.tone,
            num_chapters=args.chapters, target_words_per_chapter=args.words,
            output_dir=args.output
        )
        _save_result(result, result["run_id"])

    else:
        _interactive_mode(args.output)


def _run_test_c(output_dir):
    """Test C: Regenerate Chapter 3 of Test A in Academic, Motivational, Witty tones."""
    console.print(Panel("[bold]Test C: Multi-tone Chapter Regeneration[/bold]", expand=False))

    memory_path = f"{output_dir}/traces/test_A_memory.json"
    if not os.path.exists(memory_path):
        console.print("[red]Test A memory not found. Run --test A first.[/red]")
        sys.exit(1)

    # Load saved test A data
    result_path = f"{output_dir}/traces/test_A_result.json"
    with open(result_path) as f:
        result_data = json.load(f)

    book_plan = result_data["book_plan"]
    chapters = {int(k): v for k, v in result_data["chapters"].items()}

    from pipeline import regenerate_chapter
    for new_tone in ["academic", "motivational", "witty"]:
        console.print(f"\n[bold]Regenerating Chapter 3 in {new_tone} tone...[/bold]")
        regen_text = regenerate_chapter(
            existing_memory_path=memory_path,
            existing_chapters=chapters,
            book_plan=book_plan,
            chapter_num=3,
            new_tone=new_tone,
            output_dir=output_dir,
            run_id=f"test_C_{new_tone}"
        )
        out_path = f"{output_dir}/traces/test_C_ch3_{new_tone}.txt"
        with open(out_path, "w") as f:
            f.write(regen_text)
        console.print(f"  Saved: {out_path}")


def _run_test_d(output_dir):
    """Test D: Insert chapter between Ch4 and Ch5 of Test A."""
    console.print(Panel("[bold]Test D: Chapter Insertion + Self-Heal[/bold]", expand=False))

    memory_path = f"{output_dir}/traces/test_A_memory.json"
    result_path = f"{output_dir}/traces/test_A_result.json"

    if not os.path.exists(memory_path) or not os.path.exists(result_path):
        console.print("[red]Test A data not found. Run --test A first.[/red]")
        sys.exit(1)

    with open(result_path) as f:
        result_data = json.load(f)

    book_plan = result_data["book_plan"]
    chapters = {int(k): v for k, v in result_data["chapters"].items()}

    from pipeline import insert_chapter, generate_book
    new_chapters, updated_plan = insert_chapter(
        existing_memory_path=memory_path,
        chapters_text=chapters,
        book_plan=book_plan,
        insert_after=4,
        new_chapter_brief="The Psychology of Spending: Why We Buy What We Don't Need and How to Break the Cycle",
        tone="conversational",
        output_dir=output_dir
    )

    # Reassemble
    from agents import assembler
    from core.memory import BookMemory
    memory = BookMemory.load(memory_path)
    result = assembler.run(
        book_plan=updated_plan,
        front_matter={},
        chapters=new_chapters,
        back_matter={},
        memory=memory,
        output_dir=output_dir
    )

    # Save updated plan
    updated_plan_path = f"{output_dir}/traces/test_D_result.json"
    with open(updated_plan_path, "w") as f:
        json.dump({"book_plan": updated_plan, "chapters": {str(k): v for k, v in new_chapters.items()}}, f, indent=2)

    console.print(f"\n[bold green]✓ Test D complete[/bold green]")
    console.print(f"  PDF:  {result['pdf']}")
    console.print(f"  DOCX: {result['docx']}")


def _interactive_mode(output_dir):
    """Interactive book generation."""
    console.print(Panel("[bold blue]Book Factory — Interactive Mode[/bold blue]", expand=False))
    brief = Prompt.ask("\nDescribe your book")
    tone = Prompt.ask("Tone", choices=["conversational", "academic", "storyteller", "motivational", "witty"],
                       default="conversational")
    num_chapters = IntPrompt.ask("Number of chapters", default=5)
    words = IntPrompt.ask("Words per chapter", default=2000)

    from pipeline import generate_book
    result = generate_book(
        brief=brief, tone=tone,
        num_chapters=num_chapters, target_words_per_chapter=words,
        output_dir=output_dir
    )
    _save_result(result, result["run_id"])


def _save_result(result: dict, run_id: str):
    """Save result metadata for later test cases to reference."""
    # We need to also save chapters text and book plan for C/D tests
    # These are saved separately during the pipeline — here we just confirm
    path = f"output/traces/{run_id}_result_summary.json"
    with open(path, "w") as f:
        json.dump({k: v for k, v in result.items() if not k.startswith("_")}, f, indent=2)
    console.print(f"\n[dim]Result summary saved: {path}[/dim]")


if __name__ == "__main__":
    main()
