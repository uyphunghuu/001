# Setup and Testing Guide for ai-platform

## Docker Compose Setup

MinIO is running via Docker Compose with the following configuration:

```yaml
version: "3.8"
services:
  minio:
    image: minio/minio:latest
    container_name: ai-platform-minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
    volumes:
      - ../../data/bronze/minio:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s
    restart: unless-stopped
    networks:
      - ai-platform-net

networks:
  ai-platform-net:
    driver: bridge
```

## Expected Behavior

1. **Bronze Layer**: The MinIO instance stores raw Gmail attachments in the `gmail-raw` bucket
2. **Bind Mount**: Data is persisted in `../../data/bronze/minio` on the host
3. **Health Check**: Docker Compose monitors the MinIO service health
4. **Credentials**: Default credentials are used (minioadmin/minioadmin)

## Usage

### Start MinIO
```bash
cd infrastructure/docker
docker compose down -v
docker compose up -d
```

### Check Status
```bash
docker compose ps
docker compose logs
```

### Access Console
- Web Console: http://localhost:9001
- API: http://localhost:9000

## Current Status

- ✅ Docker Compose is running with health checks
- ✅ Bind mount is configured for bronze layer
- ❌ Template uploads may need explicit mc client installation in container
- ❌ Docker Compose health check may require `mc` to be available in the container

## Recommendations

1. Ensure `mc` (MinIO client) is available in the MinIO Docker container
2. Optionally set custom credentials in `.env` file for production
3. Consider adding `mc` installation to Docker image if health checks fail
4. Set up proper secrets management for production deployments

## Files

- `infrastructure/docker/docker-compose.yml` - Main configuration
- `infrastructure/docker/.env` - Environment variables
- `scripts/install_mc.sh` - MinIO client installation script
- `test_minio_integration.py` - Integration test script

## Testing

Run the integration test:
```bash
python test_minio_integration.py
```