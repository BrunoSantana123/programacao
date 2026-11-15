# Relatório técnico — OAuth e ambiente isolado NEXO

## Resultado e escopo

A página de consentimento tinha Client ID e Redirect URI vazios e interrompia
qualquer autorização antes do login. O PR configura os identificadores públicos
confirmados pelo responsável, reforça a validação de retornos e trata falhas no
carregamento. Não inclui Client Secret, tokens, senhas ou chaves privadas.

A função `nexo-mcp-test`, recuperada pelo responsável, foi incorporada como
referência original e como adaptação estritamente local. Não foi reconstruído
nenhum serviço ou esquema financeiro por suposição.

## Correções da revisão

- Importações dinâmicas permitem tratar configuração/política ausente, módulo
  inválido, SDK indisponível e timeout de 15 segundos. A página exibe falha e
  mantém login/consentimento ocultos, em vez de ficar em “Verificando…”.
- Testes verificam argumentos de login, identificador da solicitação, ação de
  aprovação/recusa e `skipBrowserRedirect: true`, além do destino final.
- Testes adicionais cobrem solicitação expirada, resposta ausente, retorno
  malicioso após consentimento anterior, texto não executável, armazenamento
  vazio e proteção contra uso remoto da API administrativa de testes.
- Chromium usa a instalação gerenciada pelo Playwright; o executável pode ser
  selecionado por `NEXO_CHROMIUM_EXECUTABLE`, sem caminho obrigatório no código.
- Dependências fixadas e GitHub Actions automatizam regressão e integração real
  em Docker. Actions fixadas por SHA, token com `contents: read`, sem segredos de
  produção, sem artefatos com credenciais e sem etapa de deploy.

## Evidências de execução

| Verificação | Resultado |
| --- | --- |
| Regressão no Codex | 38 testes passaram |
| Regressão GitHub Actions no commit `462ccf0` | 35 testes passaram; os três testes adicionais de segurança foram executados localmente depois |
| Supabase Docker + conta fictícia no GitHub Actions | Job de integração passou |
| OAuth real com SDK e Auth locais | Aprovação, recusa, consentimento anterior, identidade, state, PKCE e rejeição de reutilização de código passaram no job integrado |
| MCP recuperado em Edge Runtime local | Descoberta, initialize, confirmação, tools/list e testar_conexao passaram no job integrado |
| Rejeições JWT locais | Sem token, token inválido, token de login sem client_id, assinatura alterada e seis variações de claims recusadas |
| Whitespace e YAML | git diff --check e leitura sintática do workflow passaram |

Execução confirmada: https://github.com/BrunoSantana123/programacao/actions/runs/43679089467
Ambos os jobs concluíram com `success`. O acesso aos arquivos de logs do GitHub
foi bloqueado pelo proxy; os estados dos jobs e de todas as etapas foram
confirmados pela API. Os scripts não aceitam uma lista vazia de ferramentas ou
uma autenticação não executada como sucesso integrado.

A instalação da instância Docker do próprio Codex continua em avaliação de
recursos: o driver `vfs` esgotou o disco ao extrair Postgres 17. A tentativa foi
interrompida, o espaço foi recuperado e a imagem oficial Postgres 15 está sendo
preparada. Essa limitação da máquina não deve ser confundida com o job integrado
que já passou em um runner isolado do GitHub.

Comandos completos e preparação reproduzível: [TESTING.md](TESTING.md).

## Conta, fixtures e origem do código

O preparador cria `nexo-test@example.invalid` exclusivamente no Auth local,
com senha aleatória, e verifica o login. Nas execuções seguintes reutiliza a
conta e não reseta o banco. As credenciais ficam em arquivo privado fora do
checkout; no CI o diretório é temporário e não é publicado como artefato.

A fixture `nexo-synthetic.json` contém apenas dados fictícios e é copiada para o
diretório local. Não foi importada em tabelas desconhecidas. A função recebida
não consulta banco: só busca JWKS para verificar tokens e oferece a ferramenta
inofensiva `testar_conexao`. Portanto, um esquema financeiro não é necessário
para validar essa função. Migrações/RLS de funcionalidades financeiras não
foram encontradas no repositório, histórico e branches inspecionados.

O arquivo recebido foi preservado em `tests/fixtures/nexo-mcp-test-v2.ts`, SHA256
`70eb6c1a53de3c2770ec2f91319aece2e76f98f083d5818d5c5df443254e206d`.
Um teste confirma o checksum e que a adaptação muda somente configuração local:
emissor/recurso em loopback, JWKS pela rede interna Docker e exigência de modo
local explícito. JWT e comportamento das ferramentas permanecem iguais ao fonte.

## Segurança e impacto financeiro

- Nenhuma conta, cliente OAuth, política RLS, chave ou dado de produção foi alterado.
- Nenhuma mudança em cálculos, telas ou arquivos financeiros do aplicativo.
- O cliente OAuth temporário é criado e removido somente no Auth local.
- O gateway local permite alcançar os metadados públicos da função; a função
  preserva a verificação de assinatura ES256/RS256, issuer, audience, exp, sub,
  role e client_id. Os testes negativos confirmam a rejeição. Não foi desativado
  o verificador JWT da função, nem alterada configuração remota do gateway.
- Chaves assimétricas são geradas localmente e nunca entram no Git.
- Instalador verifica o checksum SHA256 oficial do CLI e mantém TLS. Docker
  verifica os downloads das imagens oficiais; usa-se o espelho oficial no Docker
  Hub porque o registro ECR foi bloqueado pela política de rede.
- O comando para validar um projeto remoto de testes bloqueia explicitamente o
  projeto atual do NEXO, não segue redirecionamentos, confere a conta no servidor
  OAuth e só inicializa/lista ferramentas. Não chama ferramentas financeiras.

## Reavaliação do 401 e da ausência de ferramentas

Na revisão, initialize e tools/list sem token retornaram 401 com
WWW-Authenticate e metadados acessíveis. As descobertas OAuth/OpenID responderam
200. Esse 401 é esperado antes da autorização, não prova defeito do MCP.

O fonte recuperado exige token OAuth com client_id; um token comum de login por
senha não é suficiente. A integração local confirmou essa diferença: o token
OAuth foi aceito e a ferramenta foi disponibilizada; o token de login foi
recusado. Isso fornece uma hipótese verificável para o problema original, mas
não identifica qual token o ChatGPT estava enviando naquela ocorrência.

Não foi executado login real dentro do conector ChatGPT, nem modificada sua
configuração. O ensaio usa um cliente local de testes e intercepta seu callback
no navegador, preservando state e usando a troca real do código no Supabase.
Não é uma certificação da configuração do conector remoto.

## Limites e intervenções

A suíte automatizada e a integração Docker funcionam sem credenciais humanas.
Para um ensaio final **dentro do ChatGPT**, é necessário disponibilizar um
endpoint HTTPS exclusivamente de testes e registrar o cliente/callback desse
conector. O projeto remoto não foi criado: não há autenticação administrativa
Supabase disponível, e organização/região/limites precisam ser definidos caso
se escolha esse caminho. Nada disso é pré-requisito para repetir os testes locais.

A função recebida é uma verificação de conexão, não um servidor financeiro
completo. Ela anuncia openid e confere audience authenticated/client_id, mas
não valida explicitamente o claim de escopo nem restringe um Client ID específico.
Essa característica foi preservada, não corrigida silenciosamente na cópia de
testes. Antes de acrescentar operações financeiras, é necessária uma revisão
própria de escopos, destinatários dos tokens, autorização por conta e RLS.

Nenhum merge ou deploy em produção foi realizado ou automatizado.
