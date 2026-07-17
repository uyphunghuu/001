FROM prom/prometheus:v2.52.0

USER root
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
USER nobody

EXPOSE 9090

ENTRYPOINT ["/entrypoint.sh"]
