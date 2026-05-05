"""PDF parser using PyMuPDF (fitz)."""

import fitz  # pymupdf

from app.services.parsers.base_parser import BaseParser, ParsedPage


class PdfParser(BaseParser):
    """Extract text from PDF files using PyMuPDF."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: str) -> list[ParsedPage]:
        pages: list[ParsedPage] = []

        doc = fitz.open(file_path)
        try:
            doc_title = doc.metadata.get("title", "") if doc.metadata else ""

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text").strip()

                if not text:
                    continue

                section = self._detect_page_section(text)

                pages.append(ParsedPage(
                    text=text,
                    page_number=page_num + 1,
                    metadata={
                        "source_type": "pdf",
                        "title": doc_title,
                        "section": section,
                    },
                ))
        finally:
            doc.close()

        return pages

    @staticmethod
    def _detect_page_section(text: str) -> str | None:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or len(line) > 90:
                continue
            if line.isupper():
                return line
            if line == line.title() and not line.endswith((".", "!", "?")):
                return line
        return None
