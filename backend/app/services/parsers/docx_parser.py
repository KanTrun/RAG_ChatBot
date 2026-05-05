"""DOCX parser using python-docx."""

from docx import Document

from app.services.parsers.base_parser import BaseParser, ParsedPage


class DocxParser(BaseParser):
    """Extract text from DOCX files, preserving heading structure."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".docx"]

    def parse(self, file_path: str) -> list[ParsedPage]:
        doc = Document(file_path)
        pages: list[ParsedPage] = []
        current_section = ""
        current_text_parts: list[str] = []
        page_counter = 1

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Track heading hierarchy as section names
            if para.style and para.style.name.startswith("Heading"):
                # Flush accumulated text as a page
                if current_text_parts:
                    pages.append(ParsedPage(
                        text="\n".join(current_text_parts),
                        page_number=page_counter,
                        metadata={"source_type": "docx", "section": current_section},
                    ))
                    page_counter += 1
                    current_text_parts = []
                current_section = text

            current_text_parts.append(text)

        # Flush remaining text
        if current_text_parts:
            pages.append(ParsedPage(
                text="\n".join(current_text_parts),
                page_number=page_counter,
                metadata={"source_type": "docx", "section": current_section},
            ))

        return pages
