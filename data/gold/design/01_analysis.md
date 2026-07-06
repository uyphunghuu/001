
# Gold Layer — Architectural Analysis

## 1. Vấn đề cốt lõi

Silver đã giải quyết "dữ liệu đến từ đâu, ở dạng nào".
Gold phải giải quyết "dữ liệu này **có nghĩa là gì**".

Ví dụ:
- Một email xác nhận đơn hàng → FinancialRecord + Event (giao hàng)
- Một lịch hẹn khám bệnh → Activity (type=healthcare) + Person (bác sĩ) + Place (phòng khám)
- Một GitHub Issue → Issue + Project + Person (assignee) + Activity (code review)

Silver nhìn thấy **cấu trúc** (content, from, to, date).
Gold phải nhìn thấy **ý nghĩa** (đây là cuộc hẹn với bác sĩ, có deadline, cần reminder).

## 2. Thách thức thiết kế

| Vấn đề | Mô tả |
|--------|-------|
| Polyformism | Một dữ liệu có thể là nhiều thứ cùng lúc (Invoice vừa là FinancialRecord vừa là Document) |
| Evolution | Kiểu dữ liệu mới xuất hiện liên tục (AI agent logs, IoT data, v.v.) |
| Granularity | Cùng là "Activity" nhưng "chạy bộ 5km" khác với "họp daily standup" |
| Relationship | Invoice "thuộc về" Project, nhưng cũng "liên quan" đến Vendor |
| Temporal | Mọi knowledge đều có thời điểm (created, updated, relevant từ->đến) |
| AI Readiness | AI Agent cần query "cho tôi biết mọi thứ liên quan đến dự án X" |

## 3. Phân tích bản chất của "Knowledge"

Sau khi phân tích hàng trăm loại dữ liệu có thể có, tôi thấy mọi knowledge đều có thể biểu diễn bằng **4 khía cạnh**:

```
┌────────────────────────────────────────────────┐
│                  KNOWLEDGE                      │
├────────────┬───────────┬──────────┬─────────────┤
│  WHAT it is │ WHO involved │ WHEN    │ WHERE/WHICH │
│  (Type)     │ (Agents)    │ (Time)  │ (Context)    │
├────────────┴───────────┴──────────┴─────────────┤
│              CONTENT (text, media, data)         │
│              RELATIONSHIPS (graph edges)         │
│              STATE (status, lifecycle)           │
└────────────────────────────────────────────────┘
```

**Type taxonomy (phân loại knowledge):**

```
KnowledgeObject
├── Activity        (việc đã/có thể làm: họp, chạy bộ, học, đọc...)
├── Event           (sự kiện thời gian: sinh nhật, lễ, deadline...)
├── Communication   (trao đổi thông tin: email, chat, call...)
├── Document        (nội dung lưu trữ: word, pdf, notion...)
├── FinancialRecord (giao dịch tài chính: invoice, expense...)
├── Goal            (mục tiêu: OKR, habit, target...)
├── Issue           (vấn đề: bug, risk, blocker...)
├── Decision        (quyết định: meeting outcome, choice...)
├── Resource        (tài nguyên: file, link, tool...)
├── Place           (địa điểm: office, clinic, gym...)
├── Agent           (con người/tổ chức tham gia)
└── Concept         (khái niệm trừu tượng: tag, category, topic)
```

## 4. Phân tích phương án kiến trúc

### Phương án A: "Super Entity" — Single Table Inheritance

**Cách hoạt động:**
- Một bảng `knowledge_objects` với type discriminator
- Mọi thuộc tính đặc thù đều trong JSONB
- Relationships là bảng riêng (SPO triples)

```sql
knowledge_objects (
  id UUID PK,
  type VARCHAR(50),      -- 'activity', 'event', 'document', ...
  subtype VARCHAR(50),   -- 'meeting', 'sport', 'appointment'
  name TEXT,
  summary TEXT,
  properties JSONB,      -- mọi thuộc tính đặc thù của type
  content TEXT,
  source_ref JSONB,      -- link về Silver
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  effective_start TIMESTAMPTZ,
  effective_end TIMESTAMPTZ,
  status VARCHAR(30),
  embedding VECTOR(1536) -- cho semantic search
)
```

| Ưu điểm | Nhược điểm |
|---------|-----------|
| Thêm type mới: zero migration | Index trên JSONB không optimized bằng column |
| Query đơn giản: SELECT FROM knowledge_objects WHERE type='X' | Không có type safety ở DB level |
| Relationship dễ join (1 bảng duy nhất) | Một bảng có thể rất lớn (hàng trăm triệu rows) |
| AI Agent chỉ cần hiểu 2 bảng (objects + relationships) | Không thể dùng CHECK constraint cho type-specific fields |
| Embedding search trên 1 bảng | ORM mapping phức tạp (polymorphic) |

### Phương án B: "Polymorphic Core" — Class Table Inheritance

**Cách hoạt động:**
- Bảng `core_objects` với các field chung nhất
- Mỗi type cluster có bảng riêng, kế thừa core_objects
- Type clustering: các type có field tương tự nhau gom chung

```sql
core_objects (
  id UUID PK,
  type VARCHAR(50),
  name TEXT,
  summary TEXT,
  source_ref JSONB,
  created_at, updated_at,
  important BOOLEAN,
  confidence FLOAT,       -- AI classification confidence
  embedding VECTOR(1536)
)

activities (inherits core_objects)
  start_time, end_time, is_all_day,
  location_ref UUID,
  participants JSONB,
  recurrence_rule TEXT

documents (inherits core_objects)
  content TEXT,
  word_count INT,
  language VARCHAR(10),
  page_count INT

communications (inherits core_objects)
  subject TEXT,
  body TEXT,
  from_agent UUID,
  to_agents JSONB,
  thread_id VARCHAR(100)

financial_records (inherits core_objects)
  amount NUMERIC,
  currency VARCHAR(3),
  transaction_date DATE,
  category VARCHAR(50)
```

| Ưu điểm | Nhược điểm |
|---------|-----------|
| Type safety: có column riêng cho từng cluster | Thêm type mới: cần migration |
| Performance: index trên column cụ thể | Nhiều bảng = phức tạp hơn |
| ORM friendly: mỗi entity là 1 class | AI Agent cần join nhiều bảng |
| Có thể dùng CHECK, FK constraints | Relationship graph phức tạp (nhiều bảng FK) |

### Phương án C: "Graph-Centric" — Universal Node-Edge (tôi đề xuất)

**Cách hoạt động:**
- Mọi thứ là Node với properties JSONB
- Node có type, subtype, và traits (attributes gắn thêm)
- Edge (relationship) là first-class citizen
- Một bảng timeline cho mọi thay đổi trạng thái

```sql
nodes (
  id UUID PK,
  type VARCHAR(50),       -- 'activity', 'event', 'document', ...
  subtype VARCHAR(50),    -- 'meeting', 'sport', 'invoice'
  name TEXT,
  summary TEXT,
  properties JSONB,       -- type-specific data
  content TEXT,
  source_ref JSONB,       -- link to Silver
  traits JSONB,           -- ['is_deadline', 'is_recurring', 'needs_reminder']
  status VARCHAR(30),     -- 'active', 'completed', 'cancelled'
  confidence FLOAT,
  importance INTEGER,     -- 1-5  (AI-estimated)
  
  -- Temporal
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  effective_start TIMESTAMPTZ,
  effective_end TIMESTAMPTZ,
  
  -- AI
  embedding VECTOR(1536),      -- pgvector
  embedding_updated_at TIMESTAMPTZ,
  
  -- Metadata
  metadata JSONB               -- extensible
)

edges (
  id UUID PK,
  source_node_id UUID FK → nodes,
  target_node_id UUID FK → nodes,
  predicate VARCHAR(100),       -- 'participates_in', 'belongs_to', 'has_deadline'
  weight FLOAT,                 -- relationship strength
  properties JSONB,             -- extra edge data
  created_at TIMESTAMPTZ,
  valid_from TIMESTAMPTZ,
  valid_until TIMESTAMPTZ,
  metadata JSONB
)

node_agents (
  node_id UUID FK → nodes,
  agent_id UUID FK → nodes (WHERE type = 'agent'),
  role VARCHAR(50),         -- 'owner', 'participant', 'assignee', 'creator'
  properties JSONB
)

node_timeline (
  id UUID PK,
  node_id UUID FK → nodes,
  field VARCHAR(50),        -- 'status', 'importance', 'assigned_to'
  old_value TEXT,
  new_value TEXT,
  changed_by UUID FK → nodes,  -- agent
  changed_at TIMESTAMPTZ,
  metadata JSONB
)
```

| Ưu điểm | Nhược điểm |
|---------|-----------|
| Thêm type mới: zero migration (chỉ thêm subtype string) | JSONB query performance cần index cẩn thận |
| Graph-native: knowledge graph ưu việt | Overhead cho relationship insert |
| AI Agent chỉ cần học 3-4 bảng | Cần trigger/code để maintain consistency |
| Timeline tracking built-in | Không có structural constraint (phải validate ở app layer) |
| Traits system: gắn behavior flag vào node (is_deadline, needs_reminder) | Embedding sync complexity |
| Edge có temporal validity (relationship có hạn) | |
| Mọi entity đều có thể làm subject hoặc object của relationship | |

## 5. So sánh tổng quan

| Tiêu chí | A. Super Entity | B. Polymorphic Core | C. Graph-Centric |
|----------|:-:|:-:|:-:|
| Zero migration khi thêm type mới | ✅✅ | ❌ | ✅✅ |
| Query performance | ⚠️ | ✅ | ⚠️ |
| AI Agent friendly | ✅ | ⚠️ | ✅✅ |
| Knowledge Graph support | ✅ | ⚠️ | ✅✅ |
| Type safety | ❌ | ✅ | ❌ |
| Temporal tracking | ⚠️ | ⚠️ | ✅✅ |
| Multi-Agent readiness | ⚠️ | ❌ | ✅✅ |
| Code maintainability | ✅ | ⚠️ | ✅ |
| Vector search integration | ✅ | ⚠️ | ✅✅ |
| Polymorphic relationships | ⚠️ | ❌ | ✅✅ |
| 5-10 year scalability | ⚠️ | ❌ | ✅✅ |

## 6. Đề xuất: Phương án C — Graph-Centric (tối ưu)

**Lý do chọn:**

1. **Zero migration** — Thêm WhatsApp chat, Fitbit data, hay Google Drive file đều chỉ cần thêm subtype string, không cần ALTER TABLE. Đây là yêu cầu cứng.

2. **AI-native** — AI Agent suy nghĩ theo graph traversal (A → connected to B → connected to C), không phải SQL JOIN. Graph model mapping 1-1 với Agent reasoning.

3. **Knowledge Graph built-in** — Mọi relationship đều là SPO triple có thể export thành RDF/Knowledge Graph. Cho phép:
   - Graph traversal: "Tìm mọi thứ liên quan đến dự án X"
   - Path analysis: "Người A ảnh hưởng đến dự án nào qua những ai?"
   - Community detection: "Nhóm nào đang làm việc với nhau?"

4. **Temporal-first** — Mọi node và edge đều có thời gian hiệu lực. Cho phép:
   - Time travel: "Dự án X tuần trước có gì?"
   - Future planning: "Tuần sau có deadline nào?"
   - Historical analysis: "Invoice tháng trước là bao nhiêu?"

5. **Traits system** — Thay vì hard-code flag như `is_deadline`, `is_recurring`, dùng traits array. Node `deadline_01` có trait `['has_deadline', 'high_priority']` mà không cần schema change.

## 7. Rủi ro và mitigation

| Rủi ro | Mitigation |
|--------|-----------|
| JSONB performance | Composite indexes: (type, (properties->>'field')), GIN indexes trên JSONB |
| No referential integrity | App-level validation + periodic audit scripts |
| Edge explosion | Edge pruning strategy: archive edges older than N years |
| Embedding sync | Async worker cập nhật embedding khi content change |
| Query complexity | View layer + materialized views cho common queries |
| Data consistency | Application-level transaction manager + outbox pattern |

## 8. Câu hỏi cần quyết định

1. **Embedding strategy**: Dùng pgvector hay external vector DB (Pinecone, Weaviate)?
2. **LLM classification**: Dùng LLM để tự động phân loại type/subtype từ Silver data?
3. **Relationship discovery**: Build rule-based hay ML-based relationship extraction?
4. **Content storage**: Text content trong PostgreSQL hay external (S3, GCS)?
5. **Traits system**: Traits cố định hay dynamic? Có cần trait hierarchy không?

---

*Chờ phản hồi trước khi viết source code.*
