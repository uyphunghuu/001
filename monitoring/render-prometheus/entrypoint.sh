#!/bin/sh
envsubst < /etc/prometheus/prometheus.yml.tpl > /etc/prometheus/prometheus.yml
exec /bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.retention.time=6h --web.enable-lifecycle "$@"
