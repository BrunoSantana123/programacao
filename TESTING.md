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

No Docker com driver `vfs`, as camadas originais da imagem podem multiplicar o
consumo de disco e inodes. Apenas nesse caso, e se a imagem ainda não existir,
o preparador deriva uma cópia local em uma camada usando `crane` 0.22.1 e
`umoci` 0.6.0 oficiais, ambos com checksum verificado. A origem é fixada por
digest; o layout OCI é aplicado pelo umoci e empacotado com GNU tar, preservando
conteúdo, hardlinks Nix, proprietários, ACLs e xattrs. O container empacotador
também é fixado por digest, não tem rede, não recebe credenciais Supabase/GitHub nem privilégios
adicionais e monta somente o cache de arquivos públicos e o binário de leitura.
O preparador compara a configuração de execução inteira com a oficial,
incluindo healthcheck, entrypoint e variáveis, antes de iniciar os serviços.

Essa derivação tem um digest próprio e usa somente um alias no cache local do
Docker, esperado pelo CLI. Ela não é apresentada como o mesmo artefato binário
da imagem publicada. `postgres-image-provenance.json`, fora do Git, registra a
origem e os identificadores derivados. Nenhuma imagem é publicada e nenhuma
imagem existente é sobrescrita. Em `overlay2`, como nos runners do GitHub,
essa conversão é dispensada. Não é necessário alterar o daemon do Docker.

Conta: `nexo-test@example.invalid`. A senha aleatória e as chaves ficam somente
em `private.json`, fora do checkout, com permissões restritas. Não copie esse
arquivo, os arquivos de assinatura ou logs privados para o GitHub. Os scripts
não usam credenciais administrativas de um projeto remoto.

O segundo comando inicia a imagem oficial `supabase/edge-runtime:v1.69.28`,
usando o modo suportado `--main-service` para executar diretamente a função
fornecida. Porta 8081 e aliases seguem o gateway do CLI 2.67.3. Não há roteador
MCP reconstruído nem dependência do template genérico que importa `deno.land`.
Utiliza o SDK real do Supabase e o HTML do PR. Os identificadores públicos são adaptados **em memória** para
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

Os metadados públicos chegam diretamente à função pelo gateway local, e cada
POST continua sujeito ao verificador JWT original do fonte recuperado. Não se
utiliza opção para desativar verificação de JWT. O teste confirma essas rejeições.
Nenhuma configuração remota é alterada.

O CLI mantém o banco local em Docker. Para encerrá-lo, sem apagar volumes:

```sh
/workspace/nexo-test-environment/bin/supabase --workdir /workspace/nexo-test-environment stop
```

Processos não sobrevivem necessariamente a uma nova tarefa; repita os comandos
de preparação. Cada tarefa do Codex é isolada: use o checkout existente e não
crie worktrees sem solicitação explícita.

## Codex com rede restrita

O preparador reutiliza a rota de proxy já fornecida ao cliente Docker, preserva
as exclusões existentes e acrescenta somente os nomes dos serviços locais ao
`NO_PROXY`. Copia o bundle público de confiança da sessão para a pasta de funções,
montada pelo CLI em modo somente leitura, e configura `DENO_CERT`/`SSL_CERT_FILE`.
Recusa um arquivo que contenha chave privada e nunca desativa a validação TLS.
Não altera o proxy, o daemon nem a política de rede global. Valores do proxy
ficam somente no arquivo privado externo ao checkout; não devem ser impressos.

O template genérico do comando `supabase functions serve` depende de `deno.land`,
bloqueado na política desta instância. O ensaio usa o modo main-service oficial
e dispensa esse template; por isso a liberação inicialmente proposta foi retirada
do rascunho. Nenhuma ampliação da política é necessária para os testes aqui.

O Chromium usa a rota de proxy da sessão. Os módulos reais do SDK são recebidos
pelo cliente HTTPS do Playwright, com verificação de certificados e a confiança
fornecida ao Node, e encaminhados ao navegador. Isso evita alterar o banco de
certificados do Chromium ou desativar TLS. Não são respostas simuladas do SDK.

Em uma nova sessão, repita preparação e validação para atualizar proxy/CA e
conferir a cópia da função e a integridade do arquivo privado antes de iniciar
o Edge Runtime. Não edite esse arquivo à mão.

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
