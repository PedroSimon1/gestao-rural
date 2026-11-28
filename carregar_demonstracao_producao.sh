#!/usr/bin/env bash
# Carga manual e permanente em PRODUÇÃO; não aplica migrations nem grava credenciais.
set -o errexit -o nounset -o pipefail
# Nunca deixe o rastreamento do shell revelar a senha digitada.
set +o xtrace

[[ -f manage.py ]] || { echo "Rode na raiz do projeto (onde fica o manage.py)."; exit 1; }
if [[ -f .venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi
command -v python >/dev/null || { echo "python não encontrado; ative o .venv."; exit 1; }

echo "== Credenciais do banco de PRODUÇÃO (nada é gravado em disco) =="
read -r -p "DB_HOST: " DB_HOST
read -r -p "DB_PORT [5432]: " DB_PORT
read -r -p "DB_NAME: " DB_NAME
read -r -p "DB_USER: " DB_USER
read -r -s -p "DB_PASSWORD (não aparece): " DB_PASSWORD
echo
read -r -p "DB_SSLMODE [require]: " DB_SSLMODE
read -r -p "DB_SSLROOTCERT [vazio]: " DB_SSLROOTCERT
DB_PORT="${DB_PORT:-5432}"
DB_SSLMODE="${DB_SSLMODE:-require}"
[[ -n "$DB_HOST" && -n "$DB_NAME" && -n "$DB_USER" && -n "$DB_PASSWORD" ]] \
    || { echo "DB_HOST, DB_NAME, DB_USER e DB_PASSWORD são obrigatórios."; exit 1; }
export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD DB_SSLMODE DB_SSLROOTCERT

# Compara apenas em memória, antes de conectar; não imprime campos nem valores do .env.
if [[ -f .env ]]; then
    python - <<'PY'
import os
import sys
from dotenv import dotenv_values

env = dotenv_values(".env")
campos = {"DB_HOST": "", "DB_PORT": "5432", "DB_NAME": "", "DB_USER": ""}
if all((env.get(campo) or padrao) == os.environ[campo] for campo, padrao in campos.items()):
    print("ABORTADO: destino igual ao da homologação no .env.")
    sys.exit(1)
PY
else
    echo "ABORTADO: .env ausente; não é possível conferir o destino da homologação."
    exit 1
fi

python manage.py shell -c "
from django.conf import settings
banco = settings.DATABASES['default']
print('Host :', banco['HOST'])
print('Banco:', banco['NAME'])
print('Papel:', banco['USER'])
"
echo "== Plano de migrations (somente consulta) =="
PLANO="$(python manage.py migrate --plan)"
printf '%s\n' "$PLANO"
# --check usa o plano do próprio Django, sem depender de idioma ou formato do texto.
if ! python manage.py migrate --check; then
    echo "ABORTADO: existem migrations pendentes (ou não foi possível conferir)."
    echo "O responsável deve aplicá-las manualmente antes desta carga."
    exit 1
fi

echo "== Simulação da carga permanente =="
python manage.py carregar_demonstracao --simular
read -r -p "Confere o banco de PRODUÇÃO? Digite PRODUCAO para criar as notas: " CONFIRMA
[[ "$CONFIRMA" == "PRODUCAO" ]] || { echo "Cancelado. Nada foi alterado."; exit 1; }
python manage.py carregar_demonstracao --confirmar --permitir-remoto
python manage.py shell -c "from financeiro.models import NotaFiscalLancada; print('Notas fiscais no banco:', NotaFiscalLancada.objects.count())"
echo "Concluído. Credenciais descartadas ao fim deste processo."
