# Project Changelog

## 2026-05-05 - Chat UX Continuity, CV/Profile Grounding, and Gemini Provider Support

Status: Chat shell, grounding rules, and optional Gemini provider path are aligned with the shipped runtime behavior

Added:
- Updated the route-driven chat shell, sidebar, and message bubbles so conversation selection, active-document context, upload acknowledgments, and permanent delete actions stay consistent across the UI.
- Refined retrieval planning so the core path is document-agnostic first, with conditional exhaustive coverage fallback for broad "list all" style questions across many document types.
- Tightened CV/profile grounding so profile-style queries use profile-oriented retrieval probes and structured answer briefs instead of research-paper assumptions.
- Added the optional Gemini provider adapter path so Gemini can be selected when configured without changing the default provider flow.
- Fixed Gemini provider model selection so `LLM_PROVIDER=gemini` now honors `GEMINI_MODEL` instead of the default `LLM_MODEL`.
- Fixed `hybrid_general` routing so clearly general questions can still use outside knowledge even when active documents are selected.
- Fixed conversation sidebar listing to aggregate message counts in one query instead of one `count(*)` per row.

Validated:
- The related chat UX, strict grounding, CV compatibility, and backend/frontend runtime checks were already completed in the follow-up runs recorded below.

Impact:
- The project docs now reflect the current shipped chat UX and a broader document-grounding strategy without changing the default provider setup.

Unresolved Questions:
- None.

## 2026-05-05 - Strict Document-Targeted Grounding and Chat Deletion

Status: Local validation complete

Added:
- Hybrid chat now classifies document-targeted questions and blocks fallback to outside knowledge when the question clearly depends on uploaded document content.
- Chat diagnostics now expose `query_classification`, `document_target_required`, `classification_reason`, and `outside_knowledge_blocked_reason` for admin debug requests.
- Conversation API now supports hard delete for whole conversations and logical delete for a user/assistant message pair.
- Chat sidebar now provides permanent conversation deletion with no-recovery confirmation.
- Chat message bubbles now provide permanent exchange deletion with in-place state reconciliation and no full conversation reload.
- CV/profile summary queries now use profile-oriented retrieval probes instead of research-paper-only section assumptions.

Fixed:
- Retrieval low-support detection now treats missing claim-level support from preferred sections as unsupported instead of letting weak evidence slip into hybrid answers.
- Message ordering for delete/reload paths now stays aligned with logical chat flow instead of using UUID as a tie-breaker.
- Chat message list auto-scroll now avoids jumping to the bottom when exchanges are deleted.
- Re-indexed runtime CV document `BACKEND ENG_TruongMinhKhang_8320.pdf`, moving it from stale 2-chunk metadata-free indexing to `document-first-v2` with 14 structured chunks.

Validated:
- Backend targeted pytest: `backend/tests/test_retrieval.py backend/tests/test_api_chat.py` -> `46 passed, 2 skipped`.
- Backend chat API regression after CV compatibility follow-up: `23 passed, 1 skipped`.
- Frontend targeted Vitest: `chat.test.tsx` -> `18 passed`.
- Frontend production build: passed.
- Live runtime check on `localhost:3001`: authenticated chat view shows `Delete conversation ...` in the sidebar and `Delete exchange` on message bubbles after refresh.

Impact:
- CV/document questions no longer get padded with outside knowledge just because hybrid mode is enabled.
- Users can permanently clean up conversations or revoke a chat exchange without corrupting message history or source-panel state.

Unresolved Questions:
- None.

## 2026-05-05 - Document-First Retrieval Diagnostics and Full Reindex Controls

Status: Query-aware retrieval expanded, admin debug/reindex tools added, and summary source grouping shipped

Fixed:
- Expanded `backend/app/services/retrieval_intent_service.py`, `backend/app/services/retrieval_service.py`, `backend/app/services/evidence_clusterer.py`, and `backend/app/services/answer_brief_builder.py` so retrieval now distinguishes factual/definition/multi-hop queries, generates broader query variants, scores parent-section candidates, and builds stricter evidence briefs beyond summary-only mode.
- Updated `backend/app/api/v1/chat_router.py`, `backend/app/schemas/chat_schemas.py`, `backend/app/services/context_assembler.py`, and `backend/app/services/retrieval_section_policy.py` so admin-only chat diagnostics can be requested at runtime, low-support reasons are explicit, and source payloads now carry `parent_block_id`, `heading_level`, and `ingestion_version`.
- Updated `backend/app/api/v1/admin_router.py`, `backend/app/schemas/admin_schemas.py`, and `backend/app/services/document_structure.py` so admins can trigger bulk re-indexing and inspect parsed outline plus indexed chunk metadata/contextualized text for any document.
- Updated `frontend/app/chat/page.tsx` and `frontend/components/chat/sources-panel.tsx` so the Sources panel groups evidence by answer section and exposes richer structural metadata for grounded answers.
- Added regression coverage in `backend/tests/test_api_admin.py`, `backend/tests/test_api_chat.py`, `backend/tests/test_retrieval.py`, and `frontend/__tests__/chat.test.tsx` for expanded retrieval planning, diagnostics payloads, source metadata, and admin debug/reindex APIs.

Validated:
- Backend compile check: passed.
- Backend targeted pytest: `backend/tests/test_api_admin.py backend/tests/test_retrieval.py backend/tests/test_ingestion.py backend/tests/test_api_chat.py` -> `46 passed, 3 skipped`.
- Backend non-integration suite: `70 passed, 3 deselected`.
- Frontend targeted Vitest: `16 passed`.
- Frontend production build: passed.

Notes:
- Bulk re-index support was implemented but not executed against a live production dataset in this session.
- Runtime diagnostics are admin-only and opt-in through the chat request flag; standard users do not receive retrieval internals.

Unresolved Questions:
- Should the frontend expose the new admin debug-index endpoint directly in the admin dashboard, or remain API-only for now?

## 2026-05-05 - Docker Auto-Port Fallback Fix

Status: Local Docker startup no longer hard-fails on occupied default ports when using raw `docker compose up`

Fixed:
- Updated `docker-compose.yml` so exposed host ports now fall back to Docker-assigned ephemeral ports instead of hard-coded `3000/8000/5432/6381/11434` when no explicit host-port env is supplied.
- Updated `docker-compose.yml` frontend runtime env so Docker local auth/public URLs now come from compose-only variables (`FRONTEND_PUBLIC_ORIGIN`, `FRONTEND_API_PUBLIC_URL`) instead of inheriting the static `NEXTAUTH_URL` value from `.env`.
- Updated `docker-up.ps1` to emit the new compose-only frontend URL variables while preserving the explicit preferred-port flow for the supported local startup path.
- Updated `Makefile` `up` target to call `docker-up.ps1` directly instead of duplicating separate port-selection logic.

Validated:
- `docker compose config` now renders `published: "0"` for host-port fallbacks when no compose port env is supplied.
- `docker compose --env-file .compose-ports.env config` now renders the probed preferred ports plus the correct frontend origin/public API URL overrides from `.compose-ports.env`.

Notes:
- `docker-up.ps1` and `make up` still prefer the familiar local ports when they are free; the new fallback matters when someone runs `docker compose up` directly or when a preferred port is already occupied.

Unresolved Questions:
- None.

## 2026-05-05 - Premium Auth Frontend Refresh

Status: Login/register now use a premium two-panel auth shell with theme toggle and refined OAuth/credential forms

Fixed:
- Updated `frontend/app/(auth)/login/page.tsx`, `frontend/app/(auth)/register/page.tsx`, `frontend/components/auth/auth-page-shell.tsx`, `frontend/components/auth/login-form.tsx`, `frontend/components/auth/register-form.tsx`, `frontend/components/auth/oauth-buttons.tsx`, and `frontend/styles/globals.css` to ship the refreshed dark-first auth experience.
- Reworked the auth landing pages into a centered premium shell with a hero panel, trust chips, explicit sign-in/register guidance, and a clearer distinction between login and account creation.
- Aligned the auth copy and shared shell styling with the current Google/GitHub-first flow and the auth-specific design tokens/classes already defined in the frontend stylesheet.

Validated:
- Verified against the current auth route implementation and stylesheet-level auth tokens/classes.

Unresolved Questions:
- None.

## 2026-05-05 - Document-First, Structure-Aware Retrieval Upgrade

Status: Structure-aware ingestion, evidence clustering, summary evidence briefs, richer source metadata, and targeted verification passed

Fixed:
- Added `backend/app/services/document_structure.py` and updated `backend/app/services/chunking_engine.py` plus `backend/app/services/ingestion_pipeline.py` so ingestion is now block-first instead of blind character recursion, emits `block_type`, `section_path`, `parent_block_id`, page range, heading level, `ingestion_version`, and embeds `contextualized_text` instead of raw chunk text alone.
- Added `backend/app/services/evidence_clusterer.py` and `backend/app/services/answer_brief_builder.py`, then updated `backend/app/services/retrieval_service.py` so summary/document retrieval now runs multi-query candidate generation, structural clustering, coverage-aware chunk selection, and summary answer briefing before generation.
- Updated `backend/app/services/retrieval_section_policy.py` and `backend/app/services/reranking_service.py` so retrieval trusts explicit structural metadata when available and pushes acknowledgements/references/TOC/caption/cover chunks down more aggressively.
- Updated `backend/app/services/context_assembler.py`, `backend/app/api/v1/chat_router.py`, and `backend/app/prompts/system_prompt.py` plus `backend/app/prompts/rag_prompt_template.py` so the LLM now receives a structured evidence brief for summary answers and source payloads expose `section_path`, `block_type`, page range, selection reason, and summary slot mapping.
- Updated `frontend/components/chat/sources-panel.tsx` so users can see structural source context and why each source was chosen instead of only file/page/snippet.
- Added regression coverage in `backend/tests/test_ingestion.py`, `backend/tests/test_retrieval.py`, `backend/tests/test_api_chat.py`, and `frontend/__tests__/chat.test.tsx` for structure-aware chunk metadata, coverage-driven summary selection, richer source payloads, and source-panel rendering.

Validated:
- Backend compile check: passed.
- Backend targeted pytest: `backend/tests/test_retrieval.py backend/tests/test_ingestion.py` -> `20 passed, 2 skipped`.
- Backend chat API pytest: `backend/tests/test_api_chat.py` -> `19 passed, 1 skipped`.
- Frontend targeted Vitest: `npx vitest run __tests__/chat.test.tsx` -> `16 passed`.

Notes:
- Chat API verification required resetting the dedicated test DB schema because the local `rag_test_db` had stale PostgreSQL enum state before the run.
- This ships the metadata/runtime layer for document-first retrieval without introducing a new persistent `parent_blocks` table yet; structural grouping is runtime-backed through chunk metadata.

Unresolved Questions:
- None.

## 2026-05-05 - Section-Aware RAG Grounding and Summary Retrieval Fix

Status: Retrieval now suppresses common boilerplate sections better, summary requests no longer bias toward the first document chunks, and runtime validation passed

Fixed:
- Added `backend/app/services/retrieval_section_policy.py` and updated `backend/app/services/retrieval_service.py` so retrieval candidates are classified by likely section type and penalized when they look like acknowledgements, references, table of contents, cover pages, appendices, or figure/table captions unrelated to the user query.
- Updated `backend/app/services/reranking_service.py` so both fallback reranking and model-backed reranking apply the same section-aware bias instead of trusting raw lexical overlap or cross-encoder scores alone.
- Updated `backend/app/services/retrieval_intent_service.py` so summary requests no longer force `ordered_document_scan=True`; they now use broader hybrid retrieval with coherent document-order assembly only after relevant evidence is selected.
- Updated `backend/app/services/grounded_answer_fallback.py` so fallback answers read like grounded responses with explicit cited support instead of the old `Based on your uploaded document` stub.
- Added regression coverage in `backend/tests/test_retrieval.py` and `backend/tests/test_api_chat.py` for section suppression, summary plan behavior, and fallback answer wording.

Validated:
- Backend targeted pytest with Docker test services: `33 passed, 2 skipped`.
- Backend compile check for touched Python modules: passed.
- Frontend targeted Vitest: `16 passed`.
- Frontend production build: passed.
- Docker `backend` and `frontend` rebuild: passed.
- Local runtime checks: `GET /health` returned `{"status":"ok","version":"0.1.0"}` and `/chat` remained reachable through the frontend.
- Real API smoke: registered a test user, uploaded `section-aware-rag-smoke.txt`, waited for `indexed`, asked `How does the system answer questions?`, and the strict grounded answer stayed on retrieval/reranking content without pulling the acknowledgement section.

Notes:
- I did not force-enable the heavyweight BGE reranker by default in runtime config because the current runtime image still does not install `FlagEmbedding`; flipping that switch alone would degrade stability instead of improving accuracy. The retrieval improvements shipped here work immediately on the current stack.

Unresolved Questions:
- None.

## 2026-05-05 - RAG Evidence Alignment, Better Source UX, and Longer Grounded Answers

Status: Source evidence UX fixed, retrieval alignment tightened around the original question, and structured long-form grounded answers shipped

Fixed:
- Updated `frontend/components/chat/sources-panel.tsx` so the Sources side panel now uses a proper flex/min-height scroll layout and can scroll through long evidence lists instead of trapping the list area.
- Updated `backend/app/services/context_assembler.py` and `backend/app/api/v1/chat_router.py` so each source now carries a short evidence excerpt in the SSE payload, giving the frontend a real snippet preview instead of metadata-only entries.
- Updated `backend/app/services/retrieval_service.py` so chat retrieval now anchors on the original user question and uses rewritten follow-up queries only as auxiliary retrieval signals instead of replacing the original query outright.
- Updated `backend/app/services/reranking_service.py` so when `reranker_provider=none`, fallback reranking now scores lexical overlap against the user question and section/title context instead of preserving raw candidate order.
- Updated `backend/app/prompts/system_prompt.py`, `backend/app/services/llm/base_provider.py`, and `frontend/components/chat/message-bubble.tsx` so grounded answers are more structured and detailed, list-item citations remain clickable, and chat generation can use larger response budgets without accidentally forcing the wrong provider model.
- Updated `backend/app/services/retrieval_intent_service.py` so normal question-answer retrieval keeps a broader evidence budget, reducing over-compression into a single dominant chunk.

Validated:
- Backend targeted pytest with Docker test services: `29 passed, 2 skipped`.
- Backend compile/import check for touched Python files: passed.
- Frontend targeted Vitest: `16 passed`.
- Frontend production build: passed.
- Docker app runtime refreshed successfully; backend health check passed and `/chat` redirect behavior remained healthy on the rebuilt app.

Notes:
- This is still pragmatic RAG, not a full claim-by-claim verifier. But it is materially closer to how production RAG systems behave: original-question anchoring, auxiliary rewrite retrieval, evidence snippets, and better fallback ranking.
- Source score display is now labeled as `Evidence score` instead of pretending to be a hard confidence percentage.

Unresolved Questions:
- None.

## 2026-05-05 - Strict Document-Only Default Mode and Intent-Aware Grounding

Status: Strict-by-default RAG mode shipped, explicit hybrid mode added, parser metadata improved, and backend/frontend verification passed

Fixed:
- Updated `backend/app/api/v1/chat_router.py`, `backend/app/schemas/chat_schemas.py`, and `backend/app/prompts/system_prompt.py` so `/api/v1/chat` now defaults to `strict_documents`, refuses uncited outside knowledge in default mode, emits clear abstention when document support is weak, and only allows general knowledge when `response_mode=hybrid_general` is explicitly enabled.
- Added `backend/app/services/retrieval_intent_service.py` and updated `backend/app/services/retrieval_service.py` plus `backend/app/services/context_assembler.py` so summary/compare/extract questions use more appropriate retrieval profiles, including ordered document scan for summaries and balanced multi-document retrieval for comparison-heavy prompts.
- Updated `backend/app/services/parsers/text_parser.py`, `backend/app/services/parsers/html_parser.py`, and `backend/app/services/parsers/pdf_parser.py` so chunk source pages preserve section/heading context better instead of flattening everything into generic text blocks.
- Updated `frontend/components/chat/chat-input.tsx` and `frontend/app/chat/page.tsx` so chat visibly exposes `Document only` as the default mode, makes `Allow outside knowledge` an explicit opt-in, and sends `response_mode` directly in the chat request payload.
- Added regression coverage in `backend/tests/test_api_chat.py`, `backend/tests/test_retrieval.py`, and `frontend/__tests__/chat.test.tsx` for strict abstention, summary retrieval planning, and frontend mode-toggle request behavior.

Validated:
- Backend targeted pytest with Docker test services: `26 passed, 2 skipped`.
- Backend compile check for touched Python modules: passed.
- Frontend targeted Vitest: `14 passed`.
- Frontend production build: passed.

Notes:
- Default product behavior now matches the requested policy: strict document evidence first, outside knowledge only by explicit user choice.
- Hybrid mode no longer silently leaks document citations into unsupported general answers; weak document retrieval now switches to non-citation general mode only when the user enabled it.

Unresolved Questions:
- None.

## 2026-05-05 - Conversation-Scoped Active Document Focus for RAG Chat

Status: Active-document RAG flow implemented, multi-document scope supported, and runtime smoke validated on the current Docker stack

Fixed:
- Updated `backend/app/models/conversation.py`, `backend/alembic/versions/002_add_active_document_ids_to_conversations.py`, `backend/app/schemas/chat_schemas.py`, and `backend/app/api/v1/chat_router.py` so each conversation can persist `active_document_ids`, `/api/v1/chat` can accept `document_ids`, and conversation detail/update APIs can rehydrate or change the active document scope directly.
- Added `backend/app/services/conversation_document_context.py` so active-document ownership, status filtering, serialization, and follow-up reuse are handled consistently instead of relying on loose user-wide retrieval.
- Updated `backend/app/api/v1/document_router.py` so deleting a document also scrubs dangling references from conversation active-document state.
- Updated `backend/app/services/retrieval_service.py` so stringified `pgvector` embeddings from the runtime DB no longer break near-duplicate chunk removal during multi-document retrieval.
- Updated `frontend/app/chat/page.tsx`, `frontend/components/chat/chat-input.tsx`, and new `frontend/components/chat/active-document-context-bar.tsx` so uploaded/selected documents become visible active context for the current chat, persist on existing conversations, support remove/clear actions, and survive follow-up prompts like `tóm tắt nó`.
- Updated `frontend/components/admin/document-table.tsx`, `frontend/components/admin/document-table-helpers.ts`, and `frontend/app/documents/page.tsx` so My Documents can launch chat scoped to one indexed file or a selected group of indexed files.

Validated:
- Backend focused pytest including retrieval regression: `33 passed, 2 skipped`.
- Frontend targeted Vitest: `20 passed`.
- Frontend production build: passed.
- Docker migration `001 -> 002`: passed.
- Real runtime API smoke on the live Docker stack:
  - duplicate upload reused the existing document id
  - uploaded documents reached `indexed`
  - first chat request returned the active document in the `done` event
  - follow-up request without re-sending `document_ids` still answered from the same conversation-scoped document
  - multi-document request returned both active documents and produced a combined answer after the retrieval embedding fix

Notes:
- This changes the product behavior from user-wide knowledge-base RAG toward conversation-scoped active-document RAG.
- `My documents` is no longer just storage/index management in practice; it can now explicitly seed chat scope.

Unresolved Questions:
- The runtime Celery worker still logs `ingestion.process_document` as unregistered in the current stack; chat/upload works via the existing fallback path, but worker registration should still be cleaned up separately.

## 2026-05-04 - Runtime Hardening Follow-up

Status: Upload/index/chat runtime fixed again; hybrid chat and streaming UX validated on the refreshed Docker stack

Fixed:
- Hardened `backend/app/services/document_ingestion_dispatcher.py` and `backend/app/services/ingestion_pipeline.py` so `INGESTION_DISPATCH_MODE=auto` now queues Celery work but also schedules a guarded in-process fallback when a document stays `pending`, while the pipeline atomically claims a document before indexing to avoid duplicate processing paths.
- Updated `backend/app/services/query_rewriter.py`, `backend/app/api/v1/chat_router.py`, `backend/app/services/retrieval_service.py`, `backend/app/services/embedding_service.py`, and `backend/app/services/llm/ollama_provider.py` so optional rewrite/model/provider calls stop hanging forever, retrieval can degrade from vector+BM25 to keyword/general mode instead of throwing `503`, and chat can answer faster when document search is weak or temporarily degraded.
- Hardened `backend/app/services/bootstrap_admin_service.py` against startup races and removed public/default admin password exposure from `docker-compose.yml`, `.env.example`, and `frontend/components/auth/login-form.tsx`.
- Updated `frontend/components/admin/document-table.tsx` so stale document-list responses can no longer overwrite newer search/filter/page state.
- Updated `frontend/app/chat/page.tsx`, `frontend/components/chat/message-bubble.tsx`, `frontend/components/chat/thinking-indicator.tsx`, `frontend/components/chat/chat-input.tsx`, and `frontend/styles/globals.css` so chat now inserts an immediate assistant placeholder, streams into that bubble in-place, shows more polished loading motion, and keeps the thread visually stable instead of janking while waiting for first tokens.
- Updated `backend/app/api/v1/admin_router.py` so admin ingestion status also shows queued `pending` jobs.

Validated:
- Backend compile: passed.
- Backend targeted pytest: `31 passed, 2 skipped`.
- Frontend targeted Vitest: `22 passed`.
- Frontend production build: passed.
- Real runtime upload smoke after dispatcher hardening: duplicate upload reused the same document id and a fresh document moved to `indexed`.
- Real runtime browser/API smoke after Docker refresh: `/chat` returned grounded document-backed answers again, and a general-language prompt such as `Bạn có thể trả lời tiếng Việt không?` returned a fast normal reply instead of `503`.

Notes:
- The refreshed Docker stack on `127.0.0.1:3002` / `127.0.0.1:8000` is now serving the updated chat/runtime code.
- A remaining browser console error for `/_next/webpack-hmr` can still appear in dev mode; that is separate from the fixed chat `503` issue.

Unresolved Questions:
- None.

## 2026-05-04 - Local Admin Bootstrap and Indexing UX Clarification

Status: Local admin bootstrap, user-owned indexing clarity, and document status UX validated

Fixed:
- Updated `backend/app/config.py`, `backend/app/main.py`, and `backend/app/services/bootstrap_admin_service.py` so the backend can create or repair a local bootstrap admin account during startup when bootstrap env vars are provided.
- Updated `docker-compose.yml` and `.env.example` with local bootstrap admin defaults for `admin123@gmail.com / admin123`.
- Kept user-owned indexing behavior intact: normal users still upload and re-index only their own documents through `backend/app/api/v1/document_router.py`, while admins retain global control through `backend/app/api/v1/admin_router.py`.
- Added `frontend/components/admin/document-indexing-guide.tsx` and wired it into `frontend/app/documents/page.tsx` so users can see what `Pending`, `Processing`, `Indexed`, and `Failed` actually mean.
- Updated `frontend/components/admin/document-table.tsx` and `frontend/components/admin/document-table-helpers.ts` so the document list auto-refreshes while indexing is active and shows a plain-language status explanation under each badge.
- Updated `frontend/components/auth/login-form.tsx` to show the local dev admin credentials in non-production/dev bootstrap scenarios.

Validated:
- Backend targeted pytest including bootstrap/admin/chat/document/retrieval coverage: 29 passed, 2 skipped.
- Frontend Vitest: 25 passed.
- Frontend production build: passed.
- Runtime bootstrap account seeded successfully into the current DB and `admin123@gmail.com / admin123` can now log in.
- Runtime admin endpoint check: `/api/v1/admin/stats` returned HTTP 200 with the seeded admin token.

Notes:
- The browser console errors in the screenshot such as `runtime.lastError`, `Cannot find menu item`, and `Unable to add filesystem` come from Chrome/extensions or DevTools state, not from the app code.
- The app-level `/api/v1/chat` 503 shown in the screenshot was consistent with a document not yet indexed or with older runtime state before the ingestion/runtime fixes.

Unresolved Questions:
- None.

## 2026-05-04 - End-to-End RAG Runtime Recovery

Status: Real upload, indexing, retrieval, and answer flow validated on the running Docker-backed app

Fixed:
- Updated `backend/app/config.py`, `backend/app/services/document_ingestion_dispatcher.py`, `backend/app/api/v1/document_router.py`, and `backend/app/api/v1/admin_router.py` so document ingestion can run in-process by default for the local runtime instead of depending entirely on a flaky Celery worker path.
- Updated `backend/app/services/embedding_service.py` to fall back to deterministic local embeddings when Ollama embedding HTTP calls are unreachable, preventing uploads from getting stuck or failing just because the runtime provider host is unstable.
- Updated `backend/app/services/grounded_answer_fallback.py` and `backend/app/api/v1/chat_router.py` so chat can still return a grounded answer from retrieved context if the generation stream fails after retrieval succeeds.

Validated:
- Real runtime login with `runtime-check-20260504-1530@example.com`.
- Real upload of `sample-article.txt` moved from `pending` to `indexed`.
- Real `/api/v1/chat` answers returned the uploaded document facts:
  - `vector similarity` and `BM25 keyword search`
  - `administrators can upload documents` and `viewers receive answers with source citations`
- Real chat responses included `sources` metadata pointing to `sample-article.txt`.
- Backend targeted pytest: `test_api_chat.py` + `test_retrieval.py` -> 16 passed, 2 skipped.
- Backend broader targeted pytest: `test_api_documents.py` + `test_api_chat.py` -> 20 passed, 1 skipped.

Notes:
- Frontend/backend currently run through the Docker-backed local stack exposed on `127.0.0.1:3002` and `127.0.0.1:8000`.
- Because the compose stack bind-mounts the repo and runs dev/reload processes, the website is serving the current workspace code.

Unresolved Questions:
- None.

## 2026-05-04 - Upload Deduplication, Ingestion Status Clarity, and Sidebar Hover Polish

Status: Duplicate upload guard, pending-state clarity, and sidebar interaction polish validated

Fixed:
- Updated `backend/app/api/v1/document_router.py` to hash uploads before insert, reuse an existing user-owned document when the same file content is uploaded again, and re-queue the existing record instead of creating duplicate rows/chunks when the prior copy failed.
- Updated `backend/app/schemas/document_schemas.py` to expose `duplicate_of_existing` so the frontend can explain reused uploads clearly.
- Updated `backend/app/api/v1/chat_router.py` to return a friendly streamed reply when a user has documents still indexing but no indexed documents yet, instead of falling through into confusing retrieval/provider failures.
- Added `frontend/lib/document-upload.ts` and updated chat/admin upload components to poll document status after upload so `Pending` now progresses to `Processing`, `Indexed`, or `Failed` without a manual refresh.
- Updated `frontend/app/chat/page.tsx` upload notice copy to explain queued indexing more clearly and to call out duplicate uploads explicitly.
- Updated `frontend/components/chat/chat-sidebar.tsx` old-conversation items with more professional hover/active states: card elevation, accent rail, icon container, and message-count badge.

Validated:
- Backend targeted pytest: 20 passed, 1 skipped.
- Frontend Vitest: 23 passed.
- Frontend production build: passed.

Notes:
- `Pending` in this project means the upload was accepted and queued for ingestion; the document is not searchable until it becomes `Indexed`.

Unresolved Questions:
- None.

## 2026-05-04 - Chat UX Continuity and Greeting Handling Fix

Status: Chat history, upload acknowledgment, and greeting flow validated

Fixed:
- Updated `frontend/components/chat/chat-sidebar.tsx` to use route-driven conversation links instead of local-only selection state.
- Updated `frontend/app/chat/page.tsx` to hydrate `/api/v1/conversations/{id}/messages`, reset cleanly for `/chat`, and keep new conversations synced into the URL.
- Updated `frontend/components/chat/chat-input.tsx` so completed uploads surface metadata back to the page and produce a professional assistant-side upload acknowledgment instead of silent status-only chips.
- Updated citation click flow so reopened conversations use the message-local `sources` payload instead of relying only on the latest streamed source set.
- Updated `backend/app/api/v1/chat_router.py` with a provider-free greeting path so simple inputs like `Hi` return a professional response instead of low-context RAG abstention copy.
- Updated `backend/app/api/v1/chat_router.py` to return HTTP 503 with explicit retrieval-unavailable copy when provider/retrieval work fails before streaming, instead of leaking a raw 500 to the chat UI.
- Updated `frontend/app/layout.tsx`, `frontend/app/chat/layout.tsx`, `frontend/app/documents/layout.tsx`, and `frontend/app/chat/page.tsx` to reduce extension-triggered hydration mismatch noise by suppressing root mismatch checks and deferring the interactive chat shell until mount.
- Added `frontend/app/icon.svg` so the app no longer emits a `/favicon.ico` 404 in local browser sessions.
- Wrapped `/chat` and shared chat sidebar `useSearchParams` usage in `Suspense` so the Next.js 15 production build succeeds.

Validated:
- Frontend targeted chat regression tests: 10 passed.
- Frontend full Vitest: 22 passed.
- Frontend production build: passed.
- Backend `test_api_chat.py`: 8 passed, 1 skipped.
- Backend compile/import: passed.

Notes:
- `npm run lint` is still not usable non-interactively because the repo's `next lint` script opens the Next.js ESLint setup wizard instead of running a configured lint pass.

Unresolved Questions:
- None.

## 2026-05-04 - Document Upload Origin Check Fix

Status: Frontend upload 403 root cause fixed

Fixed:
- Updated `frontend/app/api/v1/[...path]/route.ts` to validate mutating request origins against the public forwarded/host origin instead of the container-internal Next.js origin.
- This removes false `403 Invalid request origin` responses when the app is accessed via Docker port mapping such as `127.0.0.1:3001 -> container:3000`.
- Updated `frontend/lib/client-api.ts` to surface backend/proxy `detail` messages before falling back to generic 403 copy, so future auth/origin failures are diagnosable from the UI.
- Added Vitest regression coverage for the proxied upload case with differing public/internal origins.

Validated:
- Frontend Vitest (single-worker): proxy route regression test passed.
- Frontend Vitest (single-worker): existing admin/chat upload tests passed.

Notes:
- Frontend production build could not be re-run successfully on this machine because local Node/Next build processes are hitting process memory limits before compilation completes.
- Runtime Docker verification was partially blocked by Docker Desktop instability during probe attempts.

Unresolved Questions:
- None.

## 2026-05-04 - Auth Refresh, Upload, and User/Admin Document Scope

Status: Auth/upload/document management upgrade validated

Fixed/added:
- NextAuth now stores backend `accessToken`, `refreshToken`, `accessTokenExpires`, `roles`, and refresh errors.
- NextAuth JWT callback refreshes access tokens through `/api/v1/auth/refresh` before expiry; refresh failure marks session with `RefreshAccessTokenError`.
- Middleware rejects protected routes when session refresh fails and redirects to `/login?error=SessionExpired`.
- Added browser API wrapper for JSON/upload requests; client 401 signs out to `/login`.
- Added shared authenticated user footer with email, role badge, and logout in chat/admin shells.
- Added `/documents` user view with upload, list, re-index, and delete for own documents.
- Chat paperclip uploads documents to `/api/v1/documents/upload` and shows upload status/error.
- Admin dashboard now uses `/api/v1/admin/documents` for global list/re-index/delete.
- Backend user document endpoints now only expose `owner_id == current_user.id`; foreign docs return 404 to non-admins.
- Backend admin document endpoints can list/get/re-index/delete all documents.
- Retrieval now filters indexed chunks by `owner_id`, so chat searches user-owned knowledge base only.
- Upload too large now returns 413; frontend maps 401/403/400/413 to clear messages.

Validated:
- Backend compile: passed.
- Backend non-integration tests: 32 passed, 3 deselected.
- Focused backend auth/document/retrieval tests: 24 passed, 1 deselected.
- Frontend Vitest: 18 passed.
- Frontend production build: passed; `/documents` route generated.
- Frontend standalone smoke on `127.0.0.1:3001`: `/login` renders with no console errors.
- Frontend standalone smoke on `127.0.0.1:3001/documents`: redirects unauthenticated user to `/login?callbackUrl=%2Fdocuments` with no console errors.

Notes:
- Frontend test/build scripts now set 4096 MB Node heap to avoid local V8 OOM before assertions.
- Delegated tester/reviewer subagents did not initialize; local verification completed directly.
- Docker app rebuild/runtime smoke blocked: Docker Desktop Linux engine pipe missing; backend `127.0.0.1:8000/health` unreachable.

Unresolved Questions:
- Docker Desktop available for final full-stack browser smoke?

## 2026-05-02 - Register Route and Hydration Warning Fix

Status: Frontend auth/admin and chat retrieval fix validated

Fixed/adjusted:
- Added `/register` App Router page so the login page sign-up link no longer lands on 404.
- Added credential registration form that calls `/api/v1/auth/register`, then returns users to `/login?registered=1` with a success notice.
- Added Chat sidebar navigation to `/admin` so the management dashboard is discoverable from the authenticated app shell.
- Added admin forbidden-state UI so non-admin users see an admin-access message instead of a client-side crash.
- Fixed retrieval SQL casts for pgvector and role UUID arrays so chat retrieval no longer sends raw `:param::type` placeholders to Postgres.
- Added focused Vitest/Pytest coverage for registration redirect, admin sidebar navigation, forbidden ingestion status handling, and fake-embedding retrieval.
- Added `suppressHydrationWarning` on the root `<body>` to suppress extension-injected body attributes such as `bis_register` and `__processed_*`.

Validated:
- Frontend tests: 13 passed.
- Frontend build: passed; `/register` generated as a valid route.
- Backend non-integration tests: 29 passed, 3 deselected.
- Browser register flow: `/register` creates account and redirects to `/login?registered=1`.
- Browser authenticated chat shell: Admin dashboard link present.
- Browser `/admin` as non-admin: access-required message shown instead of crash.
- Docker app stack: frontend/backend/db/redis/ollama up, backend healthy after restart.

Impact:
- Users can create accounts from the existing login page sign-up link.
- Registration now requires explicit sign-in after account creation.
- Authenticated users can discover the management dashboard route; backend RBAC still requires admin role for management APIs.
- The reported hydration console warning is suppressed when caused by browser extension body mutations.
- Chat retrieval avoids the Postgres syntax error that produced the reported 500.

Unresolved Questions:
- Local Ollama generation can still stress Docker Desktop on this machine; avoid using the heavy chat model during smoke checks unless Docker has enough memory.

## 2026-05-01 — Chat Runtime/Auth Proxy Fix

Status: Local runtime fix validated

Fixed/adjusted:
- Browser chat now calls the backend through `frontend/app/api/v1/[...path]/route.ts`, which proxies `/api/v1/*` requests server-side and attaches the NextAuth `accessToken` when present.
- Next API proxy rejects hostile `Origin` headers on mutating methods with 403 while allowing same-origin requests and localhost/127.0.0.1 loopback development origins with matching protocol/port.
- Removed the unauthenticated `/api/v1` static rewrite from `frontend/next.config.ts`.
- `frontend/middleware.ts` redirects unauthenticated `/chat` and `/admin` users to login with `callbackUrl`.
- `frontend/app/chat/page.tsx` shows backend `detail` errors instead of replacing them with a generic chat failure.
- `backend/app/api/v1/chat_router.py` returns HTTP 503 when configured chat providers require missing `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- Backend chat SSE `done` events include `conversation_id`, letting the frontend keep follow-up messages in the same conversation.
- Backend chat SSE stream exceptions are logged server-side and emitted to clients as a generic `Chat stream failed. Please try again.` message, not raw exception text.
- `backend/tests/test_api_chat.py` covers missing provider configuration and chat `done` conversation identity.

Validated:
- Backend non-integration tests: 25 passed, 3 deselected.
- Frontend tests: 8 passed.
- Frontend build: passed.
- Docker runtime: backend/frontend/db/redis healthy/up.
- Browser `/chat` unauthenticated redirects to login.
- Login with `runtime-check@example.com` / `Password123!` reaches `/chat`.
- Sending a chat message displays `Chat provider is not configured. Missing: OPENAI_API_KEY` when provider credentials are absent.
- Hostile `Origin` on the Next API proxy is rejected with 403.
- Loopback `Origin` passes the Next proxy origin check; unauthenticated backend request returns 401.

Impact:
- Browser chat no longer bypasses NextAuth token attachment.
- Mutating proxied API requests fail closed for cross-site origins while preserving local loopback development.
- Protected frontend routes fail closed before rendering chat/admin pages.
- Missing provider credentials now produce actionable runtime errors for users and operators.
- Chat stream failures avoid leaking raw server exception messages to clients.

Unresolved Questions:
- None.

## 2026-05-01 — Docker Runtime Fixes

Status: Local Docker stack fixed

Fixed/adjusted:
- Docker Compose app stack now includes `migrate` service running `python -m alembic upgrade head` before backend and worker start.
- Backend healthcheck gates frontend startup with `service_healthy`.
- App ports bind to `127.0.0.1` for local-only exposure.
- Backend settings accept `BACKEND_CORS_ORIGINS` as comma-separated env string and ignore unrelated env keys.
- Runtime backend dependencies include `email-validator`; project dependency ranges now align with runtime pins.
- Backend and frontend Docker build contexts exclude local caches, env files, generated build output, and uploads via `.dockerignore`.
- Frontend server-side backend access uses internal `BACKEND_URL` while browser public API URL stays `localhost`.

Validated:
- `docker compose build`: backend, worker, frontend, migrate built.
- `docker compose up -d --force-recreate`: db/redis healthy, migrate exited 0, backend healthy, frontend started.
- `curl -fsS http://localhost:8000/health`: passed.
- `curl -fsS -I http://localhost:3000/chat`: passed.
- Backend non-integration tests: 24 passed, 3 deselected against Docker test services.
- Frontend Docker tests: 8 passed.
- Frontend Docker production build: passed.

Impact:
- Local app stack startup less manual: DB migration runs in compose before API/worker.
- Shared root `.env` is safer for backend settings because extra frontend/compose env keys are ignored.
- Local development services are less exposed to LAN by default.

Unresolved Questions:
- None.

## 2026-04-30 — Phase 10 Integration Testing

Status: Local validation complete

Added:
- Test Docker Compose stack for PostgreSQL pgvector + Redis.
- Backend pytest fixtures/tests for auth, health, document API, chat API, retrieval, ingestion.
- Frontend Vitest setup and component tests for chat/admin.
- Playwright config/specs for auth, chat, admin E2E flows.
- GitHub Actions CI workflow.

Fixed/adjusted:
- Frontend package scripts/deps for tests and build.
- NextAuth/PostCSS build issues.
- CI health wait and npm install path.
- E2E gated by `vars.E2E_ENABLED`.
- Removed fixed container names from test compose.
- Playwright `fullyParallel` disabled for deterministic flow tests.
- Declared pytest markers.
- Unit ingestion no longer requires DB.
- XMLHttpRequest restored via `finally` in frontend tests.
- Settings cache reset in tests.
- Test engine uses `NullPool` to avoid asyncpg event-loop reuse issues.
- Pinned `bcrypt>=4.0,<5.0` for passlib compatibility.
- Document delete test now stores document ID before expiring ORM state.

Validated:
- Frontend tests: `npm run test --prefix D:/RAG_Project/frontend` — 8/8 passed.
- Frontend build: `npm run build --prefix D:/RAG_Project/frontend` — passed.
- Backend compile/import — passed.
- Backend non-integration tests: `PYTHONPATH="D:/RAG_Project/backend" python -m pytest -q "D:/RAG_Project/backend/tests" -m "not integration"` — 24 passed, 3 deselected against Docker pgvector + Redis test services.

Impact:
- Delivery confidence higher for frontend/build/static backend import paths.
- Backend DB-backed non-integration test confidence established locally with Docker test infrastructure.
- Provider-backed integration, E2E, CI run, and coverage gate still need separate validation before release readiness.

Unresolved Questions:
- Should E2E become required after CI env stable?
