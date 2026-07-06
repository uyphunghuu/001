# Silver Layer Docker Infrastructure

## Services

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL 17 | 5433 | Main database |
| pgAdmin 4 | 5050 | Database admin UI |
| MinIO | 9000 | S3-compatible object storage API |
| MinIO Console | 9001 | MinIO web UI |

## Quick Start

```bash
# Copy environment file
cp .env.example .env

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## Access

| Service | URL | Credentials |
|---------|-----|-------------|
| pgAdmin | http://localhost:5050 | admin@platform.local / admin123 |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| PostgreSQL | localhost:5433 | platform / platform123 |

## Connect pgAdmin to PostgreSQL

1. Open http://localhost:5050
2. Login with admin@platform.local / admin123
3. Right-click "Servers" → "Register" → "Server"
4. General tab: Name = "AI Platform"
5. Connection tab:
   - Host: postgres
   - Port: 5432
   - Database: ai_platform
   - Username: platform
   - Password: platform123

## Buckets

The `mc` container automatically creates:
- `gmail-raw` — Bronze layer raw data
- `silver-output` — Silver layer output files
