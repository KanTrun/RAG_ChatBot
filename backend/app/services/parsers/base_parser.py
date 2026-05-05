"""Abstract parser interface for document text extraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    """Single page/section of extracted text from a document."""

    text: str
    page_number: int | None = None
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract base for document parsers."""

    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedPage]:
        """Parse document and return list of pages with text content."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return list of file extensions this parser handles."""
        ...
