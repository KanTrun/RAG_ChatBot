# Kiến trúc Hệ thống & Quyết định Kỹ thuật (`ARCHITECTURE.md`)

Tài liệu này mô tả chi tiết luồng dữ liệu từ lúc người dùng tải tài liệu lên cho đến khi nhận được câu trả lời có trích dẫn nguồn, cùng các cải tiến hiệu năng, bảo mật và giao diện qua 4 Phase nâng cấp.

---

## 1. Luồng dữ liệu đầu-cuối (End-to-End Data Flow)

### 1.1. Luồng Ingestion Tối ưu (Phase 1)

```text
[File Upload: PDF / DOCX / TXT / MD / HTML (<= 50MB)]
       |
       v
1. Kiểm tra định dạng & SHA-256 content_hash cấp tài liệu
       |
       v
2. Lưu Document (status = 'pending') & đẩy task 'ingestion.process_document' qua Celery
       |
       v
3. Parser theo định dạng (PdfParser / DocxParser / TextParser / HtmlParser)
   - Cập nhật metadata_.stage = "parsing"
   - Trích xuất tiêu đề thực tế từ cỡ chữ PDF, style Heading trong DOCX, thẻ # trong MD/TXT
       |
       v
4. Xây dựng khối ngữ nghĩa & Chia nhỏ văn bản (ChunkingEngine: 512 token, overlap 51)
   - Cập nhật metadata_.stage = "chunking"
   - Gán section_path, heading_level, page_start/page_end và block_type
       |
       v
5. Khử trùng lặp Chunk & Batch Embedding có giới hạn đồng thời (OllamaEmbeddingService)
   - Khử trùng lặp nội dung chunk bằng SHA-256 content_hash (không embed lại đoạn trùng)
   - Gọi /api/embed theo lô (batch_size = 32) với Semaphore(4), tái sử dụng httpx.AsyncClient
   - Cập nhật tiến độ thật metadata_.stage_message = "embedding i/m chunks"
       |
       v
6. Bulk Insert & Chuẩn hóa Tìm kiếm Toàn văn Tiếng Việt (PostgreSQL + pgvector)
   - Lưu cột embedding Vector(1024) + cột search_vector TSVECTOR kết hợp cả bản có dấu
     và bản không dấu (strip_vietnamese_accents) để BM25 bắt trúng truy vấn tiếng Việt
   - Cập nhật Document status = 'indexed'
```

### 1.2. Luồng Truy vấn, Phòng chống Prompt Injection & Hậu kiểm Trích dẫn (Phase 1 & Phase 2)

```text
[Câu hỏi người dùng + Lịch sử hội thoại + Danh sách tài liệu đang chọn]
       |
       v
1. Kiểm tra đại từ tham chiếu & Viết lại truy vấn có điều kiện (QueryRewriter)
   - Chỉ gọi LLM hoặc rule-based expansion khi câu hỏi có đại từ ("nó", "cái đó", "it", "that"...)
   - Câu hỏi độc lập đi thẳng vào bước Retrieval (rewrite_ms = 0 ms)
       |
       v
2. Phân loại ý định & Lập kế hoạch truy vấn (RetrievalIntentService)
   - 7 intent: definition, factual, summary, compare, extract, multi_hop, question
   - "what is", "how does", "how do", "là gì", "như thế nào" -> 'definition' (không ép đa section)
       |
       v
3. Tìm kiếm lai song song (Parallel Hybrid Search: Vector HNSW + BM25)
   - Kiểm tra LRU + TTL Query Embedding Cache (512 mục, TTL 1800s) trước khi gọi Ollama
   - Chạy song song _vector_search (SET LOCAL hnsw.ef_search = 64) và _bm25_search qua asyncio.gather
   - Hợp nhất thứ hạng bằng Reciprocal Rank Fusion (RRF, k = 60)
       |
       v
4. Khử trùng lặp, Gom cụm Bằng chứng (EvidenceCluster) & Từ chối Nhanh (< 2 giây)
   - Nếu điểm bằng chứng dưới ngưỡng hoặc không khớp từ khóa miền tài liệu ở chế độ strict_documents:
     trả về thông báo từ chối theo đúng ngôn ngữ câu hỏi kèm gợi ý tài liệu hiện có mà KHÔNG gọi LLM
       |
       v
5. Đóng gói Prompt Chống Injection & Sinh câu trả lời đúng ngôn ngữ (rag_prompt_template.py)
   - Lọc các chỉ thị độc hại trong chunk qua sanitize_context_chunks và bọc trong thẻ <retrieved_context>
   - Nhận diện ngôn ngữ câu hỏi (detect_query_language: 'vi' / 'en') và ép cấu trúc theo intent
     (bảng Markdown cho 'compare', đa mục cho 'summary', kết luận trực tiếp ở câu đầu cho 'factual')
       |
       v
6. Hậu kiểm Trích dẫn & Phát SSE theo giai đoạn (output_validator.py & chat_router.py)
   - Phát sự kiện SSE status ('retrieving' -> 'generating') -> 'chunk' -> 'sources' -> 'done'
   - Chạy validate_and_clean_citations loại bỏ mọi trích dẫn [n] vượt ngoài phạm vi 1..len(sources)
```

---

## 2. Thiết kế An toàn Kiểm thử & Giao diện Next.js (Phase 0 & Phase 3)

1. **Chốt chặn An toàn Database (`backend/tests/conftest.py`)**:
   - Hàm `verify_test_database_safety()` kiểm tra `DATABASE_URL` và `DATABASE_SYNC_URL` ngay khi nạp `conftest.py`. Nếu thiếu chuỗi `"rag_test"`, quá trình test lập tức dừng với `pytest.exit(..., returncode=1)` để bảo vệ tuyệt đối cơ sở dữ liệu thật (`ragdb`).
2. **Kiến trúc Giao diện Chat & Portal Menu (`frontend/components/chat/`)**:
   - `OverflowActionMenu` render qua `createPortal(..., document.body)` với `fixed z-50`, tự động lật hướng khi sát mép dưới/phải màn hình, không bao giờ bị cắt bởi `overflow-hidden` của sidebar hay bong bóng chat.
   - `ActiveDocumentContextBar` hiển thị tối đa 2 chip tài liệu trên một dòng gọn gàng và gom các tài liệu còn lại vào Popover `+N more` có thanh cuộn độc lập (`max-h-56 overflow-y-auto`).
   - `MessageBubble` tách biệt hoàn toàn thông tin chẩn đoán kỹ thuật vào thẻ `<details>` (`"Chi tiết kỹ thuật"`), hỗ trợ nút Copy cho từng khối code và hiển thị Tooltip xem trước đoạn trích khi di chuột vào `[n]`.
