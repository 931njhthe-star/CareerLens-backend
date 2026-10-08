"""Export fictional desktop resumes as text-selectable Korean PDFs.

Requires ReportLab and an installed Korean TTF font. No network calls or DB
writes are performed. TXT equivalents are produced by generate_matching_fixtures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
HEADINGS = {
    "기본정보",
    "핵심 소개",
    "경력 및 프로젝트",
    "보유 역량",
    "학력 및 교육",
    "자기소개",
    "경험 범위",
    "희망 근무조건",
}


def make_styles() -> dict[str, ParagraphStyle]:
    base = {
        "fontName": "ResumeKorean",
        "textColor": colors.HexColor("#222C2B"),
        "wordWrap": "CJK",
        "alignment": TA_LEFT,
        "splitLongWords": True,
    }
    return {
        "title": ParagraphStyle("title", **base, fontSize=22, leading=30, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", **base, fontSize=12, leading=18, spaceAfter=5),
        "notice": ParagraphStyle("notice", **base, fontSize=8, leading=12, spaceAfter=10),
        "heading": ParagraphStyle(
            "heading",
            **{**base, "fontName": "ResumeKoreanBold"},
            fontSize=10.2,
            leading=15,
            spaceBefore=7,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle("body", **base, fontSize=9.8, leading=14, spaceAfter=3),
    }


def page_footer(canvas, document):
    canvas.saveState()
    canvas.setFont("ResumeKorean", 8)
    canvas.setFillColor(colors.HexColor("#62726A"))
    canvas.drawString(19 * mm, 13 * mm, "CareerLens · 경력 및 자기소개")
    canvas.drawRightString(A4[0] - 19 * mm, 13 * mm, str(document.page))
    canvas.restoreState()


def export_pdf(item: dict, index: int, destination: Path, styles: dict) -> Path:
    filename = f"{index:02d}_{item['title'].replace(' ', '_')}_가상이력서.pdf"
    path = destination / filename
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=19 * mm,
        leftMargin=19 * mm,
        topMargin=17 * mm,
        bottomMargin=21 * mm,
        title=f"AI 오케스트레이션 가상 이력서 {index:02d} {item['title']}",
        author="CareerLens fictional fixtures",
        subject="Synthetic test data; not a real person's resume",
    )
    lines = item["resume_text"].splitlines()
    story = [
        Paragraph(escape(item["title"]), styles["title"]),
        Paragraph(escape(lines[0]), styles["subtitle"]),
        Paragraph(escape(lines[1]), styles["body"]),
        Paragraph(escape(lines[2]), styles["notice"]),
        Spacer(1, 2 * mm),
    ]
    if item.get("resume_sections"):
        for block in item["resume_sections"]:
            if block["title"] == "핵심 프로젝트 2":
                story.append(PageBreak())
            story.append(Paragraph(escape(block["title"]), styles["heading"]))
            for paragraph in block["paragraphs"]:
                story.append(Paragraph(escape(paragraph).replace("\n", "<br/>"), styles["body"]))
    else:
        for line in lines[3:]:
            if not line.strip():
                continue
            style = styles["heading"] if line in HEADINGS else styles["body"]
            story.append(Paragraph(escape(line), style))
    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/malgun.ttf"))
    parser.add_argument("--bold-font", type=Path, default=Path("C:/Windows/Fonts/malgunbd.ttf"))
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("ResumeKorean", str(args.font)))
    pdfmetrics.registerFont(TTFont("ResumeKoreanBold", str(args.bold_font)))
    args.destination.mkdir(parents=True, exist_ok=True)
    source = ROOT / "data" / "examples" / "desktop_ai_resumes.json"
    items = json.loads(source.read_text(encoding="utf-8"))["items"]
    styles = make_styles()
    for index, item in enumerate(items, 1):
        result = export_pdf(item, index, args.destination, styles)
        print(result.name)


if __name__ == "__main__":
    main()
