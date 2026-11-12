"""Plain text and Markdown parser with structure-aware section extraction."""

from pathlib import Path
import re

from app.services.parsers.base_parser import BaseParser, ParsedPage

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_NUMBERED_HEADING_RE = re.compile(
    r"^(?:(?:chapter|section|part|chương|phần|mục)\s+\d+[:.\s-]*|\d+(?:\.\d+){0,3}[\).\s-]+)(.+)$",
    re.IGNORECASE,
)


class TextParser(BaseParser):
    """Parse plain text and markdown files, extracting real sections."""

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
        doc_title = Path(file_path).stem.replace("-", " ").replace("_", " ").strip() or "Overview"
        current_section: str | None = None
        current_lines: list[str] = []
        explicit_heading_found = False

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if self._is_heading(line):
                explicit_heading_found = True
                if current_lines:
                    self._flush_section(
                        pages,
                        current_section or self._infer_section_title("\n".join(current_lines), doc_title, len(pages) + 1),
                        current_lines,
                        source_type,
                        doc_title,
                    )
                current_section = self._normalize_heading(line)
                current_lines = [f"## {current_section}"]
                continue
            current_lines.append(raw_line.rstrip())

        if current_lines:
            if not explicit_heading_found:
                # Split headingless plain text into topic-derived sections per paragraph group
                paragraphs = [p.strip() for p in "\n".join(current_lines).split("\n\n") if p.strip()]
                for idx, para in enumerate(paragraphs):
                    sec_title = self._infer_section_title(para, doc_title, idx + 1)
                    pages.append(
                        ParsedPage(
                            text=f"## {sec_title}\n{para}",
                            page_number=len(pages) + 1,
                            metadata={
                                "source_type": source_type,
                                "title": doc_title,
                                "section": sec_title,
                            },
                        )
                    )
            else:
                self._flush_section(
                    pages,
                    current_section or doc_title,
                    current_lines,
                    source_type,
                    doc_title,
                )

        return pages

    @staticmethod
    def _is_heading(line: str) -> bool:
        if not line or len(line) > 100:
            return False
        if _MD_HEADING_RE.match(line):
            return True
        if _NUMBERED_HEADING_RE.match(line) and not line.endswith((".", "!", "?")):
            return True
        if (
            len(line) <= 80
            and any(char.isalpha() for char in line)
            and line.upper() == line
            and not line.endswith((".", "!", "?"))
        ):
            return True
        if (
            line.endswith(":")
            and len(line.split()) <= 8
            and any(char.isalpha() for char in line)
            and line[0].isupper()
        ):
            return True
        return False

    @staticmethod
    def _normalize_heading(line: str) -> str:
        cleaned = re.sub(r"^#{1,6}\s*", "", line).strip(" :")
        return cleaned or "Overview"

    @staticmethod
    def _infer_section_title(text: str, doc_title: str, index: int) -> str:
        """Infer a concise section title from the leading sentence of a paragraph when no heading is present."""
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        if not first_line:
            return f"{doc_title} - Section {index}"
        first_sentence = re.split(r"[.!?]", first_line)[0].strip()
        words = first_sentence.split()
        if 2 <= len(words) <= 7:
            return first_sentence.strip(" :")
        if len(words) > 7:
            return " ".join(words[:6]).strip(" ,;:")
        return f"{doc_title} - Section {index}"

    def _flush_section(
        self,
        pages: list[ParsedPage],
        section: str,
        lines: list[str],
        source_type: str,
        doc_title: str,
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
                        "title": doc_title,
                        "section": section,
                    },
                )
            )
