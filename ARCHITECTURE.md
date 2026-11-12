# Kiến trúc Hệ thống & Quyết định Kỹ thuật (`ARCHITECTURE.md`)

Tài liệu này mô tả chi tiết luồng dữ liệu từ lúc người dùng tải tài liệu lên cho đến khi nhận được câu trả lời có trích dẫn nguồn, cùng lý do lựa chọn từng quyết định thiết kế trong hệ thống.

---

## 1. Luồng dữ liệu đầu-cuối (End-to-End Data Flow)

### 1.1. Luồng Ingestion (Từ lúc Upload tài liệu đến lúc lưu vào Database)

```text
[File Upload: PDF / DOCX / TXT / MD / HTML]
       |
       v
1. Kiểm tra định dạng & kích thước (<= 50MB) + Tính SHA-256 content_hash chống trùng lặp
       |
       v
2. Lưu bản ghi Document (status = 'pending') & đẩy task 'ingestion.process_document' qua Celery
       |
       v
3. Parser theo định dạng (PdfParser / DocxParser / TextParser / HtmlParser)
   - Trích xuất tiêu đề thực tế từ cỡ chữ PDF, style Heading/in đậm trong DOCX, thẻ # trong MD/TXT
       |
       v
4. Xây dựng khối ngữ nghĩa (build_semantic_blocks)
   - Gán section_path, heading_level, page_start/page_end và phân loại block_type
     (method, results, procedure, requirements, acknowledgement, references...)
       |
       v
5. Chia nhỏ văn bản (ChunkingEngine)
   - Chia đệ quy theo đoạn/câu/từ với kích thước mặc định 512 token, chồng lấp 51 token (cl100k_base)
   - Tạo contextualized_text ghép tiêu đề tài liệu + đường dẫn section vào nội dung chunk
       |
       v
6. Sinh Vector Embedding & Lưu trữ (PostgreSQL + pgvector)
   - Gọi Ollama model 'mxbai-embed-large' sinh vector 1024 chiều theo lô (batch size = 32)
   - Ghi vào bảng document_chunks: cột 'embedding' Vector(1024) + cột 'search_vector' TSVECTOR
   - Cập nhật Document status = 'indexed' (hoặc 'failed' kèm error_message chi tiết)
```

### 1.2. Luồng Truy vấn & Sinh câu trả lời (Retrieval & Grounded Generation)

```text
[Câu hỏi người dùng + Lịch sử hội thoại + Danh sách tài liệu đang chọn]
       |
       v
1. Kiểm tra tiền điều kiện & Làm viết lại câu hỏi (QueryRewriter)
   - Kiểm tra trạng thái tài liệu (Indexed / Pending / Failed)
   - Viết lại câu hỏi phụ thuộc ngữ cảnh thành câu hỏi độc lập (ghi nhận rewrite_ms)
       |
       v
2. Phân loại ý định & Lập kế hoạch truy vấn (RetrievalIntentService)
   - Phân loại thành 1 trong 7 intent: definition, factual, summary, compare, extract, multi_hop, question
   - Câu hỏi "what is", "how does", "how do" được xếp vào 'definition' (không ép đa section)
   - Chỉ yêu cầu bằng chứng đa section khi intent cần tổng hợp VÀ tài liệu có >= 2 section thực tế
       |
       v
3. Tìm kiếm lai (Hybrid Search: Vector + BM25)
   - Nhánh Vector: tìm kiếm tương đồng cosine qua HNSW index (c.embedding <=> :query_vec)
   - Nhánh BM25: lọc từ dừng nghi vấn, tạo biểu thức to_tsquery('simple', 'tok1 | tok2') và
     chấm điểm bằng ts_rank_cd trên cột search_vector (GIN index)
   - Hợp nhất kết quả bằng Reciprocal Rank Fusion (RRF, k = 60)
       |
       v
4. Khử trùng lặp, Chính sách Section & Reranking (ghi nhận retrieval_ms, rerank_ms)
   - Loại bỏ các chunk gần trùng lặp (cosine similarity > 0.95)
   - Hạ điểm các khối boilerplate (lời cảm ơn, mục lục, tài liệu tham khảo)
   - Xếp hạng lại top-20 ứng viên thành top-5 cụm bằng chứng (EvidenceCluster)
       |
       v
5. Kiểm tra ngưỡng bằng chứng & Lắp ráp ngữ cảnh (ContextAssembler)
   - Nếu điểm bằng chứng thấp hơn ngưỡng hoặc không khớp nội dung trong chế độ 'strict_documents':
     từ chối trả lời ngay lập tức để chống bịa đặt (hallucination)
   - Đánh số trích dẫn [1], [2]... kèm metadata trang, section_path và đoạn trích (excerpt)
       |
       v
6. Stream câu trả lời qua SSE & Ghi log có cấu trúc (chat_router.py)
   - Chờ token đầu tiên tối đa 120s (FIRST_TOKEN_TIMEOUT_SECONDS=120) cho model CPU
   - Truyền từng chunk văn bản, danh sách nguồn trích dẫn và đối tượng diagnostics về giao diện
   - Ghi STRUCTURED_CHAT_LOG (JSON) và lưu Message kèm latency_ms, tokens_used vào PostgreSQL
```

---

## 2. Lý do chọn từng quyết định kỹ thuật

### 2.1. Vì sao dùng PostgreSQL + `pgvector` thay vì tách riêng hệ quản trị Vector Database khác?
1. **Tính nhất quán giao dịch (ACID) và toàn vẹn dữ liệu**: Toàn bộ metadata tài liệu (`documents`), phân quyền người dùng (`users`, `roles`, `allowed_roles`), lịch sử hội thoại (`conversations`, `messages`) và các đoạn văn bản (`document_chunks`) nằm chung trong một cơ sở dữ liệu PostgreSQL 16. Khi xóa một tài liệu, khóa ngoại `ON DELETE CASCADE` xóa sạch toàn bộ vector và chunk ngay trong cùng một transaction, không bao giờ xảy ra lỗi "vector mồ côi" (orphaned vectors) giữa hai hệ thống lưu trữ.
2. **Truy vấn kết hợp (Filtered Vector + Full-Text Search) trong một câu SQL**: Việc lọc theo `owner_id`, `document_id`, `status = 'indexed'` kết hợp với toán tử khoảng cách cosine `<=>` (trên HNSW index `m = 16, ef_construction = 200`) và tìm kiếm toàn văn `tsvector @@ to_tsquery` (trên GIN index) được thực thi trực tiếp bởi query planner của PostgreSQL mà không cần đồng bộ dữ liệu qua mạng giữa hai dịch vụ.
3. **Đơn giản hóa vận hành container**: Giảm số lượng service cần giám sát, sao lưu và cấp phát RAM trên môi trường Docker Desktop cá nhân.

### 2.2. Vì sao chọn kích thước Chunk `512` token và Overlap `51` token (10%)?
1. **Phù hợp với cửa sổ ngữ cảnh của model embedding `mxbai-embed-large`**: Một khối 512 token (khoảng 350–400 từ tiếng Anh hoặc tiếng Việt) đủ lớn để chứa trọn vẹn một định nghĩa kỹ thuật, một quy trình hoặc một lập luận hoàn chỉnh mà không làm loãng vector biểu diễn ngữ nghĩa.
2. **Giữ mạch ngữ cảnh qua ranh giới cắt với 51 token overlap (10%)**: Khi một đoạn văn dài bị tách làm hai chunk liên tiếp, phần chồng lấp 51 token (khoảng 2–3 câu cuối) đảm bảo các mệnh đề nằm ngay điểm cắt không bị mất chủ ngữ hoặc điều kiện đi kèm.
3. **Tối ưu ngân sách token đưa vào LLM (`qwen2.5:7b`)**: Với top-5 chunk được chọn (tổng cộng tối đa ~2.500 token ngữ cảnh), prompt gửi vào `qwen2.5:7b` gọn nhẹ, giúp giảm thời gian prefill trên CPU và giữ số token trung bình mỗi câu trả lời ở mức hợp lý (`~82.7` token/câu trả lời trong bài đo chuẩn). Hệ thống vẫn cho phép người dùng tùy chỉnh `chunk_size` (64–4096) và `chunk_overlap` (0–1024) cho từng tài liệu đặc thù.

### 2.3. Vì sao kết hợp Hybrid Search (BM25 + Vector) với Reciprocal Rank Fusion (RRF)?
1. **Bù đắp điểm mù của Dense Vector đối với từ khóa chính xác**: Vector embedding (`mxbai-embed-large`) nắm bắt tốt sự tương đồng về ý nghĩa khái niệm nhưng thường kém nhạy với các tên biến cấu hình, tên hàm, mã số hoặc tên chỉ mục cơ sở dữ liệu (ví dụ: `ix_chunks_embedding_hnsw`, `trg_chunks_search_vector`, `FIRST_TOKEN_TIMEOUT_SECONDS`, `ingestion.process_document`). Ngược lại, tìm kiếm từ khóa BM25 (`tsvector` + `ts_rank_cd`) bắt chính xác 100% các ký hiệu này.
2. **Chứng minh bằng số đo thực nghiệm trên bộ 52 câu hỏi vàng**:
   - Khi chỉ chạy Vector (`ENABLE_BM25=false`): **Context Recall đạt `94.26%`**, **Faithfulness đạt `98.08%`**.
   - Khi bật Hybrid BM25 + Vector (`ENABLE_BM25=true`): **Context Recall tăng lên `98.08%` (+3.82%)**, **Faithfulness đạt `100.00%`**.
3. **Reciprocal Rank Fusion (`k = 60`) không phụ thuộc thang điểm tuyệt đối**: Điểm cosine similarity (`0.0` đến `1.0`) và điểm `ts_rank_cd` của PostgreSQL có phân phối khác nhau. Công thức RRF $\text{score}(d) = \sum \frac{1}{60 + \text{rank}(d)}$ chuẩn hóa theo thứ hạng, giúp đoạn văn xuất hiện ở cả hai nhánh tìm kiếm luôn được ưu tiên đưa lên đầu danh sách ứng viên trước khi rerank.

### 2.4. Vì sao tự xây dựng Pipeline RAG bằng Python thuần thay vì phụ thuộc Framework trung gian?
1. **Kiểm soát hoàn toàn từng bước xử lý và chẩn đoán**: Mọi giai đoạn từ tách câu hỏi viết lại (`rewrite_ms`), tìm kiếm lai (`retrieval_ms`), gom cụm bằng chứng và xếp hạng (`rerank_ms`) đến sinh câu trả lời (`generation_ms`) đều được đo đếm trực tiếp và trả về trong đối tượng `diagnostics` hiển thị ngay trên giao diện người phát triển.
2. **Cơ chế chống bịa đặt (Strict Grounding & Abstention) minh bạch**: Hệ thống kiểm tra trực tiếp điểm tin cậy, độ phủ từ khóa và mật độ trích dẫn `[1], [2]` trên từng câu trả lời, kèm theo bộ hàm tạo câu trả lời dự phòng bám sát tài liệu (`build_grounded_fallback_answer`) khi luồng sinh LLM gặp sự cố.
