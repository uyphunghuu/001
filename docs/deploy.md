# Deploy Guide — Project 001

## Tổng quan CI/CD Flow

```
git push origin main
        │
        ▼
GitHub Actions
        │
        ├─► Job 1: CI (Lint)
        │       ├── ruff check app/
        │       ├── black --check app/
        │       ├── isort --check-only app/
        │       └── python import check
        │
        ├─► Job 2: Build Docker Image
        │       └── docker build (validate)
        │
        └─► Job 3: Deploy to Railway
                ├── railway up
                ├── wait 30s
                └── curl /health → must return HTTP 200
```

---

## Bước 1 — Tạo Railway Project

1. Truy cập [railway.app](https://railway.app)
2. Sign in bằng GitHub
3. Click **New Project** → **Empty Project**
4. Đặt tên: `project-001`

---

## Bước 2 — Kết nối GitHub Repository

1. Trong Railway Project → click **+ New Service**
2. Chọn **GitHub Repo**
3. Chọn repo `uyphunghuu/001`
4. Railway sẽ tự detect `Dockerfile`

---

## Bước 3 — Thiết lập Environment Variables trên Railway

Vào service → **Variables** → thêm từng biến:

| Variable | Value | Ghi chú |
|----------|-------|---------|
| `PG_HOST` | Railway PostgreSQL host | Từ Railway DB service |
| `PG_PORT` | `5432` | Railway dùng port 5432 |
| `PG_USER` | `postgres` | Railway PostgreSQL default |
| `PG_PASSWORD` | _(từ Railway DB)_ | |
| `PG_DB` | `railway` | Railway PostgreSQL default |
| `LLM_API_KEY` | _(Groq API key)_ | |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | |
| `PORT` | `8000` | Railway inject tự động |

> **Lưu ý:** Railway tự inject `PORT`. Không cần set thủ công.

---

## Bước 4 — Thêm PostgreSQL trên Railway

1. Trong cùng Project → **+ New Service** → **Database** → **PostgreSQL**
2. Railway tạo PostgreSQL và inject `DATABASE_URL` tự động
3. Copy connection string và điền vào các biến `PG_*`

---

## Bước 5 — Lấy Railway Token và Service Name

### Railway Token
1. [railway.app/account/tokens](https://railway.app/account/tokens)
2. Click **Create Token**
3. Copy token

### Service Name
1. Vào Railway Project → click vào service
2. Xem URL hoặc settings — lấy tên service (ví dụ: `web`)

---

## Bước 6 — Thêm GitHub Secrets

Vào GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret | Value |
|--------|-------|
| `RAILWAY_TOKEN` | Token từ bước 5 |
| `RAILWAY_SERVICE_NAME` | Tên service Railway |
| `RAILWAY_URL` | URL public của Railway app (ví dụ: `https://project-001.up.railway.app`) |

---

## Bước 7 — Verify CI/CD

```bash
git add .
git commit -m "ci: add CI/CD pipeline"
git push origin main
```

Xem Actions tại: `https://github.com/uyphunghuu/001/actions`

---

## Chạy local với Docker

```bash
# Build
docker build -t project-001-api .

# Run
docker run -p 8000:8000 \
  -e PG_HOST=host.docker.internal \
  -e PG_PORT=5433 \
  -e PG_USER=platform \
  -e PG_PASSWORD=platform123 \
  -e PG_DB=ai_platform \
  -e LLM_API_KEY=your_key \
  project-001-api

# Health check
curl http://localhost:8000/health
```

---

## Troubleshooting

**Docker build fail — psycopg2**
```
Error: pg_config executable not found
```
→ Đã fix: dùng `psycopg2-binary` và cài `libpq-dev` trong builder stage.

**Railway health check fail**
- Kiểm tra `PG_HOST`, `PG_PORT` đúng chưa
- Kiểm tra Railway PostgreSQL service đang chạy
- Xem logs: `railway logs`

**CI fail — black/isort**
```bash
# Fix local
black app/
isort app/
git add -u && git commit -m "style: fix formatting"
```
