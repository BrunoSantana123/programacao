# Relatório técnico — OAuth e ambiente isolado NEXO

## Resultado

O ambiente isolado foi preparado e validado no Codex. Supabase local em Docker,
conta fictícia, OAuth real e a função MCP recuperada passaram nos ensaios.
A preparação foi repetida sem recriar a conta nem resetar o banco.

O PR corrige o consentimento, que tinha Client ID e Redirect URI vazios, e suas
pendências de carregamento, testes e automação. Não contém Client Secret,
tokens, senhas, chaves privadas ou dados financeiros reais.

## Correções

- Configuração pública confirmada e conferência de cliente, conta, solicitação
  e endereço de retorno antes de autorizar a conexão.
- Importações dinâmicas com tratamento de rede, arquivo ausente, módulo inválido
  e tempo limite de 15 segundos. Falhas não deixam a página em “Verificando…”.
- Testes conferem os argumentos efetivos de login, consulta, aprovação e recusa,
  inclusive `skipBrowserRedirect`, além dos destinos de navegação.
- Cobertura de expiração, respostas ausentes, conteúdo não executável, URLs
  maliciosas, isolamento de credenciais, alterações indevidas no ambiente e
  preservação de serviços Docker que não pertencem ao teste.
- Chromium gerenciado pelo Playwright, com opção de executável externo, e
  dependências fixadas em `requirements-test.txt`.
- GitHub Actions com regressão e integração real em Docker, permissões mínimas,
  actions fixadas por SHA, sem segredos de produção e sem etapa de deploy.

## Resultados dos testes

| Verificação | Resultado |
| --- | --- |
| Regressão e segurança no Codex | 51 testes passaram; resultado do CI da revisão atual disponível nos checks do PR |
| Instalação Supabase no Codex | Postgres, Auth e gateway saudáveis; metadados REST responderam; login fictício passou |
| Repetição da preparação | Conta preservada, sem reset; arquivo privado com permissão 600 |
| OAuth real no Codex | Recusa, aprovação, consentimento anterior e identidade passaram |
| Proteções OAuth | State preservado; PKCE divergente e reutilização do código recusados |
| MCP real no Codex | Metadados, initialize, confirmação, tools/list e testar_conexao passaram |
| Rejeições de autenticação MCP | Sem token, token inválido, login sem client_id, assinatura alterada e seis variações de claims recusados |
| GitHub Actions | Regressão e integração real passaram nas execuções iniciais; cada atualização do PR executa novamente os dois jobs |
| Integridade do fonte | Checksum original e equivalência da adaptação local passaram |
| Configuração da imagem derivada | Configuração de execução inteira conferida contra a oficial, incluindo healthcheck |
| Arquivos financeiros | Sem mudanças em bot.py, gastos.py, index.html ou nexo-teste.html |

Evidências iniciais de CI com ambos os jobs aprovados:
- https://github.com/BrunoSantana123/programacao/actions/runs/43679089467
- https://github.com/BrunoSantana123/programacao/actions/runs/43679670775

Resultado da revisão mais recente: https://github.com/BrunoSantana123/programacao/pull/1/checks
Os arquivos brutos de logs do GitHub ficaram indisponíveis pelo proxy; os estados
individualizados dos jobs e etapas foram confirmados pela API. No Codex, os
ensaios integrados emitiram os resultados PASS diretamente, sem expor credenciais.
Não há testes ignorados ou resultados esperados de falha usados como aprovação.

Comandos reproduzíveis e limites: [TESTING.md](TESTING.md).

## Fonte recuperado e execução real

`tests/fixtures/nexo-mcp-test-v2.ts` preserva o arquivo fornecido pelo responsável.
SHA256: `70eb6c1a53de3c2770ec2f91319aece2e76f98f083d5818d5c5df443254e206d`.

A cópia executada altera somente configuração: emissor/recurso em loopback,
JWKS pela rede interna Docker e exigência de modo local explícito. Um teste
compara essa adaptação integralmente com o fonte original. Nenhum roteador MCP,
ferramenta ou esquema financeiro ausente foi reconstruído por suposição.

A função é executada pelo modo `--main-service` da imagem oficial Edge Runtime
v1.69.28. Porta e aliases seguem o gateway do CLI oficial 2.67.3. Isso dispensa
os imports deno.land do template genérico de `supabase functions serve` e mantém
cada POST sujeito ao verificador JWT original. Não é necessário desativar JWT.

O ensaio usa o HTML do PR e o SDK verdadeiro. Somente os identificadores públicos
são adaptados em memória para o projeto local. Um cliente OAuth temporário é
criado/removido no Auth local. O callback fictício é interceptado no navegador;
state é conferido, e o código é trocado por token no servidor Auth real.
Nenhum código é enviado ao ChatGPT ou a um domínio externo.

## Dados e segurança

A conta `nexo-test@example.invalid` tem senha aleatória, guardada em arquivo
privado fora do checkout. A preparação verifica seu login e preserva a identidade
em execuções seguintes. Credenciais locais, chaves e logs privados não entram no
Git, em imagens construídas ou em artefatos públicos do CI.

A fixture `nexo-synthetic.json` contém receitas/despesas inteiramente fictícias
no formato do front-end. É preparada em arquivo, sem inserir em tabelas cujo
esquema não foi fornecido. A função recuperada não usa banco: sua única ferramenta
é `testar_conexao`. Portanto, não é necessário inventar um esquema para validá-la.

JWT mantém assinatura ES256/RS256, issuer, audience, exp, sub, role e client_id.
Os casos negativos usam somente a chave privada gerada no projeto LOCAL e
confirmam rejeição no servidor real. Não há alteração de RLS ou de configuração
remota. Nenhum endpoint financeiro foi chamado.

O runtime recebe somente modo local e configuração de rede necessária. Não
recebe as chaves administrativas do Supabase usadas pelo preparador. Sua pasta
é montada em modo somente leitura; não há publicação de porta extra, privilégio
adicional ou encerramento de containers alheios.

O SDK é baixado por HTTPS verificado pelo cliente do Playwright com a confiança
fornecida à sessão e encaminhado ao navegador. São os bytes reais da biblioteca,
não respostas simuladas. Isso atende ao proxy do Codex sem alterar o banco de
certificados do Chromium nem usar ignore_https_errors ou desativar TLS.

## Recursos e rede do Codex

O driver Docker vfs multiplicou o uso de recursos ao extrair as camadas originais
do Postgres. O preparador, somente nesse driver e sem sobrescrever imagem já
existente, usa crane/umoci oficiais com checksum verificado para aplicar o layout
OCI fixado por digest e empacotar uma derivação local em uma camada. Preserva
conteúdo, hardlinks, proprietários, ACLs, xattrs e configuração de execução.
O original e o derivado têm identificadores distintos registrados em arquivo de
proveniência; não se altera checksum esperado para aceitar artefato inválido.
Nenhuma imagem é publicada e o daemon global não é modificado.

A rota já fornecida ao Docker e o bundle público de confiança da sessão são
reutilizados em arquivos privados externos ao Git. Exclusões existentes são
preservadas e somente serviços locais são acrescentados ao NO_PROXY. Arquivos
que contenham chave privada são recusados como bundle de CA.

A inclusão de deno.land, inicialmente proposta para o roteador genérico, foi
retirada do rascunho após validar o modo main-service. O fluxo final não precisa
de nova liberação de rede. Instruções reutilizáveis foram salvas em start_skill.
Salvar rascunho não publica nem aplica uma nova versão do ambiente.

## 401, ferramentas e limites do parecer

O 401 sem token é esperado e anuncia a descoberta de autorização. O fonte exige
token OAuth com client_id; um token comum de login por senha não é suficiente.
Isso foi confirmado no ensaio real: o token OAuth disponibilizou a ferramenta,
e o token comum foi recusado. Não comprova qual token o ChatGPT enviou na
ocorrência histórica, portanto não se afirma resolver conclusivamente aquele caso.

O ensaio isolado não certifica o conector dentro do ChatGPT. Esse último passo
exige um endpoint HTTPS exclusivo de testes e o consentimento pelo conector;
não foi realizado deploy remoto nesta tarefa.

A função fornecida é um teste de conexão, não um servidor financeiro completo.
Ela anuncia openid e confere audience authenticated/client_id, mas não valida
explicitamente o claim de escopo nem restringe um Client ID específico. Isso foi
preservado. Antes de acrescentar ferramentas financeiras, revisar escopos,
destinatários dos tokens, autorização por conta e as migrações/RLS reais.

Não há bloqueio humano para repetir a suíte isolada. A publicação de uma nova
versão do ambiente de desenvolvimento permanece sob controle do usuário.
Nenhum merge ou deploy em produção foi realizado ou automatizado.
