# Testes OAuth e MCP do NEXO

## Regressão isolada (sem Supabase)

Python 3.12, Linux x86-64:

```sh
python -m pip install -r requirements-test.txt
python -m playwright install --with-deps chromium
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

Playwright usa seu Chromium gerenciado por padrão. Para usar uma instalação
existente, defina `NEXO_CHROMIUM_EXECUTABLE` com o caminho do executável.
As dependências de teste estão fixadas em `requirements-test.txt`.

## Integração real exclusivamente local

Pré-requisitos: Docker Engine acessível, Python e dependências acima, portas
54320–54329 disponíveis e espaço para as imagens oficiais. Não use um diretório
de checkout para o ambiente, pois ele armazena chaves e a senha fictícia.

```sh
python -m tools.setup_local_test --directory /workspace/nexo-test-environment
python -m tools.validate_local_oauth --directory /workspace/nexo-test-environment
```

O primeiro comando instala o CLI oficial 2.67.3 com verificação SHA256, inicializa
um projeto **local**, gera chaves ES256 locais, habilita OAuth apenas nessa
configuração e inicia Postgres 15, Auth, gateway e REST em Docker. A versão 15,
suportada pelo CLI, reduz o custo da imagem no driver Docker `vfs`; não é uma
afirmação de compatibilidade com um esquema financeiro ausente. Reutiliza o
ambiente e a conta fictícia em execuções seguintes, sem resetar o banco.
Usa o espelho oficial das imagens no Docker Hub, pois ECR foi bloqueado na rede
do ambiente de desenvolvimento. O primeiro download pode levar vários minutos.

Conta: `nexo-test@example.invalid`. A senha aleatória e as chaves ficam somente
em `private.json`, fora do checkout, com permissões restritas. Não copie esse
arquivo, os arquivos de assinatura ou logs privados para o GitHub. Os scripts
não usam credenciais administrativas de um projeto remoto.

O segundo comando inicia o Edge Runtime local e utiliza o SDK real do Supabase
e o HTML do PR. Os identificadores públicos são adaptados **em memória** para
o projeto local; os arquivos do aplicativo não são reconfigurados para testes.
Um cliente OAuth temporário é criado e removido ao terminar. O callback HTTPS
do cliente fictício é interceptado no navegador; nenhum código é enviado ao
ChatGPT ou a um domínio externo.

Valida aprovação, recusa, consentimento anterior, identidade, `state`, PKCE,
rejeição da reutilização de código e integração com a função MCP recuperada.
A função preserva `jwtVerify` com assinatura ES256/RS256, emissor, público e
campos obrigatórios. Requisições sem token, com token inválido, token de login
sem `client_id`, assinatura alterada e seis variações de claims são recusadas.
Verifica `initialize`, confirmação, `tools/list` e somente `testar_conexao`,
cujo código fornecido não acessa dados financeiros. Não chama outras ferramentas
existentes. Não usa JWT inventado para demonstrar sucesso: o token válido vem
da troca real do código OAuth no Auth local.

O gateway local permite alcançar os metadados públicos da função
(`verify_jwt = false` somente no diretório local). Isso **não** desabilita a
verificação JWT da função: cada POST continua sujeito ao verificador original.
O teste confirma essas rejeições. Nenhuma configuração remota é alterada.

O CLI mantém o banco local em Docker. Para encerrá-lo, sem apagar volumes:

```sh
/workspace/nexo-test-environment/bin/supabase --workdir /workspace/nexo-test-environment stop
```

Processos não sobrevivem necessariamente a uma nova tarefa; repita os comandos
de preparação. Cada tarefa do Codex é isolada: use o checkout existente e não
crie worktrees sem solicitação explícita.

## Origem da função e dados fictícios

`tests/fixtures/nexo-mcp-test-v2.ts` preserva exatamente o arquivo recuperado e
fornecido pelo responsável. SHA256:
`70eb6c1a53de3c2770ec2f91319aece2e76f98f083d5818d5c5df443254e206d`.
`tests/integration/nexo-mcp-test/index.ts` altera somente configuração local:
emissor, recurso, endereço interno do JWKS e exigência de modo local explícito.
Um teste compara essa adaptação com o fonte recebido para impedir alterações
silenciosas na autenticação ou no comportamento da função.

`tests/fixtures/nexo-synthetic.json` contém receitas e despesas inteiramente
fictícias no formato do front-end existente. A preparação copia a fixture para
o diretório local, mas não inventa tabelas nem importa em um esquema desconhecido.
A função recebida não usa tabelas. O esquema real de `nexo_data` não consta
nas branches/histórico inspecionados; testes de operações financeiras dependem
de suas migrações e RLS reais, e não são necessários para `testar_conexao`.

## GitHub Actions

`.github/workflows/oauth-tests.yml` executa automaticamente em Pull Requests e
pushes para `main`. Atualizações da branch do PR disparam o evento do PR, sem
duplicar execuções por push. Há dois jobs: regressão e integração real
local em Docker. Ambos usam Python 3.12 e dependências fixadas. As actions estão
fixadas por SHA, o token tem somente `contents: read`, e nenhum segredo de
produção ou artefato com credenciais é utilizado. Não há etapa de deploy.
Os testes locais encerram sua instância Docker ao final do job.

## Validação futura dentro do ChatGPT

O ensaio local não comprova a configuração do conector do ChatGPT. Para esse
último passo é necessário um endpoint HTTPS de testes acessível pelo ChatGPT,
um cliente OAuth registrado para ele e uma conta exclusiva de testes. A sessão
local em loopback não deve ser exposta publicamente por improvisação.

Após existir um projeto remoto exclusivo, o comando abaixo verifica descoberta
sem autenticação e, opcionalmente, inicialização e lista autenticadas:

```sh
python -m tools.check_mcp_test --url https://REF.supabase.co/functions/v1/nexo-mcp-test --test-project-ref REF
python -m tools.check_mcp_test --url https://REF.supabase.co/functions/v1/nexo-mcp-test --test-project-ref REF --authenticated
```

O segundo comando lê `NEXO_TEST_OAUTH_ACCESS_TOKEN` e `NEXO_TEST_USER_ID` de
variáveis seguras; nunca informe seus valores na linha de comando ou no chat.
Use um token **OAuth**, não um token de login por senha. O programa confere a
identidade no servidor OAuth antes de listar ferramentas e nunca faz `tools/call`.
O projeto atualmente usado pelo NEXO é bloqueado explicitamente nesse utilitário.

Nenhum projeto remoto foi criado: não há autenticação administrativa Supabase
disponível e a criação também depende de organização, região e limites da conta.
Essas decisões são dispensáveis para executar os testes locais acima.
