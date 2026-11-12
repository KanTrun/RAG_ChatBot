"""DOCX parser using python-docx with multi-level section extraction."""

from pathlib import Path
import re

from docx import Document

from app.services.parsers.base_parser import BaseParser, ParsedPage

_NUMBERED_HEADING_RE = re.compile(
    r"^(?:(?:chapter|section|part|chương|phần|mục)\s+\d+[:.\s-]*|\d+(?:\.\d+){0,3}[\).\s-]+)(.+)$",
    re.IGNORECASE,
)


class DocxParser(BaseParser):
    """Extract text from DOCX files, preserving real heading hierarchy and sections."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".docx"]

    def parse(self, file_path: str) -> list[ParsedPage]:
        doc = Document(file_path)
        doc_title = (doc.core_properties.title or "").strip() or Path(file_path).stem.replace("-", " ").replace("_", " ").strip()
        pages: list[ParsedPage] = []
        current_section = doc_title or "Overview"
        current_text_parts: list[str] = []
        page_counter = 1

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            heading_level = self._detect_paragraph_heading_level(para, text)
            if heading_level is not None:
                if current_text_parts:
                    pages.append(
                        ParsedPage(
                            text="\n\n".join(current_text_parts),
                            page_number=page_counter,
                            metadata={
                                "source_type": "docx",
                                "title": doc_title,
                                "section": current_section,
                            },
                        )
                    )
                    page_counter += 1
                    current_text_parts = []
                current_section = text.strip(" :")
                current_text_parts.append(f"{'#' * heading_level} {current_section}")
                continue

            current_text_parts.append(text)

        # Also extract text from DOCX tables if present
        for table_idx, table in enumerate(doc.tables):
            table_rows: list[str] = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    table_rows.append(" | ".join(cells))
            if table_rows:
                current_text_parts.append("\n".join(table_rows))

        if current_text_parts:
            pages.append(
                ParsedPage(
                    text="\n\n".join(current_text_parts),
                    page_number=page_counter,
                    metadata={
                        "source_type": "docx",
                        "title": doc_title,
                        "section": current_section,
                    },
                )
            )

        return pages

    @staticmethod
    def _detect_paragraph_heading_level(para, text: str) -> int | None:
        style_name = (para.style.name if para.style and para.style.name else "").strip()
        if style_name.startswith("Heading"):
            parts = style_name.split()
            if len(parts) >= 2 and parts[-1].isdigit():
                return min(max(int(parts[-1]), 1), 6)
            return 1
        if style_name in {"Title", "Subtitle"}:
            return 1 if style_name == "Title" else 2

        if len(text) <= 100 and not text.endswith((".", "!", "?", ";", ",")):
            if _NUMBERED_HEADING_RE.match(text):
                return 2
            if text.isupper() and any(c.isalpha() for c in text) and len(text.split()) <= 12:
                return 1
            runs = [r for r in para.runs if r.text.strip()]
            if runs and all(bool(r.bold) for r in runs) and len(text.split()) <= 12:
                return 2
        return None
