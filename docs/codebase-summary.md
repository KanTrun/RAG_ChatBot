# Codebase Summary

## Current State

RAG chatbot scaffold includes backend, frontend, Docker infrastructure, docs, and CI/test coverage. Local Docker runtime, chat auth/runtime behavior, active-document conversation focus, strict document-only default mode, evidence-aligned retrieval, and explicit hybrid follow-up behavior have been validated.

## Main Areas

| Area | Path | Status |
|---|---|---|
| Backend API | `D:/RAG_Project/backend` | Implemented; chat API supports conversation-scoped active document ids, strict document-only default mode, explicit hybrid mode, original-query-anchored retrieval, and evidence snippets in source payloads |
| Backend tests | `D:/RAG_Project/backend/tests` | Implemented; latest focused chat/retrieval pytest passed: 29 passed, 2 skipped |
| Frontend app | `D:/RAG_Project/frontend` | Implemented; build passed; `/register` and `/documents` routes present; `/login` and `/register` now use a premium two-panel auth shell with theme toggle; `/chat` reloads saved conversations, hydrates active document scope, exposes strict-vs-hybrid response mode clearly, and renders scrollable evidence snippets in the Sources panel |
| Frontend tests | `D:/RAG_Project/frontend/__tests__` | Implemented; latest targeted chat Vitest passed: 16/16 |
| E2E tests | `D:/RAG_Project/frontend/e2e` | Implemented; gated by env |
| Test services | `D:/RAG_Project/docker-compose.test.yml` | Implemented |
| Runtime stack | `D:/RAG_Project/docker-compose.yml` | Validated locally: backend/frontend/db/redis healthy/up |
| CI | `D:/RAG_Project/.github/workflows/ci.yml` | Implemented; needs PR/main run validation |

## Auth and Chat Runtime Flow

- Browser chat sends requests to `/api/v1/chat` through the shared client wrapper.
- `frontend/app/api/v1/[...path]/route.ts` proxies `/api/v1/*` to the configured backend URL and attaches `Authorization: Bearer <accessToken>` when a NextAuth session contains `accessToken`.
- `frontend/lib/auth.ts` stores backend access/refresh tokens, access expiry, roles, and refresh errors in NextAuth JWT/session state.
- NextAuth refreshes access tokens through `/api/v1/auth/refresh`; refresh failure sets `RefreshAccessTokenError`.
- `frontend/middleware.ts` protects `/chat`, `/documents`, and `/admin`, including redirect on refresh error.
- `frontend/lib/client-api.ts` handles browser JSON/upload requests, maps common upload/auth/permission errors, and signs out on 401.
- The Next API proxy protects mutating methods with origin checks: same-origin is allowed, localhost/127.0.0.1 loopback origins are allowed for matching protocol/port development flows, and hostile origins return 403.
- `frontend/next.config.ts` has no `/api/v1` rewrite, avoiding unauthenticated static proxying.
- `frontend/components/chat/chat-sidebar.tsx` exposes Chat, My documents, and Admin dashboard navigation in the authenticated shell; Admin link is role-gated; conversation items are route-driven links.
- Authenticated shells show user email, role badge, and logout.
- `/documents` is the user-owned document management view.
- `/register` posts to the backend register endpoint, then returns users to `/login?registered=1` for explicit sign-in.
- `frontend/app/(auth)` now uses the premium dark-first auth shell defined in `frontend/styles/globals.css`, including the hero panel, trust chips, social buttons, and refined credential forms.
- `/admin` shows an access-required state for authenticated non-admin users instead of crashing on 403 responses.
- `/admin` uses `/api/v1/admin/documents`, `/api/v1/admin/stats`, and `/api/v1/admin/ingestion-status` for global system data.
- `frontend/app/chat/page.tsx` displays backend `detail` errors when available, keeps the active `conversation_id` from chat `done` events for follow-up messages, and reloads saved messages from `/api/v1/conversations/{id}/messages` when a conversation is selected from the sidebar.
- `backend/app/api/v1/chat_router.py` now persists `active_document_ids` per conversation, exposes `GET /api/v1/conversations/{id}` and `PATCH /api/v1/conversations/{id}`, and filters retrieval to the active document set when present.
- `backend/app/api/v1/chat_router.py` now also enforces `strict_documents` as the default response mode, returns an abstention when support is weak, and only enables outside knowledge through explicit `hybrid_general`.
- `backend/app/api/v1/chat_router.py` now keeps the original user question as the primary retrieval query, passes rewritten query only as auxiliary recall, emits source excerpts, and uses a larger structured-answer generation config for grounded replies.
- `frontend/app/chat/page.tsx` hydrates active documents from either conversation metadata or `documentIds` query params, keeps that scope visible through `ActiveDocumentContextBar`, and syncs scoped-document changes back to the backend in sequence to avoid stale overwrite races.
- `frontend/app/chat/page.tsx` and `frontend/components/chat/chat-input.tsx` expose a visible mode switch so users can tell whether chat is document-only or allowed to use outside knowledge.
- `frontend/components/chat/sources-panel.tsx` now scrolls correctly and shows section/page plus evidence snippets so users can inspect why a grounded answer was produced.
- `frontend/app/chat/page.tsx` and the authenticated chat/documents layouts intentionally defer their full interactive shells until mount, reducing hydration mismatch noise when browser extensions mutate server HTML before React hydrates.
- Chat paperclip uploads documents to `/api/v1/documents/upload`, shows pending/processing/indexed/failed state, appends a professional assistant acknowledgment, and makes the uploaded or duplicate-reused document active for the current chat scope.
- `frontend/app/documents/page.tsx` and `frontend/components/admin/document-table.tsx` can start chat scoped to one indexed document or a selected set of indexed documents.
- `backend/app/api/v1/document_router.py` is user-scoped: list/get/delete/reindex operate only on documents owned by current user.
- `backend/app/api/v1/admin_router.py` has admin-only global document list/get/delete/reindex endpoints.
- `backend/app/services/retrieval_service.py` filters retrieval candidates by `documents.owner_id`, keeping chat knowledge base user-scoped.
- `backend/app/services/retrieval_service.py` uses SQLAlchemy-safe `CAST(:param AS ...)` syntax for pgvector and UUID array binds.
- `backend/app/api/v1/chat_router.py` checks configured chat providers before streaming and returns HTTP 503 with missing env keys when required provider credentials are absent for document-backed questions.
- `backend/app/api/v1/chat_router.py` short-circuits greeting-only messages like `Hi` with a professional canned response before provider/retrieval work.
- `backend/app/api/v1/chat_router.py` returns HTTP 503 with a user-facing retrieval-unavailable message when embedding/retrieval dependencies fail before SSE streaming starts.
- Backend chat SSE logs stream exceptions server-side and sends a generic stream failure event to clients instead of raw exception text.
- Backend chat SSE `done` events include `conversation_id`.
- Backend chat SSE `done` events also include the authoritative `active_documents` payload used by the frontend to keep conversation scope consistent.
- `backend/app/services/retrieval_service.py` now normalizes both list and stringified pgvector embeddings during deduplication so runtime multi-document retrieval does not silently fall back to general chat.
- `backend/app/services/retrieval_intent_service.py` now classifies summary/compare/extract/question queries into retrieval plans, and parser metadata now preserves more section structure for `pdf`, `html`, `txt`, and `md`.
- `backend/app/services/reranking_service.py` now falls back to lexical question-aware ranking when the cross-encoder reranker is disabled, which matters in the current default config where `reranker_provider=none`.

## Phase 10 Test Coverage Added

Backend:
- Auth tests.
- Health tests.
- Document API tests.
- Chat API tests, including missing provider configuration.
- Retrieval tests.
- Ingestion tests and fixtures.

Frontend:
- Chat component tests.
- Admin component tests.
- Client API 401/sign-out test.
- Vitest config/setup.

E2E:
- Auth flow.
- Chat flow.
- Admin flow.
- Playwright config.

## Validation Status

Passed:
- Focused backend chat/retrieval tests after evidence-alignment follow-up: 29 passed, 2 skipped.
- Focused frontend chat tests after evidence/source UX follow-up: 16 passed.
- Frontend production build after evidence/source UX follow-up: passed.
- Docker migration `001 -> 002` applied successfully.
- Real runtime API smoke on the active Docker stack validated:
  - duplicate upload reused the same document id
  - upload -> indexed -> chat with active document worked
  - follow-up `tóm tắt nó` without re-sending `document_ids` stayed grounded to the same conversation-scoped document
  - multi-document scoped chat returned both active documents and produced a combined answer
- Backend non-integration tests: 32 passed, 3 deselected.
- Focused backend auth/document/retrieval tests: 24 passed, 1 deselected.
- Frontend Vitest after chat UX continuity fix: 22/22.
- Frontend build.
- `/documents` page builds and is protected by middleware.
- Standalone frontend smoke on `127.0.0.1:3001`: `/login` renders and `/documents` redirects unauthenticated to login with no console errors.
- Docker runtime: backend/frontend/db/redis healthy/up.
- Unauthenticated `/chat` redirects to login.
- Browser login with `runtime-check@example.com` / `Password123!` reaches `/chat`.
- Sending a chat message displays `Chat provider is not configured. Missing: OPENAI_API_KEY` when OpenAI is configured without a key.
- Hostile `Origin` on the Next API proxy returns 403.
- Loopback `Origin` passes the Next proxy origin check and unauthenticated backend request receives 401.
- `/register` page builds and posts registration through the authenticated API proxy path, then redirects to login.
- `/admin` as a non-admin displays an access-required message instead of a client-side exception.
- Chat history selection reloads saved messages, upload acknowledgment appears in-thread, and greeting-only chat requests return professional copy.
- Browser smoke on `localhost:3002/chat` after the latest fixes showed no console hydration warnings or favicon errors; a document-backed query now surfaces HTTP 503 with `Chat retrieval is temporarily unavailable. Please try again in a moment.` instead of a raw 500.

Pending:
- Provider-backed integration tests with real provider credentials.
- Full CI workflow run.
- E2E run with enabled vars and full stack.

## Current Blockers

| Blocker | Impact | Owner | Next step |
|---|---|---|---|
| Provider credentials absent in local runtime | Real chat streaming cannot be fully validated | Main agent | Set required `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, then run provider-backed integration tests |
| Local Ollama generation can stress Docker Desktop | Docker containers may exit during heavy model calls | Main agent | Allocate more Docker memory or use a smaller/local-ready Ollama model before chat-generation smoke tests |
| Celery worker currently logs `ingestion.process_document` as unregistered in the live Docker stack | Upload/index still works through the existing fallback path, but worker noise indicates dispatch/runtime drift | Main agent | Align Celery task registration/imports or simplify to one deliberate ingestion path |
| Frontend Vitest default heap OOM locally | Plain Vitest can fail before assertions | Main agent | Mitigated in frontend package scripts with 4096 MB Node heap |
| Docker Desktop unavailable on 2026-05-04 | Full-stack rebuild/runtime smoke blocked | Main agent | Start Docker Desktop; backend `127.0.0.1:8000/health` must respond before login/upload/admin browser checks |
| E2E gated by env | Browser flows not always run | Main agent | Enable `vars.E2E_ENABLED` when env ready |
| CI first-run state unknown | Release confidence depends on workflow result | Main agent | Run workflow on PR/main and fix drift |

## Unresolved Questions

- CI secrets/test vars ready?
- Docker Desktop available for final full-stack smoke?
