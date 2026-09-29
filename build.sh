#!/usr/bin/env bash
# Build de produção (Render). Sem banco: nada de migrate.
# Localmente, rode com o .venv ativado.
set -o errexit

python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
