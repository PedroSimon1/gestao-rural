#!/usr/bin/env bash
# Servidor de produção (Render). PORT e WEB_CONCURRENCY vêm da plataforma.
# gthread (1 worker, WEB_THREADS threads): uma chamada longa ao Gemini ocupa só
# uma thread; o login e as demais telas continuam atendendo. Cada thread abre a
# própria conexão com o banco (CONN_MAX_AGE=0), então o teto é workers x threads.
# GUNICORN_TIMEOUT é o prazo de vida do worker sem sinal. Nas threads ele não
# limita uma requisição: o limite do Gemini é o timeout do próprio cliente
# (GEMINI_TIMEOUT_SEGUNDOS x GEMINI_MAX_TENTATIVAS).
set -o errexit

exec python -m gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --worker-class gthread \
    --threads "${WEB_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-420}"
