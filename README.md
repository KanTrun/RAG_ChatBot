# RAG ChatBot — Hệ thống Hỏi Đáp Tài Liệu Nội Bộ (Local-First Hybrid RAG)

Hệ thống RAG Chatbot hoàn chỉnh chạy độc lập (local-first) với **FastAPI**, **PostgreSQL + pgvector**, **Celery + Redis**, **Ollama (`mxbai-embed-large` + `qwen2.5:7b`)** và **Next.js 15 + React 19**. Hệ thống hỗ trợ trích xuất cấu trúc tài liệu đa định dạng, tìm kiếm lai (BM25 + Vector kết hợp bằng Reciprocal Rank Fusion), trả lời kèm trích dẫn nguồn bấm được `[1], [2]`, cơ chế từ chối khi thiếu bằng chứng (`strict_documents`), bảng chẩn đoán độ trễ/token từng bước và bộ công cụ đánh giá chất lượng trên 52 cặp hỏi đáp chuẩn.

---

## 1. Sơ đồ kiến trúc hệ thống

```text
+-----------------------------------------------------------------------------------+
|                        Frontend (Next.js 15 + React 19, Port 3000)                |
|  - Chat SSE Streaming + Nút dừng sinh (Stop) + Chế độ Document Only / Hybrid      |
|  - Trích dẫn tương tác [1],[2] + Panel Chẩn đoán (Intent, BM25, Latency, Tokens)  |
|  - Quản lý Tài liệu (Kéo thả đa file, Cấu hình Chunk 512/51, Chunks Inspector)    |
|  - Admin Dashboard (Quản lý Users/RBAC, System Stats, Lịch sử Đánh giá Chất lượng)|
+-----------------------------------------+-----------------------------------------+
                                          | HTTP / SSE (/api/v1/*)
                                          v
+-----------------------------------------------------------------------------------+
|                        Backend API (FastAPI Async, Port 8000)                     |
|  - Auth JWT + RBAC (admin / editor / viewer) + Sliding-Window Rate Limiter        |
|  - Startup Check & Model Warmup (Kiểm tra model Ollama & làm nóng trên CPU)       |
|  - Query Rewriter -> Intent Classifier -> Hybrid Retrieval -> Context Assembler   |
|  - Structured JSON Logging (STRUCTURED_CHAT_LOG) & Deep Health Check (/health)    |
+------------+----------------------------+----------------------------+------------+
             |                            |                            |
             v                            v                            v
+-------------------------+  +-------------------------+  +-------------------------+
| PostgreSQL 16 + pgvector|  |   Redis 7 + Celery      |  |  Ollama Local Server    |
|       (Port 5432)       |  |      (Port 6379)        |  |      (Port 11434)       |
| - Bảng document_chunks  |  | - Queue tác vụ bất đồng |  | - Embedding:            |
| - Vector(1024) HNSW idx |  |   bộ: ingestion.        |  |   mxbai-embed-large     |
| - TSVECTOR GIN index +  |  |   process_document      |  |   (1024 chiều)          |
|   trigger cập nhật BM25 |  | - Broker & Result store |  | - LLM: qwen2.5:7b       |
+-------------------------+  +-------------------------+  +-------------------------+
```

---

## 2. Cách chạy hệ thống từ bản clone mới

### Bước 1: Chuẩn bị file môi trường `.env`
Từ thư mục gốc của dự án (`D:\RAG_Project`), sao chép file `.env.example` sang `.env`:

```powershell
cp .env.example .env
```

### Bước 2: Khởi động toàn bộ 7 service bằng một lệnh Docker Compose

```powershell
docker compose up -d --build
```

### Bước 3: Tải (pull) 2 model bắt buộc vào container Ollama
Nếu chạy lần đầu và volume `ollama-data` chưa có sẵn model, chạy lệnh sau để tải model embedding (`mxbai-embed-large`) và model sinh văn bản (`qwen2.5:7b`):

```powershell
docker exec -it rag-ollama ollama pull mxbai-embed-large
docker exec -it rag-ollama ollama pull qwen2.5:7b
```

### Bước 4: Kiểm tra trạng thái hệ thống (`/health`)

```powershell
curl http://127.0.0.1:8000/health
```

Kết quả trả về HTTP `200 OK` liệt kê chi tiết trạng thái từng thành phần:
- `components.database`: kết nối PostgreSQL và extension `pgvector`
- `components.redis`: kết nối Redis (`PING`)
- `components.ollama`: trạng thái kết nối Ollama, danh sách model đã cài (`mxbai-embed-large`, `qwen2.5:7b`) và trạng thái làm nóng (`warmup_status`)
- `components.celery_worker`: xác nhận task `ingestion.process_document` đã được đăng ký trong worker.

Truy cập giao diện web tại: **`http://localhost:3000`** (Tài khoản Admin mặc định khởi tạo từ `.env`: `admin@example.com` / `AdminPassword123!`).

---

## 3. Các biến `.env` bắt buộc và ý nghĩa

| Biến môi trường | Giá trị mặc định | Mô tả |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://rag:rag@localhost:5432/ragdb` | Kết nối async PostgreSQL cho FastAPI và Celery worker |
| `REDIS_URL` | `redis://localhost:6379/0` | Kết nối Redis cho Celery broker/backend |
| `EMBEDDING_PROVIDER` | `ollama` | Nhà cung cấp vector embedding (`ollama` cho chạy local) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Địa chỉ dịch vụ Ollama trong mạng Docker |
| `OLLAMA_EMBEDDING_MODEL` | `mxbai-embed-large` | Model embedding 1024 chiều khớp với cột `Vector(1024)` |
| `LLM_PROVIDER` | `ollama` | Nhà cung cấp mô hình ngôn ngữ (`ollama`) |
| `LLM_MODEL` | `qwen2.5:7b` | Model sinh câu trả lời trên Ollama |
| `FIRST_TOKEN_TIMEOUT_SECONDS` | `120` | Thời gian chờ tối đa (giây) cho token đầu tiên khi chạy trên CPU |
| `ENABLE_BM25` | `true` | Bật/tắt tìm kiếm từ khóa BM25 (`tsvector`) trong hybrid retrieval |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `512` / `51` | Kích thước chunk (token) và phần chồng lấp mặc định |
| `RATE_LIMIT_CHAT` / `RATE_LIMIT_UPLOAD` | `30` / `10` | Giới hạn số request mỗi phút cho API chat và upload |

---

## 4. Đánh giá chất lượng hệ thống (Golden Dataset Benchmark)

Hệ thống đi kèm bộ dữ liệu vàng `backend/app/evaluation/golden_dataset.json` gồm **52 cặp hỏi đáp** bám sát tài liệu (`sample-article.txt` và `rag-architecture-guide.md`), bao gồm cả các câu hỏi ngoài phạm vi tài liệu để kiểm tra khả năng từ chối trả lời (`strict_documents`).

### Chạy đánh giá bằng một lệnh

```powershell
# Chạy trong container backend:
docker compose exec backend python scripts/run_evaluation.py

# Hoặc chạy kèm so sánh đóng góp của BM25 (Vector-only vs. Hybrid BM25 + Vector):
docker compose exec backend python scripts/run_evaluation.py --compare-bm25
```

### Số đo thực nghiệm đã kiểm chứng trên bộ 52 câu hỏi vàng

Kết quả chạy thực tế từ `scripts/run_evaluation.py` (lưu tại `backend/app/evaluation/evaluation_report.json` và `evaluation_history.json`):

| Chế độ Retrieval | Faithfulness | Context Precision | Context Recall | Latency p50 / p95 (Retrieval + Synthesis) | Avg Tokens / Answer |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Vector-Only (`ENABLE_BM25=false`)** | `0.9808` (98.1%) | `0.9103` (91.0%) | `0.9426` (94.3%) | `0.59 ms` / `0.71 ms` | `79.7` |
| **Hybrid RRF (`ENABLE_BM25=true`)** | `1.0000` (100.0%) | `0.8818` (88.2%) | `0.9808` (98.1%) | `0.91 ms` / `1.10 ms` | `82.7` |

- Khi bật **BM25 kết hợp Vector qua RRF**, chỉ số **Context Recall tăng từ 94.3% lên 98.1% (+3.82 điểm phần trăm)** và **Faithfulness đạt 100.0%** nhờ tìm đúng các đoạn chứa định danh kỹ thuật và từ khóa chính xác (`ix_chunks_embedding_hnsw`, `trg_chunks_search_vector`, `FIRST_TOKEN_TIMEOUT_SECONDS`).
- Toàn bộ 6/6 câu hỏi ngoài phạm vi tài liệu (ví dụ: *"What is the capital of France?"*, *"What is the population of Tokyo in 2026?"*) đều được hệ thống từ chối chính xác (`abstained = true`).

---

## 5. Cách chạy bộ kiểm thử (Tests)

```powershell
# 1. Chạy script kiểm tra nghiệm thu toàn diện (5 lỗi gốc + 8 tiêu chí nghiệm thu):
docker compose exec backend python scripts/verify_acceptance.py

# 2. Chạy toàn bộ pytest backend:
docker compose exec backend pytest -v

# 3. Chạy unit tests frontend (Vitest):
cd frontend
npm test -- --run
```

---

## 6. Các lỗi thường gặp và cách khắc phục (Troubleshooting)

1. **Lỗi thiếu model trên Ollama (`Missing Ollama models: mxbai-embed-large, qwen2.5:7b`)**:
   - **Nguyên nhân**: Container `rag-ollama` đã chạy nhưng chưa pull model về volume.
   - **Cách sửa**: Kiểm tra `curl http://127.0.0.1:8000/health` xem mục `components.ollama.missing_models`, sau đó chạy `docker exec -it rag-ollama ollama pull mxbai-embed-large` và `docker exec -it rag-ollama ollama pull qwen2.5:7b`.
2. **Câu hỏi đầu tiên sau khi khởi động phản hồi chậm trên máy chỉ có CPU**:
   - **Nguyên nhân**: Model `qwen2.5:7b` (4.7GB) cần nạp vào RAM.
   - **Cách sửa**: Hệ thống đã tự động chạy tác vụ warmup lúc khởi động và nâng giới hạn chờ token đầu tiên lên `120` giây (`FIRST_TOKEN_TIMEOUT_SECONDS=120`), đồng thời hiển thị thông báo *"Đang tải model, vui lòng chờ..."* trên giao diện chat.
3. **Tài liệu cũ trước khi nâng cấp không tìm thấy bằng từ khóa BM25**:
   - **Nguyên nhân**: Các bản ghi cũ có cột `search_vector` bị `NULL`.
   - **Cách sửa**: Khi khởi động, `backend` tự động tạo lại trigger `trg_chunks_search_vector` và chạy lệnh SQL backfill toàn bộ các dòng `search_vector IS NULL`. Bạn cũng có thể bấm nút **Re-index** trên giao diện quản lý tài liệu.
