"""RAG prompt template: assembles system prompt + context + query into messages."""


def build_rag_messages(
    context: str,
    query: str,
    system_prompt: str,
    conversation_history: list[dict] | None = None,
    answer_brief: str | None = None,
) -> list[dict]:
    """Build the message list for the LLM call.

    Returns OpenAI-style messages: [{role, content}, ...].
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add conversation history (if multi-turn)
    if conversation_history:
        messages.extend(conversation_history)

    parts: list[str] = []
    if answer_brief:
        parts.append(f"Evidence brief:\n{answer_brief}")
    parts.append(f"Context:\n{context}")
    parts.append(f"Question: {query}")
    user_content = "\n\n".join(parts)
    messages.append({"role": "user", "content": user_content})

    return messages
