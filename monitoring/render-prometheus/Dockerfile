FROM prom/prometheus:v2.53.0

USER root
RUN apk add --no-cache gettext

COPY prometheus.yml.tpl /etc/prometheus/prometheus.yml.tpl
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER nobody

EXPOSE 9090

ENTRYPOINT ["/entrypoint.sh"]
