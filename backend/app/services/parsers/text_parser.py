"""Plain text parser."""

import re

from app.services.parsers.base_parser import BaseParser, ParsedPage


class TextParser(BaseParser):
    """Parse plain text and markdown files."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".txt", ".md"]

    def parse(self, file_path: str) -> list[ParsedPage]:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read().strip()

        if not content:
            return []

        pages: list[ParsedPage] = []
        source_type = "markdown" if file_path.lower().endswith(".md") else "text"
        current_section = "Document"
        current_lines: list[str] = []

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if self._is_heading(line):
                self._flush_section(pages, current_section, current_lines, source_type)
                current_section = self._normalize_heading(line)
                current_lines = []
                continue
            current_lines.append(raw_line.rstrip())

        self._flush_section(pages, current_section, current_lines, source_type)

        return pages

    @staticmethod
    def _is_heading(line: str) -> bool:
        if not line:
            return False
        if re.match(r"^#{1,6}\s+\S+", line):
            return True
        return (
            len(line) <= 80
            and any(char.isalpha() for char in line)
            and line.upper() == line
            and not line.endswith((".", "!", "?"))
        )

    @staticmethod
    def _normalize_heading(line: str) -> str:
        return re.sub(r"^#{1,6}\s*", "", line).strip(" :") or "Document"

    def _flush_section(
        self,
        pages: list[ParsedPage],
        section: str,
        lines: list[str],
        source_type: str,
    ) -> None:
        text = "\n".join(lines).strip()
        if not text:
            return

        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
        grouped: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for paragraph in paragraphs:
            current_parts.append(paragraph)
            current_len += len(paragraph)
            if current_len >= 300:
                grouped.append("\n\n".join(current_parts))
                current_parts = []
                current_len = 0

        if current_parts:
            grouped.append("\n\n".join(current_parts))

        for grouped_text in grouped:
            pages.append(
                ParsedPage(
                    text=grouped_text,
                    page_number=len(pages) + 1,
                    metadata={
                        "source_type": source_type,
                        "section": section,
                    },
                )
            )
