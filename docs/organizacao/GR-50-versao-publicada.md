# GR-50 parcial — SHA publicado na home (DEL-05)

O rodapé usa RENDER_GIT_COMMIT, variável padrão do Render, para mostrar o SHA
integral do commit do deploy e o link para esse commit no GitHub.
Fonte: [Render — Default Environment Variables](https://render.com/docs/environment-variables).
Somente um SHA hexadecimal completo é exibido. Sem valor válido, aparece
"Versão publicada: não informada neste ambiente." Não há fallback inventado,
execução de Git, dependência de .git, alteração de settings ou consulta externa.

## Verificação humana depois da publicação

1. Identificar o SHA do commit de release integrado e escolhido para o deploy.
2. Após o deploy terminar, abrir a home da URL entregue ao professor.
3. Conferir o SHA integral no rodapé contra o deploy do Render e o commit no GitHub.
4. Abrir o link e guardar a evidência da mesma versão. Conferir também em janela
   sem cache se a página anterior estava aberta.

Falta realizar essa verificação real após deploy. Sem ela DEL-05 não está
concluído em produção. A GR-50 ainda depende de homologação funcional, bancos
isolados, migrations humanas coordenadas, publicação e demais evidências.
Nenhum deploy ou mudança em QA/PROD faz parte deste incremento.
