# NEXO — versão mínima para homologação

Esta entrega contém somente cadastro/login, conexão OAuth da própria conta e
registro de receitas/despesas pelo MCP, visíveis no NEXO e separados por usuário.

## Executar a versão isolada

Na pasta do repositório, com as dependências de teste já preparadas:

```sh
python -m tools.setup_local_test --directory /workspace/nexo-test-environment
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_local_oauth --directory /workspace/nexo-test-environment
```

Os comandos reaproveitam a infraestrutura existente. A tabela local segue a
estrutura SQL e as políticas fornecidas pelo responsável. A preparação aplica
somente a operação nova de gravação e não substitui registros existentes.
As credenciais fictícias ficam em `private.json`, fora do Git; não copie senhas
ou tokens para conversas, issues ou relatórios.

O ensaio usa o cadastro e login reais do HTML, o OAuth do Supabase, dois usuários,
a função MCP e o banco. Verifica receitas/despesas aparecendo na tela sem
recarregar manualmente, valores em centavos, ausência de duplicação ao repetir,
gravacões concorrentes e bloqueio de leitura/escrita entre contas.

## Homologar no ChatGPT, celular e computador

**Ainda falta um ambiente HTTPS exclusivo de homologação.** A versão local não
pode ser chamada pelos servidores do ChatGPT. Nada foi publicado em produção.

Esse ambiente precisa disponibilizar:

- NEXO e `oauth-consent.html` por HTTPS, configurados com a URL/chave pública do Supabase de homologação.
- A função `nexo-mcp-test` desta branch, no projeto de homologação.
- A tabela/políticas fornecidas e a operação SQL `nexo_registrar_lancamento`.
- OAuth Server habilitado, assinatura ES256/RS256 e um cliente OAuth de homologação, com o callback apresentado pelo ChatGPT; seu Client ID deve coincidir com `oauth-config.js` e `NEXO_OAUTH_CLIENT_IDS` na função.

Não copie chaves administrativas para o front-end. A função usa a chave pública
fornecida pelo Supabase e o JWT do usuário, mantendo RLS. O endereço do projeto
vem de `SUPABASE_URL`; não usar o projeto de produção para esse ensaio.

Com o ambiente disponível e o conector configurado:

1. No celular, crie uma conta no NEXO e confirme o e-mail se o Supabase solicitar.
2. Entre na mesma conta no computador.
3. No ChatGPT, abra a conexão NEXO, escolha conectar e autentique sua conta NEXO.
4. Envie: “Registre uma receita de R$ 150 de serviço particular hoje”.
5. Envie: “Registre uma despesa de R$ 32,50 de alimentação hoje”.
6. Confira os lançamentos no Financeiro do NEXO. A tela busca alterações ao voltar e, enquanto visível, a cada 15 segundos, sem interromper um formulário aberto.
7. Use o microfone de **ditado** do ChatGPT, confira a transcrição e envie um pedido equivalente. Não foi implementado um sistema de voz separado.
8. Repita com uma segunda conta e confira que os dados da primeira não aparecem.

A disponibilidade de Apps/ferramentas e do modo de voz é controlada pelo ChatGPT.
O fluxo previsto para voz é o ditado enviado como mensagem; a sessão de voz ao
vivo não foi certificada. Conversa real e ditado serão homologados somente após
o endpoint HTTPS de testes existir.

## Banco e formato preservados

`supabase/migrations/20261115000100_registrar_lancamento.sql` acrescenta apenas
uma função transacional à tabela existente; não recria tabela, políticas ou dados.
O lançamento usa os mesmos campos do app: `id`, `date`, `type`, `category`,
`amount`, `description`. Valores são recebidos em centavos e armazenados em
reais como o NEXO já utiliza. A identidade vem do JWT, nunca de um argumento do
ChatGPT. A função executa como o usuário e continua sujeita às políticas existentes.

Não foi feito merge nem deploy em produção. A publicação de homologação depende
de definir o projeto/endereço HTTPS e disponibilizar acesso seguro para configurá-lo.
