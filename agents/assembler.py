"""
agents/assembler.py - Assembles full book into PDF + DOCX with TOC and page numbering
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib import colors
from core.memory import BookMemory


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


def _build_ordered_sections(book_plan, front_matter, chapters, back_matter, memory):
    """Return list of (section_type, title, content) tuples in reading order."""
    sections = []

    # Front matter
    fm_order = book_plan.get("front_matter", ["copyright", "toc", "preface"])
    for key in fm_order:
        if key == "toc":
            continue  # TOC handled specially in PDF/DOCX
        content = front_matter.get(key, "")
        if content:
            sections.append(("front", key.replace("_", " ").title(), content))

    # Chapters
    for ch_num in sorted(chapters.keys()):
        text = chapters[ch_num]
        # Find chapter title from first ## heading
        title_match = re.search(r'^## (.+)', text, re.MULTILINE)
        ch_title = title_match.group(1) if title_match else f"Chapter {ch_num}"
        sections.append(("chapter", f"Chapter {ch_num}: {ch_title}", text))

    # Back matter
    bm_order = book_plan.get("back_matter", ["afterword", "glossary", "references", "about_author", "back_cover"])
    for key in bm_order:
        content = back_matter.get(key, "")
        if content:
            sections.append(("back", key.replace("_", " ").title(), content))

    return sections


def _build_pdf(sections, book_plan, path):
    """Build PDF using ReportLab."""
    doc = SimpleDocTemplate(
        path,
        pagesize=letter,
        leftMargin=1.25 * inch,
        rightMargin=1.25 * inch,
        topMargin=1.0 * inch,
        bottomMargin=1.0 * inch
    )

    styles = getSampleStyleSheet()

    # Custom styles
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

    story = []

    # Title page
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph(book_plan.get('title', 'Untitled'), title_style))
    if book_plan.get('subtitle'):
        story.append(Paragraph(book_plan['subtitle'], subtitle_style))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(f"by {book_plan.get('author_name', 'The Author')}", author_style))
    story.append(PageBreak())

    # TOC placeholder (ReportLab TOC requires two-pass; we do a simple text TOC)
    story.append(Paragraph("Table of Contents", h1_style))
    story.append(Spacer(1, 0.2 * inch))
    for stype, stitle, _ in sections:
        if stype == "chapter":
            story.append(Paragraph(stitle, body_style))
    story.append(PageBreak())

    # Content sections
    for stype, stitle, content in sections:
        if stype == "chapter":
            story.append(Paragraph(stitle, h1_style))
            story.append(Spacer(1, 0.1 * inch))
            _add_markdown_to_pdf(content, story, body_style, h2_style)
            story.append(PageBreak())
        else:
            story.append(Paragraph(stitle, h1_style))
            story.append(Spacer(1, 0.1 * inch))
            _add_markdown_to_pdf(content, story, front_style, h2_style)
            story.append(PageBreak())

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
            # Clean any remaining markdown
            clean = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
            clean = re.sub(r'\*(.*?)\*', r'<i>\1</i>', clean)
            if clean.strip():
                story.append(Paragraph(clean, body_style))


def _add_page_number(canvas, doc):
    """Add page number footer."""
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(letter[0] / 2, 0.5 * inch, str(doc.page))
    canvas.restoreState()


def _build_docx(sections, book_plan, path):
    """Build DOCX using python-docx."""
    doc = DocxDocument()

    # Page margins
    for section in doc.sections:
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.25)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)

    # Title page
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

    # TOC
    toc_heading = doc.add_heading('Table of Contents', level=1)
    for stype, stitle, _ in sections:
        if stype == "chapter":
            p = doc.add_paragraph(stitle)
            p.style = doc.styles['List Bullet']
    doc.add_page_break()

    # Sections
    for stype, stitle, content in sections:
        doc.add_heading(stitle, level=1)
        _add_markdown_to_docx(doc, content)
        doc.add_page_break()

    doc.save(path)


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
            p = doc.add_paragraph(line[2:], style='List Bullet')
        else:
            # Handle inline bold
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
