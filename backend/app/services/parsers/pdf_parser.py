"""PDF parser using PyMuPDF (fitz) with structure-aware section heading extraction."""

from __future__ import annotations

from pathlib import Path
import re

from app.services.parsers.base_parser import BaseParser, ParsedPage

_NUMBERED_SECTION_RE = re.compile(
    r"^(?:(?:chapter|section|part|chương|phần|mục)\s+\d+[:.\s-]*|\d+(?:\.\d+){0,3}[\).\s-]+)([A-ZÀ-Ỹ].+)$",
    re.IGNORECASE,
)


class PdfParser(BaseParser):
    """Extract text and real section headings from PDF files."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: str) -> list[ParsedPage]:
        try:
            import fitz  # pymupdf

            return self._parse_with_fitz(file_path, fitz)
        except ImportError:
            return self._parse_with_pypdf(file_path)

    def _parse_with_fitz(self, file_path: str, fitz_module) -> list[ParsedPage]:
        pages: list[ParsedPage] = []
        doc = fitz_module.open(file_path)
        try:
            doc_title = (doc.metadata.get("title", "") if doc.metadata else "").strip()
            if not doc_title:
                doc_title = Path(file_path).stem.replace("-", " ").replace("_", " ").strip()

            active_section: str | None = None
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                structured_text, detected_headings = self._extract_structured_page_text(page)
                if not structured_text:
                    continue

                page_section = (
                    detected_headings[0]
                    if detected_headings
                    else self._detect_page_section(structured_text)
                    or active_section
                    or f"{doc_title} - Page {page_num + 1}"
                )
                if detected_headings:
                    active_section = detected_headings[-1]
                elif page_section:
                    active_section = page_section

                pages.append(
                    ParsedPage(
                        text=structured_text,
                        page_number=page_num + 1,
                        metadata={
                            "source_type": "pdf",
                            "title": doc_title,
                            "section": page_section,
                            "headings": detected_headings,
                        },
                    )
                )
        finally:
            doc.close()

        return pages

    def _parse_with_pypdf(self, file_path: str) -> list[ParsedPage]:
        import pypdf

        reader = pypdf.PdfReader(file_path)
        doc_title = Path(file_path).stem.replace("-", " ").replace("_", " ").strip()
        pages: list[ParsedPage] = []
        active_section: str | None = None

        for idx, page in enumerate(reader.pages):
            raw_text = (page.extract_text() or "").strip()
            if not raw_text:
                continue
            section = self._detect_page_section(raw_text) or active_section or f"{doc_title} - Page {idx + 1}"
            active_section = section
            pages.append(
                ParsedPage(
                    text=raw_text,
                    page_number=idx + 1,
                    metadata={
                        "source_type": "pdf",
                        "title": doc_title,
                        "section": section,
                    },
                )
            )
        return pages

    def _extract_structured_page_text(self, page) -> tuple[str, list[str]]:
        """Inspect PDF font sizes and line patterns to emit Markdown headings for real sections."""
        try:
            page_dict = page.get_text("dict")
        except Exception:
            raw = page.get_text("text").strip()
            sec = self._detect_page_section(raw)
            return raw, ([sec] if sec else [])

        blocks = page_dict.get("blocks", [])
        line_entries: list[tuple[str, float, bool]] = []
        font_sizes: list[float] = []

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text_parts = [str(s.get("text") or "") for s in spans]
                line_text = "".join(text_parts).strip()
                if not line_text:
                    continue
                max_size = max((float(s.get("size") or 10.0) for s in spans), default=10.0)
                is_bold = any("bold" in str(s.get("font") or "").lower() for s in spans)
                line_entries.append((line_text, max_size, is_bold))
                font_sizes.append(max_size)

        if not line_entries:
            raw = page.get_text("text").strip()
            sec = self._detect_page_section(raw)
            return raw, ([sec] if sec else [])

        sorted_sizes = sorted(font_sizes)
        median_size = sorted_sizes[len(sorted_sizes) // 2] if sorted_sizes else 11.0
        output_lines: list[str] = []
        detected_headings: list[str] = []

        for line_text, size, is_bold in line_entries:
            clean = re.sub(r"\s+", " ", line_text).strip()
            if not clean:
                continue

            is_font_heading = (
                len(clean) <= 100
                and not clean.endswith((".", "!", "?", ";", ","))
                and (size >= median_size * 1.15 or (is_bold and size >= median_size * 1.05 and len(clean.split()) <= 12))
            )
            is_pattern_heading = self._is_heading_line(clean)

            if is_font_heading or is_pattern_heading:
                level = 1 if size >= median_size * 1.3 else 2
                heading_clean = re.sub(r"^#{1,6}\s*", "", clean).strip(" :")
                if heading_clean and heading_clean not in detected_headings:
                    detected_headings.append(heading_clean)
                output_lines.append(f"\n{'#' * level} {heading_clean}\n")
            else:
                output_lines.append(clean)

        return "\n".join(output_lines).strip(), detected_headings

    @classmethod
    def _detect_page_section(cls, text: str) -> str | None:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if cls._is_heading_line(line):
                return re.sub(r"^#{1,6}\s*", "", line).strip(" :")
        return None

    @staticmethod
    def _is_heading_line(line: str) -> bool:
        if not line or len(line) > 95:
            return False
        if line.startswith("#"):
            return True
        if _NUMBERED_SECTION_RE.match(line) and not line.endswith((".", "!", "?")):
            return True
        if line.isupper() and any(c.isalpha() for c in line) and len(line.split()) <= 12:
            return True
        if line == line.title() and 1 <= len(line.split()) <= 10 and not line.endswith((".", "!", "?", ",", ";")):
            return True
        return False
