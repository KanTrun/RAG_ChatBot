"""Feedback router: thumbs up/down on messages."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.dependencies import get_db
from app.models.conversation import Conversation
from app.models.feedback import Feedback
from app.models.message import Message
from app.schemas.feedback_schemas import FeedbackCreate

router = APIRouter(tags=["feedback"])


@router.post(
    "/messages/{message_id}/feedback",
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    message_id: UUID,
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Submit or update feedback (thumbs up/down) for a message."""
    # Verify message exists and user owns the conversation
    msg = await db.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")

    conv = await db.get(Conversation, msg.conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your conversation")

    # Upsert feedback
    existing = await db.execute(
        select(Feedback).where(Feedback.message_id == message_id)
    )
    feedback = existing.scalar_one_or_none()

    if feedback:
        feedback.score = body.score
        feedback.comment = body.comment
    else:
        feedback = Feedback(
            message_id=message_id,
            user_id=user.id,
            score=body.score,
            comment=body.comment,
        )
        db.add(feedback)

    await db.commit()
    return {"status": "ok", "feedback_id": str(feedback.id)}
