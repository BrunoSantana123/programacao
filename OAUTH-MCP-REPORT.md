# Correção do consentimento NEXO / ChatGPT

## Diagnóstico confirmado

O arquivo `oauth-consent.html` interrompia toda solicitação antes de autenticar:
`TRUSTED_CLIENT_ID` e `TRUSTED_CALLBACK` estavam vazios. Isso impedia concluir
o consentimento por esta página, mas não comprova a origem do 401 do MCP.

Os identificadores públicos fornecidos pelo responsável foram configurados em
`oauth-config.js`: Client ID `451c10f2-5062-45a7-b4df-94664ecf212c` e callback
`https://chatgpt.com/connector/oauth/jtfRMxXsq31B`. O parâmetro de rastreamento
`utm_source` presente nos links da mensagem não integra a URI registrada.
Nenhum Client Secret é necessário ou permitido nesses arquivos públicos.

A versão usada de `@supabase/supabase-js` (2.119.0) declara `client.id` nos
detalhes de autorização. Esse campo estava correto e foi preservado. Os tipos
do SDK foram consultados em `@supabase/auth-js@2.119.0/dist/module/lib/types.d.ts`.

## Correções

- Configuração pública separada, mantendo bloqueio quando ausente ou inválida.
- Conferência da identidade do cliente, do usuário autenticado e da solicitação
  retornados pelo Supabase antes de exibir o consentimento.
- Correspondência completa do callback nos detalhes de autorização, incluindo
  parâmetros registrados. Antes só se comparavam origem e caminho.
- Retornos de aprovação, recusa e consentimento anterior aceitam somente o destino
  confiável e parâmetros OAuth conhecidos; rejeitam credenciais na URL,
  fragmentos, HTTP, destinos diferentes, parâmetros inesperados/duplicados e
  combinações ambíguas de código e erro. Parâmetros registrados são preservados.
- `state` é repassado sem alteração; a validação de seu valor pertence ao cliente
  OAuth. A página não gera códigos, tokens ou redirecionamentos por conta própria.

Sessões continuam sem persistência no navegador. Não foram alterados dados
financeiros, RLS, políticas SQL, validação de JWT ou configuração de Edge Functions.

## Testes executados

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`

Resultado: **14 testes passaram** em Chromium headless, com Playwright Python.
Cobertura: solicitação ausente/inválida, configuração ausente, falha de login,
aprovação, recusa, cliente/usuário/solicitação divergentes, URI divergente,
destino malicioso, falha ao decidir, consentimento anterior e política de URLs.
As respostas do SDK são simuladas e toda saída de rede não autorizada no teste
é bloqueada. Nenhuma conta real ou dado remoto é usado. Testes requerem o pacote
Python `playwright` e Chromium em `/usr/bin/chromium`, disponíveis neste ambiente.

`git diff --check` passou. Os programas financeiros e suas bases não foram modificados.

## Limitação do diagnóstico remoto

O repositório não contém a implementação do servidor MCP, configuração de Edge
Functions, migrações ou logs do servidor. O endpoint informado é
`https://tznebgdgdqpbhjdrhprb.supabase.co/functions/v1/nexo-mcp-test`.

Tentativas de acesso a esse endpoint e à descoberta OpenID do Supabase falharam
com `Tunnel connection failed: 403 Forbidden`. Esse erro é do proxy deste
ambiente, não uma reprodução do 401 relatado pelo ChatGPT. A inclusão do domínio
Supabase já está salva no rascunho de rede do ambiente; precisa ser aplicada nas
configurações antes de validar remotamente. Nenhum token foi solicitado ou enviado.

Não foram validados contra o serviço real: descoberta OAuth/MCP, troca do código
por token, `initialize`, `notifications/initialized`, `tools/list` e chamadas de
ferramentas. Portanto não se afirma que o 401 ou a ausência de ferramentas estejam
resolvidos. Credenciais não devem ser enviadas pelo chat.

## Publicação e validação restante

Publicar juntos `oauth-consent.html`, `oauth-config.js` e `oauth-policy.js` no
mesmo diretório do site. Incluir os testes e este relatório no GitHub. Nenhum
push, deploy ou alteração remota foi realizado nesta tarefa.

Depois de liberar o domínio no ambiente, conferir a configuração efetiva do
Supabase e obter o código/configuração da função MCP para continuar o diagnóstico:

1. Confirmar OAuth Server habilitado, URL da página de consentimento e o mesmo
   registro de cliente/callback nas configurações do Supabase e do ChatGPT.
2. Inspecionar a resposta MCP sem autenticação e o desafio `WWW-Authenticate`:
   401 pode ser esperado antes de obter um token; isoladamente não indica defeito.
   Conferir metadados do recurso protegido, servidor de autorização, issuer,
   endpoints e escopos anunciados. Distinguir rejeição no gateway de rejeição pela função.
3. Concluir OAuth com uma conta de teste autorizada, verificando `state`, PKCE e
   troca de código sem registrar códigos, tokens ou segredos em logs.
4. Com token apropriado, executar a inicialização MCP e `tools/list`, preservando
   cabeçalhos e sessão exigidos pelo transporte. Registrar somente status e nomes
   de ferramentas. Não executar ferramentas financeiras para testar descoberta.
5. Se ainda ocorrer 401, correlacionar logs sanitizados do gateway/função com a
   requisição; conferir issuer, audience, validade, escopos e verificação de JWT.
   Não desabilitar autenticação, RLS ou validação de assinatura como solução.

O nome do conector ser reconhecido não demonstra que `tools/list` foi concluído.
O resultado depende do servidor MCP e do fluxo autenticado, além desta página.
