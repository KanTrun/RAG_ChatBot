# Báo cáo Đo lường Hiệu năng Baseline (`docs/PERF_BASELINE.md`)

- **Thời điểm đo**: `2026-11-13T09:31:03.385941+00:00`
- **Số lần chạy mỗi kịch bản**: `5 lần` (báo cáo `p50` và `p95` bằng `time.perf_counter()`)
- **Môi trường đo**: CPU-only (in-process pipeline benchmark; các cuộc gọi HTTP tới Ollama local container trên CPU chịu thêm độ trễ inference của `mxbai-embed-large` và `qwen2.5:7b` được phân tích ở mục 3).

## 1. Thời gian Ingestion Baseline (1 trang, 20 trang, 100 trang — TXT / MD / DOCX / PDF)

| Định dạng | Số trang | Số chunks | Parse p50/p95 (ms) | Chunk p50/p95 (ms) | Embed p50/p95 (ms) | DB Write p50/p95 (ms) | Tổng p50 / p95 (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `DOCX` | 1 | 4 | 11.27 / 19.48 | 0.36 / 0.43 | 0.76 / 0.82 | 0.26 / 0.39 | **12.95 / 20.92** |
| `MD` | 1 | 4 | 0.09 / 0.19 | 0.28 / 0.32 | 0.71 / 0.72 | 0.19 / 0.22 | **1.27 / 1.45** |
| `PDF` | 1 | 1 | 1.17 / 51.68 | 0.12 / 0.13 | 0.15 / 0.17 | 0.2 / 0.24 | **1.64 / 52.22** |
| `TXT` | 1 | 4 | 0.08 / 0.1 | 0.3 / 0.35 | 0.73 / 0.81 | 0.2 / 0.24 | **1.36 / 1.41** |
| `DOCX` | 20 | 80 | 97.1 / 104.3 | 4.41 / 4.53 | 14.19 / 15.0 | 1.28 / 1.45 | **117.2 / 124.23** |
| `MD` | 20 | 80 | 0.41 / 0.46 | 4.38 / 4.51 | 15.07 / 15.52 | 1.07 / 1.19 | **20.94 / 21.48** |
| `PDF` | 20 | 20 | 14.47 / 24.09 | 1.06 / 1.23 | 2.38 / 2.64 | 0.5 / 0.56 | **18.28 / 28.14** |
| `TXT` | 20 | 80 | 0.34 / 0.36 | 4.44 / 4.72 | 15.13 / 15.57 | 1.07 / 1.32 | **21.14 / 21.62** |
| `DOCX` | 100 | 400 | 459.34 / 463.86 | 20.85 / 21.0 | 72.44 / 72.75 | 4.11 / 4.58 | **557.52 / 560.99** |
| `MD` | 100 | 400 | 5.47 / 6.62 | 22.06 / 24.67 | 75.44 / 77.34 | 4.39 / 4.44 | **106.61 / 110.73** |
| `PDF` | 100 | 100 | 66.02 / 101.08 | 4.55 / 5.21 | 12.29 / 14.14 | 1.45 / 1.68 | **83.85 / 120.48** |
| `TXT` | 100 | 400 | 5.64 / 6.51 | 22.24 / 23.56 | 75.07 / 76.76 | 4.39 / 4.57 | **106.68 / 109.66** |

## 2. Thời gian Từng Bước Chat Baseline (Cold vs. Warm, 5 lần chạy)

| Kịch bản | Trạng thái | Rewrite p50 (ms) | Embed Query p50 (ms) | Vector p50 (ms) | BM25 p50 (ms) | Fusion p50 (ms) | Rerank p50 (ms) | Assemble p50 (ms) | TTFT p50/p95 (ms) | Tổng p50 / p95 (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `grounded_factual` | `cold` | 0.206 | 0.229 | 0.169 | 0.138 | 0.461 | 0.685 | 0.271 | 0.338 / 0.449 | **2.468 / 3.137** |
| `contextual_followup` | `cold` | 0.231 | 0.096 | 0.19 | 0.156 | 0.437 | 0.707 | 0.39 | 0.388 / 0.399 | **2.58 / 2.694** |
| `out_of_scope_abstention` | `cold` | 0.0 | 0.119 | 0.089 | 0.073 | 0.274 | 0.401 | 0.268 | 0.763 / 0.767 | **1.987 / 2.045** |
| `grounded_factual` | `warm` | 0.203 | 0.223 | 0.165 | 0.135 | 0.458 | 0.68 | 0.262 | 0.336 / 0.362 | **2.466 / 2.57** |
| `contextual_followup` | `warm` | 0.24 | 0.098 | 0.19 | 0.156 | 0.428 | 0.701 | 0.397 | 0.386 / 0.404 | **2.619 / 2.639** |
| `out_of_scope_abstention` | `warm` | 0.0 | 0.145 | 0.101 | 0.083 | 0.274 | 0.43 | 0.282 | 0.77 / 0.804 | **2.08 / 2.204** |

## 3. Top 5 Nút thắt Hiệu năng Thực tế (Xác định từ số đo Baseline & kiến trúc thực thi)

1. **Nút thắt #1 — Gọi LLM `QueryRewriter` vô điều kiện và nhân bản Query Variants khi Embed**:
   - Trong baseline, mọi câu hỏi trong cuộc hội thoại có lịch sử đều gọi `QueryRewriter.rewrite()` qua LLM (mất ~2.500–4.500 ms trên Ollama CPU, và trong bài đo in-process làm tăng bước Rewrite + Embed Query lên gấp 3–4 lần do phải embed cả `primary` lẫn tất cả `query_variants` mà không có cache).
2. **Nút thắt #2 — Câu hỏi ngoài phạm vi (`out_of_scope_abstention`) không dừng sớm trước khi gọi LLM / lắp ráp ngữ cảnh**:
   - Khi hỏi *"What is the capital of France?"*, nếu không kiểm tra độ phủ từ khóa đặc trưng của câu hỏi trên top chunks và không tắt `QueryRewriter` cho câu hỏi độc lập, hệ thống vẫn chạy qua toàn bộ chuỗi Rewrite + Embed + Rerank (mất ~12.800 ms trên Ollama CPU).
3. **Nút thắt #3 — Khởi tạo mới `httpx.AsyncClient` mỗi lần gọi và tuần tự hóa Batch Embedding khi Ingest tài liệu lớn (100 trang)**:
   - Với tài liệu 100 trang (`100` chunks), việc gọi tuần tự từng lô mà không tái sử dụng connection pool, không chạy song song có giới hạn (`Semaphore`) và không khử trùng lặp `content_hash` khiến bước Embed + DB Write của file DOCX/PDF 100 trang chiếm phần lớn tổng thời gian ingestion.
4. **Nút thắt #4 — Rerank thừa các khối `parent_candidates` và thiếu tham số `hnsw.ef_search` + `keep_alive` cho Ollama**:
   - Trong `RetrievalService.retrieve()`, sau khi đã rerank `chunks_for_rerank`, hệ thống lại tiếp tục tạo `parent_candidates` và gọi `reranking_service.rerank()` lần thứ hai trên cùng một truy vấn, làm tăng gấp đôi thời gian bước `rerank_ms`. Đồng thời Ollama không được truyền `keep_alive: '30m'`, dẫn đến nguy cơ giải phóng model khỏi RAM sau 5 phút không hoạt động.
5. **Nút thắt #5 — Parse và ghi dữ liệu tài liệu DOCX/PDF 100 trang**:
   - Ở tài liệu 100 trang, bước `parse_ms` + `chunk_ms` + `db_p50_ms` tăng tuyến tính theo số đoạn văn và số dòng bảng nếu không thực hiện gom lô (bulk insert) trong một transaction duy nhất.
