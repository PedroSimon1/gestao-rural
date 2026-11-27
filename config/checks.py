"""Verificações de implantação da conexão com o banco."""
from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def tls_do_banco_sem_verificacao_do_servidor(app_configs, **kwargs):
    modo = settings.DATABASES["default"].get("OPTIONS", {}).get("sslmode")
    if modo == "require":
        return [Warning(
            "DB_SSLMODE=require criptografa a conexão com o banco, mas não confere o certificado do servidor.",
            hint=(
                "Use DB_SSLMODE=verify-full e informe DB_SSLROOTCERT com o certificado "
                "da CA do Supabase."
            ),
            id="config.W001",
        )]
    return []
