"""RAG prompt template: assembles system prompt + sanitized XML context + language/intent guidance into messages."""

from __future__ import annotations

from app.prompts.system_prompt import (
    detect_query_language,
    get_intent_formatting_instructions,
)
from app.security.prompt_guard import sanitize_context_chunks, sanitize_input


def build_rag_messages(
    context: str,
    query: str,
    system_prompt: str,
    conversation_history: list[dict] | None = None,
    answer_brief: str | None = None,
    intent: str | None = None,
) -> list[dict]:
    """Build the message list for the LLM call.

    Returns OpenAI-style messages: [{role, content}, ...].
    """
    language = detect_query_language(query)
    lang_directive = (
        "LANGUAGE REQUIREMENT: Người dùng đang hỏi bằng TIẾNG VIỆT. "
        "Bạn BẮT BUỘC phải trả lời hoàn toàn bằng TIẾNG VIỆT tự nhiên, chuyên nghiệp, "
        "kể cả khi tài liệu gốc bằng tiếng Anh."
        if language == "vi"
        else "LANGUAGE REQUIREMENT: The user asked in ENGLISH. "
        "You MUST write your entire response in natural, professional ENGLISH, "
        "even if the source documents are in Vietnamese."
    )
    format_directive = get_intent_formatting_instructions(intent or "factual", language)

    enhanced_system_prompt = f"{system_prompt}\n\n{lang_directive}\n{format_directive}"
    messages: list[dict] = [{"role": "system", "content": enhanced_system_prompt}]

    if conversation_history:
        messages.extend(conversation_history)

    parts: list[str] = []
    if answer_brief:
        parts.append(f"<evidence_brief>\n{sanitize_context_chunks(answer_brief)}\n</evidence_brief>")
    if context and context.strip():
        parts.append(
            "<retrieved_context>\n"
            f"{sanitize_context_chunks(context)}\n"
            "</retrieved_context>"
        )
    parts.append(f"Question: {sanitize_input(query)}")
    user_content = "\n\n".join(parts)
    messages.append({"role": "user", "content": user_content})

    return messages
