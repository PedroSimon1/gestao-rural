"""GR-50/DEL-05: versão do deploy visível na home, sem consultar banco."""
import os
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo


@override_settings(**CREDENCIAIS_TESTE)
class VersaoPublicadaTests(SimpleTestCase):
    def setUp(self):
        autenticar_demo(self.client)

    def test_home_exibe_sha_do_deploy_e_link_exato(self):
        sha = 'abcdef0123456789abcdef0123456789abcdef01'
        with mock.patch.dict(os.environ, {'RENDER_GIT_COMMIT': sha}):
            r = self.client.get(reverse('documento_inicio'))
        self.assertContains(r, f'<code>{sha}</code>', html=True)
        self.assertContains(r, f'https://github.com/PedroSimon1/gestao-rural/commit/{sha}')

    def test_sem_sha_valido_nao_exibe_versao_ficticia(self):
        for valor in ('', 'valor-invalido', '<script>alert(1)</script>'):
            with self.subTest(valor=valor), mock.patch.dict(os.environ, {'RENDER_GIT_COMMIT': valor}):
                r = self.client.get(reverse('documento_inicio'))
                self.assertContains(r, 'Versão publicada: não informada neste ambiente.')
                self.assertNotContains(r, 'gestao-rural/commit/')
                self.assertNotContains(r, '<script>alert(1)</script>')
