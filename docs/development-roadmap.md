# Development Roadmap

## Status Snapshot

| Phase | Status | Evidence |
|---|---|---|
| Phase 1: Project Setup & Infrastructure | Complete | Project scaffold, Docker, backend/frontend baseline present |
| Phase 2: Database Schema & Models | Complete | Backend models/migrations present |
| Phase 3: Document Ingestion Pipeline | Complete | Ingestion services/tests present; structure-aware block-first chunking, contextualized embeddings, and ingestion-version metadata added |
| Phase 4: RAG Retrieval Engine | Complete | Retrieval services/tests present; strict intent-aware profiles, section-aware boilerplate suppression, evidence clustering, summary evidence briefs, and richer source metadata added |
| Phase 5: Backend API Layer | Complete | Auth, health, document, chat APIs present; chat now defaults to strict document grounding |
| Phase 6: Authentication & Security | Complete | NextAuth/JWT/RBAC paths present; premium login/register shell and theme toggle shipped |
| Phase 7: Frontend Chat Interface | Complete | Chat UI, active-document context bar, strict/hybrid mode toggle, chat document upload, My documents scoped-chat launch, and tests present |
| Phase 8: Admin Dashboard | Complete | Admin UI uses admin-scoped global document APIs and tests present |
| Phase 9: Observability & Evaluation | Complete | Evaluation/observability code present |
| Phase 10: Integration Testing | Local validation complete | Test infra, CI config, frontend tests/build, backend non-integration pytest, Docker app runtime fixes, chat auth proxy origin protection, token refresh handling, user/admin document scoping, safe SSE errors, conversation continuity, and browser runtime checks validated; provider-backed integration, E2E, CI run, and coverage gate remain unverified |

## Phase 10 Completion

Completed:
- `docker-compose.test.yml` for PostgreSQL pgvector + Redis test services.
- Main `docker-compose.yml` runtime fixes: migration service before backend/worker, backend healthcheck, frontend waits for healthy backend, localhost-only exposed ports, compose CORS env as string, backend/worker Redis/DB dependencies.
- Docker local startup follow-up: raw `docker compose up` now falls back to Docker-assigned host ports when defaults are occupied, while `docker-up.ps1` and `make up` keep preferring stable local ports and emit compose-only frontend origin/public URL overrides.
- Backend pytest fixtures/tests under `backend/tests`: auth, health, documents, chat, retrieval, ingestion, fixtures.
- Frontend Vitest config/setup/tests: chat and admin coverage.
- Playwright config/specs for auth/chat/admin E2E.
- GitHub Actions CI workflow.
- Frontend package scripts/deps and NextAuth/PostCSS build fixes.
- Backend runtime dependency and build context fixes: `email-validator`, backend/frontend `.dockerignore`.
- Chat runtime/auth proxy fixes: Next route proxy for `/api/v1/*` with NextAuth `accessToken`, mutating-method same-origin protection with localhost/127.0.0.1 loopback dev support, no unauthenticated static rewrite, middleware protection for `/chat` and `/admin`, detailed chat provider-config errors, generic SSE stream failure messages, and `conversation_id` in chat `done` events.

Validated:
- `npm run test --prefix D:/RAG_Project/frontend`: 8/8 passed.
- `npm run build --prefix D:/RAG_Project/frontend`: passed.
- Backend compile/import: passed.
- `PYTHONPATH="D:/RAG_Project/backend" python -m pytest -q "D:/RAG_Project/backend/tests" -m "not integration"`: 24 passed, 3 deselected against Docker pgvector + Redis test services.
- `docker compose build`: backend, worker, frontend, migrate built.
- `docker compose up -d --force-recreate`: db/redis healthy, migrate exited 0, backend healthy, frontend started.
- `curl -fsS http://localhost:8000/health`: passed.
- `curl -fsS -I http://localhost:3000/chat`: passed.
- Backend non-integration tests after chat provider-config coverage: 25 passed, 3 deselected.
- Frontend tests after chat proxy/runtime fix: 8 passed.
- Frontend build after chat proxy/runtime fix: passed.
- Frontend tests after register/admin route fix: 13 passed.
- Frontend build after register route fix: passed; `/register` generated as a valid route.
- Backend non-integration tests after retrieval SQL fix: 29 passed, 3 deselected.
- Browser register/admin smoke check: `/register` redirects to `/login?registered=1`; authenticated chat shell shows Admin dashboard; non-admin `/admin` shows access-required state.
- Docker runtime after chat proxy/runtime fix: backend/frontend/db/redis healthy/up; unauthenticated `/chat` redirects to login; login with `runtime-check@example.com` / `Password123!` reaches `/chat`; sending chat displays `Chat provider is not configured. Missing: OPENAI_API_KEY`; hostile `Origin` is rejected with 403; loopback `Origin` passes proxy origin protection and unauthenticated backend request receives 401.
- Auth/upload/scope upgrade: backend non-integration tests 32 passed, 3 deselected; focused auth/document/retrieval tests 24 passed, 1 deselected; frontend Vitest 18 passed; frontend build passed and generated `/documents`.
- Frontend standalone route smoke after auth/upload/scope upgrade: `/login` renders and `/documents` redirects unauthenticated to login on `127.0.0.1:3001`, no console errors.
- Chat UX continuity fix: targeted chat regression tests 10 passed; full frontend Vitest 22 passed; frontend production build passed; backend `test_api_chat.py` 7 passed, 1 skipped; chat history selection, upload acknowledgment, and greeting handling validated.
- Hydration/retrieval availability follow-up: browser chat console at `localhost:3002` no longer shows hydration mismatch or favicon errors; frontend production build passed; backend `test_api_chat.py` now 8 passed, 1 skipped; retrieval/provider failures now surface HTTP 503 instead of raw 500.
- Upload deduplication and status-follow-up pass: backend targeted pytest 20 passed, 1 skipped; frontend Vitest 23 passed; frontend production build passed; duplicate uploads now reuse the existing document, pending uploads self-refresh to terminal status, and chat/sidebar UX copy/states are clearer.
- End-to-end RAG runtime recovery: real Docker-backed app login/upload/index/chat flow now works; `sample-article.txt` indexed successfully, chat returned source-backed answers from the uploaded document, and backend fallback paths now cover flaky ingestion/generation provider runtime failures.
- Runtime hardening follow-up: upload deduplication still reuses the same document id, a fresh runtime upload reaches `indexed`, hybrid chat now degrades gracefully instead of surfacing retrieval `503`, the polished in-thread loading UI shipped, frontend targeted tests/build still pass, and refreshed Docker runtime verification shows `/chat` answering from documents again.
- Conversation-scoped active-document RAG: backend chat/conversation APIs now persist active document ids, My Documents can open chat with one or more indexed files, follow-up prompts stay tied to the active scope, and real Docker-backed API smoke validated duplicate upload reuse, single-document follow-up grounding, and multi-document answers after the pgvector embedding-dedup fix.
- Strict grounded RAG mode: chat now defaults to `strict_documents`, hybrid general knowledge is explicit, summary/compare retrieval uses intent-aware tuning, parser metadata preserves section context better, backend targeted pytest passed `26 passed, 2 skipped`, frontend chat Vitest passed `14 passed`, and frontend production build passed.
- Evidence-aligned RAG follow-up: source panel scroll behavior fixed, evidence snippets added, retrieval now keeps the original user question as the primary anchor with rewritten query as auxiliary recall, fallback reranking behaves better when the cross-encoder is disabled, backend targeted pytest passed `29 passed, 2 skipped`, frontend chat Vitest passed `16 passed`, frontend build passed, and the Docker app stack was refreshed successfully.
- Section-aware grounding follow-up: retrieval now classifies likely acknowledgement/reference/TOC/cover/caption chunks and demotes them for normal questions, summary mode no longer uses ordered first-chunk scanning, grounded fallback answers are more natural, backend targeted pytest passed `33 passed, 2 skipped`, frontend chat Vitest passed `16 passed`, frontend build passed, and backend/frontend Docker runtime rebuild plus health checks passed.
- Section-aware runtime smoke: a fresh uploaded document containing both `Acknowledgement` and substantive retrieval content indexed successfully, and strict chat answered from the retrieval body instead of the acknowledgement section.
- Document-first structure-aware retrieval upgrade: ingestion now emits structural chunk metadata and contextualized embeddings, summary retrieval now selects evidence by coverage-aware clusters and generates an explicit evidence brief before answer generation, backend targeted pytest passed `20 passed, 2 skipped`, backend chat API pytest passed `19 passed, 1 skipped`, and frontend chat Vitest passed `16 passed`.

## Risks

| Risk | Status | Owner | Unblock path |
|---|---|---|---|
| E2E requires full stack/env vars | Open | Main agent | Enable the CI E2E gate and required test credentials/services in CI/staging |
| CI first-run drift from local | Open | Main agent | Run workflow on PR, address service timing/env issues |
| Celery worker task registration drift in current Docker stack | Open | Main agent | Register/import `ingestion.process_document` correctly or rely on a deliberate non-Celery ingestion path instead of noisy worker failures |
| Local Ollama model calls can destabilize Docker Desktop | Open | Main agent | Increase Docker memory or switch compose to a smaller model before repeated chat smoke tests |
| Frontend Vitest can OOM under default Node heap locally | Mitigated | Main agent | Frontend test/build scripts now run Node with 4096 MB heap |
| Docker Desktop not reachable during 2026-05-04 runtime smoke | Open | Main agent | Start Docker Desktop, then run `docker compose build` and full login/upload/admin browser smoke |
| Dev-mode HMR websocket console noise on frontend | Open | Main agent | Switch local frontend runtime to a cleaner prod-like mode if the team wants zero dev-console noise |

## Next Actions

| Action | Owner | Done when |
|---|---|---|
| Complete implementation plan cleanup | Complete | Plan statuses and docs match actual local validation state |
| Run browser/API smoke for auth/upload/admin/chat scope after Docker rebuild | Complete | Upload/index, duplicate reuse, single-document follow-up grounding, and multi-document answer verified on the refreshed runtime |
| Run provider-backed integration tests | Main agent | Ingestion/retrieval/chat integration tests pass with configured provider credentials |
| Run CI on PR/main | Main agent | Workflow green or failures logged with fixes |

## Unresolved Questions

- Should E2E stay opt-in only, or become required on main once env stable?
- Keep local frontend in `next dev`, or switch Docker frontend to a production-style `next start` flow for cleaner console/runtime behavior?
