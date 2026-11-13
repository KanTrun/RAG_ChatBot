# RAG ChatBot — Hệ thống Hỏi Đáp Tài Liệu Nội Bộ (Local-First Hybrid RAG)

Hệ thống RAG Chatbot hoàn chỉnh chạy độc lập (local-first) với **FastAPI**, **PostgreSQL + pgvector**, **Celery + Redis**, **Ollama (`mxbai-embed-large` + `qwen2.5:7b`)** và **Next.js 15 + React 19**. Hệ thống hỗ trợ trích xuất cấu trúc tài liệu đa định dạng (`.pdf`, `.docx`, `.txt`, `.md`, `.html`), tìm kiếm lai song ngữ Anh–Việt (BM25 + Vector hợp nhất bằng Reciprocal Rank Fusion), trả lời đúng ngôn ngữ người hỏi kèm trích dẫn nguồn `[1], [2]` có hậu kiểm, cơ chế từ chối nhanh khi thiếu bằng chứng (`strict_documents`), phòng chống Prompt Injection từ tài liệu, giao diện Dark/Light mượt mà và bộ công cụ đánh giá chất lượng trên **112 cặp hỏi đáp chuẩn trải đều 12 cấp độ (`L1`–`L12`)**.

---

## 1. Sơ đồ kiến trúc hệ thống

```text
+-----------------------------------------------------------------------------------+
|                        Frontend (Next.js 15 + React 19, Port 3000)                |
|  - Chat SSE Streaming theo giai đoạn (retrieving -> generating -> chunk -> done)  |
|  - Menu 3 chấm Portal (z-50, auto-flip, phím mũi tên/Escape), Dark/Light Theme    |
|  - Trích dẫn [n] có Hover Preview + Drawer Nguồn tự cuộn, Copy Code Block         |
|  - Thanh tài liệu thu gọn (tối đa 2 chip + Popover "+N more")                     |
|  - Quản lý Tài liệu (Tiến độ stage thật, Bulk Re-index/Delete, Chunks Inspector)  |
|  - Admin Dashboard (Users/RBAC, System Stats, Biểu đồ Lịch sử Đánh giá RAG)       |
+-----------------------------------------+-----------------------------------------+
                                          | HTTP / SSE (/api/v1/*)
                                          v
+-----------------------------------------------------------------------------------+
|                        Backend API (FastAPI Async, Port 8000)                     |
|  - Auth JWT + RBAC (admin / editor / viewer) + Sliding-Window Rate Limiter        |
|  - Startup Check & Model Warmup + Celery Live Ping (/health inspect().ping())     |
|  - Conditional QueryRewriter -> Intent Classifier -> Parallel Hybrid Retrieval    |
|  - Prompt Guard (<retrieved_context> + sanitize_context_chunks)                   |
|  - Output Validator (validate_and_clean_citations: loại bỏ [n] vượt phạm vi)      |
+------------+----------------------------+----------------------------+------------+
             |                            |                            |
             v                            v                            v
+-------------------------+  +-------------------------+  +-------------------------+
| PostgreSQL 16 + pgvector|  |   Redis 7 + Celery      |  |  Ollama Local Server    |
|       (Port 5432)       |  |      (Port 6379)        |  |      (Port 11434)       |
| - Bảng document_chunks  |  | - Queue tác vụ bất đồng |  | - Embedding:            |
| - Vector(1024) HNSW idx |  |   bộ: ingestion.        |  |   mxbai-embed-large     |
|   (ef_search = 64)      |  |   process_document      |  |   (batch=32, Sem=4,     |
| - TSVECTOR GIN index +  |  | - Live Worker Ping      |  |   LRU cache 512/1800s)  |
|   BM25 tiếng Việt       |  |                         |  | - LLM: qwen2.5:7b       |
+-------------------------+  +-------------------------+  +-------------------------+
```

---

## 2. Cách chạy hệ thống từ bản clone mới

### Bước 1: Chuẩn bị file môi trường `.env`
Từ thư mục gốc của dự án (`D:\RAG_Project`), sao chép file `.env.example` sang `.env`:

```powershell
cp .env.example .env
```

> Lưu ý: `BACKEND_CORS_ORIGINS` hỗ trợ cả định dạng mảng JSON (`["http://localhost:3000","http://127.0.0.1:3000"]`) lẫn chuỗi phân tách bằng dấu phẩy.

### Bước 2: Khởi động toàn bộ 7 service bằng một lệnh Docker Compose

```powershell
docker compose up -d --build
```

### Bước 3: Tải (pull) 2 model bắt buộc vào container Ollama

```powershell
docker exec -it rag-ollama ollama pull mxbai-embed-large
docker exec -it rag-ollama ollama pull qwen2.5:7b
```

### Bước 4: Kiểm tra trạng thái hệ thống (`/health`)

```powershell
curl http://127.0.0.1:8000/health
```

Truy cập giao diện web tại: **`http://localhost:3000`** (Tài khoản Admin mặc định khởi tạo từ `.env`: `admin@example.com` / `AdminPassword123!`).

---

## 3. Các biến `.env` quan trọng

| Biến môi trường | Giá trị mặc định | Mô tả |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://rag:rag@localhost:5432/ragdb` | Kết nối async PostgreSQL cho FastAPI và Celery worker |
| `REDIS_URL` | `redis://localhost:6379/0` | Kết nối Redis cho Celery broker/backend |
| `EMBEDDING_PROVIDER` | `ollama` | Nhà cung cấp vector embedding (`ollama`, `bge-m3`, `openai`) |
| `OLLAMA_EMBEDDING_MODEL` | `mxbai-embed-large` | Model embedding 1024 chiều khớp với cột `Vector(1024)` |
| `LLM_PROVIDER` / `LLM_MODEL` | `ollama` / `qwen2.5:7b` | Nhà cung cấp và model sinh câu trả lời trên Ollama |
| `OLLAMA_KEEP_ALIVE` | `30m` | Thời gian giữ model trong RAM sau mỗi lần gọi |
| `EMBEDDING_BATCH_SIZE` / `EMBEDDING_CONCURRENCY` | `32` / `4` | Kích thước batch và số luồng đồng thời khi gọi `/api/embed` |
| `HNSW_EF_SEARCH` | `64` | Tham số `hnsw.ef_search` cho truy vấn pgvector |
| `FAST_MODE` | `false` | Bật chế độ tối ưu tốc độ trên CPU (bỏ qua LLM rewrite và secondary parent rerank) |
| `RERANKER_PROVIDER` | `none` | Dùng bộ xếp hạng từ vựng/cấu trúc nhanh mặc định (hoặc `cohere` khi có API key) |
| `FIRST_TOKEN_TIMEOUT_SECONDS` | `120` | Thời gian chờ tối đa (giây) cho token đầu tiên khi chạy trên CPU |

---

## 4. Đo Hiệu năng (Before/After) & Đánh giá Chất lượng 112 Câu hỏi (`L1`–`L12`)

### 4.1. Chạy bộ đo hiệu năng Ingestion & Chat (`benchmark_rag.py`)

```powershell
# Đo baseline và lưu docs/PERF_BASELINE.md:
docker compose exec backend python scripts/benchmark_rag.py --mode baseline --runs 5

# Đo sau tối ưu và lưu app/evaluation/benchmark_optimized.json:
docker compose exec backend python scripts/benchmark_rag.py --mode optimized --runs 5
```

Xem báo cáo đầy đủ tại:
- `docs/PERF_BASELINE.md` (Số đo Baseline & Top 5 nút thắt)
- `docs/PERFORMANCE_REPORT.md` (Bảng so sánh Trước vs. Sau, đối chứng `mxbai-embed-large` vs. `bge-m3`, và kết quả 12 cấp độ `L1`–`L12`).

### 4.2. Chạy đánh giá chất lượng trên 112 câu hỏi vàng (`L1`–`L12`)

```powershell
docker compose exec backend python scripts/run_evaluation.py --compare-bm25
```

| Chế độ Truy xuất (112 câu hỏi L1–L12) | Faithfulness | Context Precision | Context Recall | Latency p50 / p95 | Avg Tokens / Answer |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Vector-Only (`ENABLE_BM25=false`)** | `0.9893` (98.9%) | `0.8221` (82.2%) | `0.9234` (92.3%) | `1.59 ms` / `1.92 ms` | `113.6` |
| **Hybrid RRF (`ENABLE_BM25=true`)** | **`0.9982` (99.8%)** | `0.8092` (80.9%) | **`0.9676` (96.8%)** | `2.23 ms` / `2.94 ms` | `117.5` |

---

## 5. Quy tắc An toàn Database & Cách chạy Kiểm thử (Tests)

> **CẢNH BÁO AN TOÀN BẮT BUỘC**: Tuyệt đối **KHÔNG** chạy `pytest` trực tiếp bên trong container `rag-backend` đang kết nối tới database thật (`ragdb`). `backend/tests/conftest.py` đã có chốt chặn tự động dừng (`pytest.exit(..., returncode=1)`) nếu `DATABASE_URL` không chứa `"rag_test"`.

```powershell
# 1. Sao lưu database thật trước khi chạy migration:
bash scripts/backup_db.sh

# 2. Chạy pytest AN TOÀN trên stack test độc lập (rag_test):
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit

# 3. Chạy script kiểm tra nghiệm thu toàn diện Phase 0-4:
docker compose exec backend python scripts/verify_acceptance.py

# 4. Chạy unit tests frontend (Vitest):
cd frontend
npm test -- --run
```
