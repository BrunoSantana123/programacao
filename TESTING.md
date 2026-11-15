# Testes essenciais do NEXO

O escopo é cadastro/login, conexão OAuth da própria conta e receitas/despesas
pelo MCP, apresentadas no NEXO e isoladas por usuário. Não há deploy automático.

## Regressão

```sh
python -m pip install -r requirements-test.txt
python -m playwright install --with-deps chromium
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

No Codex, pode-se usar o Chromium existente com
`NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium`. Não desative verificação TLS.

## Ponta a ponta real e isolado

Docker, Python 3.12 e as dependências acima são necessários. Use um diretório
exclusivo fora do checkout, pois conterá credenciais fictícias e chaves locais.

```sh
python -m tools.setup_local_test --directory /workspace/nexo-test-environment
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_local_oauth --directory /workspace/nexo-test-environment
```

A preparação reaproveita o Supabase local existente, preserva a conta e os
registros, inicializa a tabela somente se estiver ausente e aplica a função de
gravacão. O esquema/políticas são exatamente os fornecidos pelo responsável em
`tests/integration/nexo-data-schema.sql`. A migração não recria essa tabela.

O teste usa as páginas e SDK reais, Supabase Auth/OAuth, dois usuários e a função
MCP em `supabase/functions/nexo-mcp-test/index.ts`. O cliente OAuth temporário é
criado antes de iniciar o runtime e é explicitamente autorizado no MCP. O
runtime recebe chave pública e JWT do usuário; não recebe service_role.

São exercitados:

- Cadastro, login e consentimento em telas de celular/computador.
- Aprovação, recusa, state, PKCE, recusa de código reutilizado e de tokens inválidos.
- Receitas/despesas gravadas no banco e exibidas no Financeiro sem atualização manual.
- Repetição sem duplicação, valores em centavos, preservação do JSON e concorrência com o aplicativo.
- RLS de duas contas: consulta, alteração, exclusão e inserção na conta alheia bloqueadas.
- Troca de conta no mesmo navegador, inclusive com renovação antiga de sessão em andamento.

A conta primária fictícia é mantida para inspeção. A segunda é criada pelo
cadastro normal do NEXO e removida ao terminar, junto de seus próprios dados
fictícios. Os lançamentos da conta primária são exclusivamente de teste.
Credenciais ficam em `private.json` com permissão 600 fora do Git. Não as imprima.

O fonte original recebido continua arquivado, com checksum verificado, em
`tests/fixtures/nexo-mcp-test-v2.ts`. A função nova estende esse servidor com
`registrar_lancamento` e reaproveita sua autenticação e protocolo.

## Infraestrutura já preparada

O CLI oficial 2.67.3, Postgres 15, chaves ES256 e Edge Runtime v1.69.28 são usados
localmente. No driver vfs, o preparador usa a derivação local de uma camada,
com origem/digests e configuração verificados, sem sobrescrever imagem existente
ou alterar o daemon. Ferramentas oficiais são verificadas por checksum e nenhuma
imagem é publicada. Em overlay2 essa conversão não é necessária.

O runtime usa o modo oficial main-service para executar a função fornecida,
dispensando o template genérico que importa deno.land. Não é necessário ampliar
a política de rede. Proxy e bundle público de confiança são reutilizados em
arquivos privados da sessão; o bundle é montado somente para leitura, fora de
imagens. O cliente HTTPS do Playwright obtém os bytes reais do SDK com verificação
de certificados. Não há respostas OAuth/financeiras simuladas no ensaio integrado.

Em nova sessão, repita a preparação para renovar configuração de rede/CA.
Para encerrar apenas o Supabase desta tarefa, sem reset:

```sh
/workspace/nexo-test-environment/bin/supabase --workdir /workspace/nexo-test-environment stop
```

## GitHub Actions e homologação

O workflow existente executa regressão e o ensaio integrado automaticamente nos
PRs, com permissões mínimas e sem segredos de produção. Não faz merge ou deploy.
Cada tarefa Codex já é isolada: use o checkout existente, sem novos worktrees.

O ensaio não certifica conversa/voz dentro do ChatGPT. Para esse teste final,
precisa existir um ambiente HTTPS exclusivo de homologação. Instruções e pedidos
para conferir manualmente estão em [HOMOLOGACAO.md](HOMOLOGACAO.md).
