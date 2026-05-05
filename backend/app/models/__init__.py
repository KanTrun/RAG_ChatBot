"""Export all models so Alembic can auto-discover them."""

from app.models.base import Base, UUIDMixin, TimestampMixin
from app.models.user import User, Role, user_roles
from app.models.document import Document, DocumentStatus
from app.models.chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.feedback import Feedback
from app.models.audit import AuditLog

__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    "User",
    "Role",
    "user_roles",
    "Document",
    "DocumentStatus",
    "DocumentChunk",
    "Conversation",
    "Message",
    "MessageRole",
    "Feedback",
    "AuditLog",
]
