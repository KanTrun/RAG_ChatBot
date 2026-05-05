"""HTML parser using BeautifulSoup."""

from bs4 import BeautifulSoup

from app.services.parsers.base_parser import BaseParser, ParsedPage


class HtmlParser(BaseParser):
    """Extract text from HTML, stripping scripts/styles."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".html", ".htm"]

    def parse(self, file_path: str) -> list[ParsedPage]:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            html = f.read()

        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""
        body = soup.body or soup
        pages: list[ParsedPage] = []
        current_section = title or "Document"
        current_parts: list[str] = []

        for element in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            text = element.get_text(" ", strip=True)
            if not text:
                continue

            if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                self._flush_section(pages, current_section, current_parts, title)
                current_section = text
                current_parts = []
                continue

            if not current_parts or current_parts[-1] != text:
                current_parts.append(text)

        self._flush_section(pages, current_section, current_parts, title)
        if pages:
            return pages

        fallback_text = body.get_text(separator="\n").strip()
        if not fallback_text:
            return []

        return [
            ParsedPage(
                text=fallback_text,
                page_number=1,
                metadata={"source_type": "html", "title": title, "section": current_section},
            )
        ]

    @staticmethod
    def _flush_section(
        pages: list[ParsedPage],
        section: str,
        parts: list[str],
        title: str,
    ) -> None:
        text = "\n\n".join(parts).strip()
        if not text:
            return
        pages.append(
            ParsedPage(
                text=text,
                page_number=len(pages) + 1,
                metadata={
                    "source_type": "html",
                    "title": title,
                    "section": section,
                },
            )
        )
