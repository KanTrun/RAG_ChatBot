"""Auto-detect and return appropriate parser by file extension."""

from pathlib import Path

from app.services.parsers.base_parser import BaseParser
from app.services.parsers.pdf_parser import PdfParser
from app.services.parsers.docx_parser import DocxParser
from app.services.parsers.html_parser import HtmlParser
from app.services.parsers.text_parser import TextParser


class UnsupportedFormatError(ValueError):
    """Raised when file format has no registered parser."""
    pass


# Extension → parser instance mapping
_PARSERS: dict[str, BaseParser] = {}


def _register_parsers() -> None:
    for parser_cls in [PdfParser, DocxParser, HtmlParser, TextParser]:
        parser = parser_cls()
        for ext in parser.supported_extensions:
            _PARSERS[ext.lower()] = parser


_register_parsers()

SUPPORTED_EXTENSIONS = set(_PARSERS.keys())


def get_parser(file_path: str) -> BaseParser:
    """Return parser for the given file path based on its extension."""
    ext = Path(file_path).suffix.lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        raise UnsupportedFormatError(
            f"Unsupported file format: '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return parser
