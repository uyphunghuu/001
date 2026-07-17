@echo off
REM ── Grafana Cloud Setup Script ─────────────────────────────
REM Step 1: Sign up
echo ========================================
echo   BUOC 1: Tao tai khoan Grafana Cloud
echo ========================================
echo   1. Mo https://grafana.com
echo   2. Click "Sign up for free" (dung Google/GitHub)
echo   3. Xac nhan email
echo.
echo ========================================
echo   BUOC 2: Lay credentials
echo ========================================
echo   1. Vao https://grafana.com/org/access-policies
echo   2. Click "Create API Key" - Role: MetricsPublisher
echo   3. Copy "Instance ID" (la so, VD: 123456)
echo   4. Copy "API Key" (chuoi dai)
echo.
pause
echo.
echo ========================================
echo   BUOC 3: Nhap credentials
echo ========================================
set /p GC_ID="Instance ID: "
set /p GC_KEY="API Key: "
echo.
echo GC_INSTANCE_ID=%GC_ID%> .env.grafana-cloud
echo GC_API_KEY=%GC_KEY%>> .env.grafana-cloud
echo GC_ENABLED=true>> .env.grafana-cloud
echo GC_REGION=us-central-0>> .env.grafana-cloud
echo.
echo Da luu credentials vao .env.grafana-cloud
echo.
echo ========================================
echo   BUOC 4: Chay monitoring push mode
echo ========================================
echo.
echo Docker compose se chay:
echo   - Prometheus (scrape local + push len Grafana Cloud)
echo   - OTel Collector (tracing)
echo   - Pushgateway (pipeline jobs)
echo.
echo KHONG chay Grafana/Loki/Tempo local nua.
echo.
echo Chay lenh:
echo   docker compose -f monitoring/docker-compose.grafana-cloud.yml up -d
echo.
echo Mo dashboard tai: https://%GC_ID%.grafana.net
echo (dang nhap bang tai khoan grafana.com)
echo.
echo ========================================
echo   BUOC 5: Import dashboards
echo ========================================
echo   Trong Grafana Cloud:
echo   1. Dashboards ^> New ^> Import
echo   2. Upload file JSON tu monitoring/grafana/dashboards/
echo   3. Chon datasource "grafanacloud-prom"
echo   4. Lam lai cho 9 dashboards
echo.
echo Hoac dung script: python monitoring/upload_dashboards.py
echo.
pause
