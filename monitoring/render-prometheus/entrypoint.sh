#!/bin/sh
cat > /etc/prometheus/prometheus.yml << ENDCONFIG
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s

remote_write:
  - url: "https://${GC_INSTANCE_ID}.grafana.net/api/prom/push"
    basic_auth:
      username: "${GC_INSTANCE_ID}"
      password: "${GC_API_KEY}"
    remote_timeout: 30s
    queue_config:
      capacity: 10000
      max_shards: 10
      min_shards: 1

scrape_configs:
  - job_name: "ai_platform_app"
    metrics_path: /metrics
    scheme: https
    static_configs:
      - targets: ["zero01-i4nb.onrender.com"]
        labels:
          service: ai-platform
          layer: app
ENDCONFIG

exec /bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.retention.time=6h --web.enable-lifecycle "$@"
