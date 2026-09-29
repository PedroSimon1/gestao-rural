#!/usr/bin/env bash
# Servidor de produção (Render). PORT e WEB_CONCURRENCY vêm da plataforma.
# GUNICORN_TIMEOUT cobre as duas chamadas sequenciais ao Gemini, que podem
# levar minutos no pior caso (o padrão de 30 s do Gunicorn não basta).
set -o errexit

exec python -m gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --timeout "${GUNICORN_TIMEOUT:-420}"
