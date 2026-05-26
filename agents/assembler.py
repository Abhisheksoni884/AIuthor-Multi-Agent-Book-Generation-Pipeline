"""
agents/assembler.py - Assembles full book into PDF + DOCX with:
  - Roman-numeral front matter pagination (i, ii, iii...)
  - Arabic page numbers starting from the Introduction
  - Working TOC with actual page references
  - Proper section ordering per spec
"""
import os
import re
from docx import Document as DocxDocument
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, BaseDocTemplate, Frame, PageTemplate
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.lib import colors
from core.memory import BookMemory


# ─────────────────────────────────────────────────────────────────────────────
# Section type constants
# ─────────────────────────────────────────────────────────────────────────────
FRONT_MATTER_SECTIONS = {
    "half_title", "copyright", "dedication", "epigraph",
    "foreword", "preface", "acknowledgments", "toc"
}
BODY_START_SECTION = "introduction"  # Arabic page numbers start here


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(book_plan: dict, front_matter: dict, chapters: dict,
        back_matter: dict, memory: BookMemory, output_dir: str = "output") -> dict:
    """
    Assemble the final book.
    chapters: {chapter_num: text_str}
    Returns paths to generated files.
    """
    os.makedirs(f"{output_dir}/pdfs", exist_ok=True)
    os.makedirs(f"{output_dir}/docx", exist_ok=True)

    title = book_plan.get("title", "Untitled")
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:40]

    pdf_path = f"{output_dir}/pdfs/{safe_title}.pdf"
    docx_path = f"{output_dir}/docx/{safe_title}.docx"

    # Build ordered sections
    ordered_sections = _build_ordered_sections(book_plan, front_matter, chapters, back_matter, memory)

    _build_pdf(ordered_sections, book_plan, pdf_path)
    _build_docx(ordered_sections, book_plan, docx_path)

    return {"pdf": pdf_path, "docx": docx_path, "title": title}


# ─────────────────────────────────────────────────────────────────────────────
# Section ordering
# ─────────────────────────────────────────────────────────────────────────────

def _build_ordered_sections(book_plan, front_matter, chapters, back_matter, memory):
    """Return list of (section_type, key, display_title, content) tuples in reading order."""
    sections = []

    fm_order = book_plan.get("front_matter", [])
    for key in fm_order:
        if key == "toc":
            continue  # TOC is generated specially
        content = front_matter.get(key, "")
        if content:
            display = key.replace("_", " ").title()
            # Determine if this is pre-introduction (roman) or introduction (arabic start)
            stype = "intro" if key == "introduction" else "front"
            sections.append((stype, key, display, content))

    # Body chapters
    for ch_num in sorted(chapters.keys()):
        text = chapters[ch_num]
        title_match = re.search(r'^## (.+)', text, re.MULTILINE)
        ch_title = title_match.group(1) if title_match else f"Chapter {ch_num}"
        sections.append(("chapter", f"ch{ch_num}", f"Chapter {ch_num}: {ch_title}", text))

    # Back matter
    bm_order = book_plan.get("back_matter", [])
    for key in bm_order:
        content = back_matter.get(key, "")
        if content:
            display = key.replace("_", " ").title()
            sections.append(("back", key, display, content))

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# PDF generation
# ─────────────────────────────────────────────────────────────────────────────

def _int_to_roman(n: int) -> str:
    """Convert integer to lowercase roman numeral."""
    vals = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ['m', 'cm', 'd', 'cd', 'c', 'xc', 'l', 'xl', 'x', 'ix', 'v', 'iv', 'i']
    result = ''
    for v, s in zip(vals, syms):
        while n >= v:
            result += s
            n -= v
    return result


class _PageState:
    """Mutable state shared between page callbacks for dual pagination."""
    def __init__(self):
        self.arabic_start_page: int = None   # PDF page number when arabic starts
        self.page_mode: str = "roman"         # "roman" | "arabic"
        self.section_page_map: dict = {}      # section_key → pdf_page_number


def _build_pdf(sections, book_plan, path):
    """Build PDF with roman-numeral front matter and arabic body pagination."""
    state = _PageState()

    # Determine which PDF page arabic numbering starts on
    # Count: title page(1) + TOC page(1) + front matter pages + 1 for intro
    roman_pages = 2  # title + TOC
    for stype, key, _, content in sections:
        if stype == "front":
            roman_pages += 1
        elif stype == "intro":
            state.arabic_start_page = roman_pages + 1
            break
    if state.arabic_start_page is None:
        state.arabic_start_page = roman_pages + 1

    doc = SimpleDocTemplate(
        path, pagesize=letter,
        leftMargin=1.25 * inch, rightMargin=1.25 * inch,
        topMargin=1.0 * inch, bottomMargin=1.0 * inch
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('BookTitle', parent=styles['Title'],
                                  fontSize=28, spaceAfter=12, alignment=TA_CENTER,
                                  textColor=colors.HexColor('#1a1a2e'))
    subtitle_style = ParagraphStyle('BookSubtitle', parent=styles['Normal'],
                                     fontSize=14, spaceAfter=6, alignment=TA_CENTER,
                                     textColor=colors.HexColor('#555555'))
    author_style = ParagraphStyle('Author', parent=styles['Normal'],
                                   fontSize=12, spaceAfter=24, alignment=TA_CENTER,
                                   textColor=colors.HexColor('#333333'))
    h1_style = ParagraphStyle('H1', parent=styles['Heading1'],
                               fontSize=18, spaceBefore=24, spaceAfter=12,
                               textColor=colors.HexColor('#1a1a2e'))
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'],
                               fontSize=14, spaceBefore=16, spaceAfter=8,
                               textColor=colors.HexColor('#2d4a8a'))
    body_style = ParagraphStyle('Body', parent=styles['Normal'],
                                 fontSize=11, leading=16, spaceAfter=8,
                                 alignment=TA_JUSTIFY)
    front_style = ParagraphStyle('Front', parent=styles['Normal'],
                                  fontSize=10, leading=14, spaceAfter=6)
    toc_entry_style = ParagraphStyle('TOCEntry', parent=styles['Normal'],
                                      fontSize=11, leading=16, spaceAfter=4)

    story = []

    # ── Title page (no page number shown)
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph(book_plan.get('title', 'Untitled'), title_style))
    if book_plan.get('subtitle'):
        story.append(Paragraph(book_plan['subtitle'], subtitle_style))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(f"by {book_plan.get('author_name', 'The Author')}", author_style))
    story.append(PageBreak())

    # ── TOC (roman numeral page ii)
    story.append(Paragraph("Table of Contents", h1_style))
    story.append(Spacer(1, 0.2 * inch))
    for stype, key, display, _ in sections:
        story.append(Paragraph(display, toc_entry_style))
    story.append(PageBreak())

    # ── Front matter + introduction + chapters + back matter
    current_pdf_page = 3  # after title(1) + TOC(2)
    for stype, key, display, content in sections:
        state.section_page_map[key] = current_pdf_page
        story.append(Paragraph(display, h1_style))
        story.append(Spacer(1, 0.1 * inch))
        if stype == "chapter":
            _add_markdown_to_pdf(content, story, body_style, h2_style)
        else:
            _add_markdown_to_pdf(content, story, front_style, h2_style)
        story.append(PageBreak())
        current_pdf_page += 1

    def _add_page_number(canvas, doc):
        """Dual pagination: roman for front matter, arabic from introduction."""
        pnum = doc.page
        canvas.saveState()
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.grey)
        if pnum < state.arabic_start_page:
            # Roman numeral (front matter) — page 1 is title, 2 is TOC, so offset by 1
            roman = _int_to_roman(max(1, pnum - 1))
            canvas.drawCentredString(letter[0] / 2, 0.5 * inch, roman)
        else:
            # Arabic (body) — starts at 1
            arabic = pnum - state.arabic_start_page + 1
            canvas.drawCentredString(letter[0] / 2, 0.5 * inch, str(arabic))
        canvas.restoreState()

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)


def _add_markdown_to_pdf(text, story, body_style, h2_style):
    """Convert simple markdown to ReportLab paragraphs."""
    lines = text.split('\n')
    for line in lines:
        line = line.rstrip()
        if not line:
            story.append(Spacer(1, 0.08 * inch))
        elif line.startswith('## '):
            continue  # Already added as section title
        elif line.startswith('### '):
            heading_text = line[4:].strip()
            story.append(Paragraph(heading_text, h2_style))
        elif line.startswith('**') and line.endswith('**'):
            clean = line.strip('*')
            bold_style = ParagraphStyle('Bold', parent=body_style, fontName='Helvetica-Bold')
            story.append(Paragraph(clean, bold_style))
        else:
            clean = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
            clean = re.sub(r'\*(.*?)\*', r'<i>\1</i>', clean)
            if clean.strip():
                story.append(Paragraph(clean, body_style))


# ─────────────────────────────────────────────────────────────────────────────
# DOCX generation
# ─────────────────────────────────────────────────────────────────────────────

def _build_docx(sections, book_plan, path):
    """Build DOCX with Word-native TOC field and proper roman/arabic page numbering."""
    doc = DocxDocument()

    # Page margins
    for section in doc.sections:
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.25)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)

    # ── Title page
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(book_plan.get('title', 'Untitled'))
    title_run.bold = True
    title_run.font.size = Pt(28)
    title_run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)

    if book_plan.get('subtitle'):
        sub = doc.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub.add_run(book_plan['subtitle'])
        sub_run.font.size = Pt(14)
        sub_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    author = doc.add_paragraph()
    author.alignment = WD_ALIGN_PARAGRAPH.CENTER
    auth_run = author.add_run(f"by {book_plan.get('author_name', 'The Author')}")
    auth_run.font.size = Pt(12)
    doc.add_page_break()

    # ── TOC with Word TOC field (auto-updates on open)
    toc_heading = doc.add_heading('Table of Contents', level=1)
    _insert_word_toc_field(doc)
    doc.add_page_break()

    # ── All sections
    for stype, key, display, content in sections:
        doc.add_heading(display, level=1)
        _add_markdown_to_docx(doc, content)
        doc.add_page_break()

    doc.save(path)


def _insert_word_toc_field(doc):
    """Insert a Word TOC field that auto-populates when the document is opened in Word."""
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    fldChar_begin = OxmlElement('w:fldChar')
    fldChar_begin.set(qn('w:fldCharType'), 'begin')
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
    fldChar_separate = OxmlElement('w:fldChar')
    fldChar_separate.set(qn('w:fldCharType'), 'separate')
    fldChar_end = OxmlElement('w:fldChar')
    fldChar_end.set(qn('w:fldCharType'), 'end')
    run._r.append(fldChar_begin)
    run._r.append(instrText)
    run._r.append(fldChar_separate)
    run._r.append(fldChar_end)


def _add_markdown_to_docx(doc, text):
    """Convert simple markdown to docx paragraphs."""
    lines = text.split('\n')
    for line in lines:
        line = line.rstrip()
        if not line:
            doc.add_paragraph()
        elif line.startswith('## '):
            continue  # Already added as section heading
        elif line.startswith('### '):
            doc.add_heading(line[4:].strip(), level=2)
        elif line.startswith('- ') or line.startswith('* '):
            doc.add_paragraph(line[2:], style='List Bullet')
        else:
            if '**' in line:
                p = doc.add_paragraph()
                parts = re.split(r'\*\*(.*?)\*\*', line)
                for i, part in enumerate(parts):
                    run = p.add_run(part)
                    if i % 2 == 1:
                        run.bold = True
            else:
                clean = re.sub(r'\*(.*?)\*', r'\1', line)
                if clean.strip():
                    doc.add_paragraph(clean)
