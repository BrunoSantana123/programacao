> Pacote operacional completo: [supabase/production/README.md](supabase/production/README.md). O responsável informa que o ChatGPT possui acesso administrativo; a instalação pode ser executada por essa conexão usando os arquivos deste pacote.

# NEXO oficial + ChatGPT — integração e relatório técnico

## Estado desta entrega

Código preparado no PR #1, atualizado com a versão oficial de cadastro/recuperação
publicada pelo PR #2. Não foi executado novo merge ou deploy nesta entrega.
Nenhuma operação financeira autenticada foi realizada em produção.

O cliente OAuth confirmado foi reaproveitado, sem inventar outro registro:

- Projeto: NEXO-APP (`tznebgdgdqpbhjdrhprb`).
- Site: `https://brunosantana123.github.io/programacao/`.
- Consentimento: `https://brunosantana123.github.io/programacao/oauth-consent.html`.
- MCP: `https://tznebgdgdqpbhjdrhprb.supabase.co/functions/v1/nexo-mcp-test`.
- Client ID público: `451c10f2-5062-45a7-b4df-94664ecf212c`.
- Callback registrada: `https://chatgpt.com/connector/oauth/jtfRMxXsq31B`.

Esses identificadores não são credenciais privadas. Não incluir Client Secret,
senhas, tokens ou chaves administrativas em arquivos do frontend ou neste relatório.

## Diagnóstico OAuth/MCP em produção

Verificações públicas executadas, sem login nem consulta financeira:

| Verificação | Resultado |
| --- | --- |
| Protected resource metadata | HTTP 200; resource e issuer apontam para NEXO-APP |
| Authorization server metadata | HTTP 200; endpoints OAuth e PKCE S256 anunciados |
| JWKS | HTTP 200; chave pública ES256 |
| Início de autorização com o Client ID/callback confirmados e S256 | HTTP 302 para o consentimento no site oficial |

O par Client ID/callback está aceito pelo servidor. A página de consentimento da
versão oficial original ainda tinha configuração vazia; a configuração correta está
no candidato do PR #1. Não confundir um cadastro válido no Supabase com configuração
já publicada no HTML.

Um HTTP 401 **antes** de obter um token OAuth é esperado: o MCP exige autenticação.
O cliente precisa seguir `WWW-Authenticate` e o metadata para autorizar. Isso não
prova uma falha do serviço. Após autorizar, issuer, audience, assinatura, expiração,
role e client_id precisam ser válidos. Tokens de login comum e tokens administrativos
não substituem o token OAuth da integração.

A função v2 recuperada originalmente oferecia somente `testar_conexao`. A presença
do nome “NEXO Test” no ChatGPT, por si só, não comprova ferramentas financeiras.
A lista financeira efetivamente publicada ainda requer verificação autenticada após
o deploy correto; não foi presumida a partir do nome do app.

## Alterações implementadas

### Consentimento e múltiplos usuários

`oauth-config.js` contém os identificadores confirmados e uma lista explícita de pares
cliente/callback. `oauth-consent.html` aceita somente um par registrado, confere o
usuário retornado pelo servidor, a solicitação e o destino antes de autorizar/redirecionar.
Uma callback de um cliente não serve para outro. Configuração ausente ou duplicada
bloqueia autorização. Mantém timeout/erros de carregamento e tokens sem persistência.

Uma integração publicada pode atender muitos usuários com **o mesmo Client ID**.
O isolamento vem da conta NEXO autenticada em cada autorização, não de criar um cliente
por pessoa. Se outra pessoa criar sua própria instalação de desenvolvimento no ChatGPT,
pode receber outro Client ID/callback; nesse caso registrar o novo par exato no Supabase,
na lista do frontend e na allowlist do MCP. Nunca liberar callbacks/clientes arbitrários.
O retorno automático de autorização já aprovada continua limitado aos destinos confiáveis.

### Ferramentas MCP

| Ferramenta | Efeito |
| --- | --- |
| `testar_conexao` | Confirma autenticação, sem dados financeiros |
| `registrar_lancamento` | Receita/despesa, categoria, descrição e data na conta conectada |
| `consultar_saldo` | Saldo e totais em centavos de BRL, com período opcional |
| `consultar_movimentacoes` | Consulta por período, tipo/categoria e páginas de até 50 itens |

O saldo segue o NEXO: receitas menos despesas e reservas, mais resgates. Inclui o
formato legado de Uber/99/particulares e despesas, além dos lançamentos atuais.
Não é saldo bancário. Valores inválidos ou fora do intervalo seguro interrompem a
consulta; não são convertidos silenciosamente em um saldo fictício. Descrições e
categorias são dados, não comandos a executar.

O servidor valida JWT com JWKS ES256/RS256, issuer NEXO-APP, audience `authenticated`,
expiração, sub, role `authenticated` e Client ID permitido. Envia o JWT do próprio usuário
às operações sujeitas a RLS. Consultas também filtram o `user_id` derivado do JWT;
argumentos que tentam selecionar outra conta são recusados. Nenhuma escrita financeira
usa service_role. O resultado expõe campos financeiros selecionados, não agenda,
configurações ou dados pessoais do documento.

A gravação usa a função transacional já testada, com bloqueio da linha, UUID idempotente
e atualização compatível com o controle de concorrência do NEXO. Só acrescenta o novo
lançamento e a categoria. Não substitui os registros anteriores nem recria políticas.
O recibo precisa corresponder a ID, tipo, valor, categoria, descrição e data solicitados
antes de emitir confirmação de sucesso. Erros/timeout não geram “registrado”. A mesma
operação pode ser repetida com o mesmo UUID sem duplicação.

### Site oficial preservado

Cadastro, confirmação, reenvio e recuperação do PR #2 foram incorporados e testados
novamente. Mantida a proteção contra renovação atrasada de outra conta. O NEXO busca
lançamentos externos ao voltar à tela e a cada 15 segundos enquanto visível, sem
interromper formulário aberto. Histórico e documentos vazios não são sobrescritos no login.

## Voz: escopo comprovado e limite

O servidor recebe argumentos estruturados das ferramentas, não áudio. Pode processar
um lançamento escolhido pelo ChatGPT a partir de uma mensagem digitada ou ditada.
As respostas incluem confirmação textual baseada no recibo real; o servidor não produz
áudio nem consegue obrigar o ChatGPT a falar a resposta.

O caminho previsto é **ditado na caixa de mensagem**, revisão da transcrição e envio
com o NEXO conectado. Não confundir o botão de ditado com o modo de conversa de voz
ao vivo. Uso de apps/ferramentas durante voz ao vivo e confirmações de escrita dependem
do suporte vigente da interface/conta do ChatGPT; **não estão certificados nesta entrega**.
Também não foi testada a interpretação de áudio por duas contas reais do ChatGPT.

As páginas oficiais da OpenAI abaixo foram tentadas, mas o proxy desta sessão recusou
os domínios. Portanto não foi possível confirmar por consulta atual os planos elegíveis
nem uma mudança recente no suporte à voz. Não foi prometido suporte universal:

- https://developers.openai.com/apps-sdk/build/mcp-server
- https://help.openai.com/en/articles/11487775-connectors-in-chatgpt
- https://help.openai.com/en/articles/8400625-voice-mode-faq

## Testes executados

**Resultado executado: 108 testes de regressão aprovados.** A suíte cobre os fluxos
antigos e os novos cálculos/recibos. O ensaio real usa Supabase,
OAuth, JWT, PostgREST, RLS, função MCP e o HTML reais em Docker, com dados fictícios.
As duas contas abaixo são contas NEXO/Supabase independentes, **não duas contas ChatGPT**.

| Ensaio | Resultado local |
| --- | --- |
| Autorizar/negar, retorno previamente aprovado, state, PKCE errado/replay | Aprovado |
| Renovação OAuth real, seguida de acesso MCP com o novo token | Aprovado |
| Token ausente/alterado/expirado/issuer/audience/role/client errados | Recusados |
| Receitas/despesas, centavos, categoria e data São Paulo | Aprovado |
| UUID repetido e concorrência sem perda de histórico | Aprovado |
| Lançamentos aparecem no NEXO desktop/mobile | Aprovado |
| Duas contas OAuth: leitura e escrita exclusivamente próprias | Aprovado |
| Consulta MCP de saldo/movimentações por duas contas | Aprovado |
| Consulta não modifica documento nem updated_at | Aprovado |
| Tentativa de user_id alheio, paginação/data inválidas | Recusada |
| RLS direta: leitura, insert, update e delete entre contas | Bloqueados |
| Saldo legado/atual, reservas/resgates, período e paginação | Aprovado |
| Recibo divergente não gera confirmação financeira | Aprovado |
| Cadastro/confirmar e-mail/recuperar senha reais locais | Aprovado |
| Senha antiga e link de recuperação reutilizado | Recusados |
| Login preserva documento vazio e histórico anterior | Aprovado |

O teste de cálculo importa o mesmo `finance.mjs` utilizado pelo MCP. O ambiente recusa
um módulo financeiro diferente da cópia revisada. Nenhum teste usa dados de produção.
Entrega SMTP, duas contas reais ChatGPT e fala/ditado reais não foram certificados.

Comandos reproduzíveis:

```sh
python -m tools.setup_local_test --directory /workspace/nexo-test-environment
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m unittest discover -s tests -v
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_local_oauth --directory /workspace/nexo-test-environment
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_auth_local --directory /workspace/nexo-test-environment
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_recovery_local --directory /workspace/nexo-test-environment
```

Requer Node.js 18+ para os testes do módulo financeiro, além das dependências já
preparadas. GitHub Actions executa regressões e integração local; não faz deploy.

## Configurações/validações indispensáveis antes de liberar o uso oficial

1. **Acesso administrativo efetivamente disponível:** nenhuma ferramenta Supabase
   administrativa está exposta nesta sessão. A leitura da lista de secrets de Actions
   também retornou 403, portanto não foi possível confirmar uma rota de deploy com
   credencial já configurada. Não inserir credenciais no chat ou frontend.
2. **Pré-verificação de banco no NEXO-APP:** conferir tabela/RLS fornecidas pelo
   responsável e a existência/definição de `nexo_registrar_lancamento` antes de aplicar
   a migração. Se já existir uma função diferente, revisar sua definição antes de
   substituí-la. Não aplicar o SQL de fixtures nem resetar banco em produção.
3. **Aplicar somente a migração de função**
   `supabase/migrations/20261115000100_registrar_lancamento.sql`, após essa conferência.
   Ela não recria a tabela/políticas nem reescreve linhas existentes durante instalação.
4. **Publicar os dois arquivos da função** `index.ts` e `finance.mjs`, no nome
   `nexo-mcp-test`, após os testes e a pré-verificação. Preservar o nome/endpoint usado
   pelo NEXO Test. Configurar `NEXO_OAUTH_CLIENT_IDS` com os clientes realmente
   registrados. URL/chave pública vêm do próprio ambiente Supabase. Nenhuma chave
   administrativa é necessária nas operações financeiras.
5. O gateway não pode rejeitar tokens OAuth assimétricos antes do verificador da
   função. Conferir a configuração atual antes de alterar: a validação própria de
   assinatura/issuer/audience/expiração/cliente **deve permanecer obrigatória**.
   Se o gateway legado exigir ajuste, é exclusivamente nessa função, nunca global:
   o deploy CLI usa `supabase functions deploy nexo-mcp-test --project-ref
   tznebgdgdqpbhjdrhprb --no-verify-jwt`. Isso desativa apenas a checagem legada do
   gateway; não a autenticação dentro da função. Não alterar outras funções.
6. **OAuth Server:** manter consentimento na URL oficial acima e o par confirmado
   registrado. Client Secret, quando o ChatGPT solicitar, deve ficar somente nos
   painéis seguros do Supabase/ChatGPT. Nunca no GitHub.
7. **Publicar o frontend validado** do PR #1 no GitHub Pages. Não apontar o site para
   outro Supabase e não alterar as opções de cadastro/recuperação do PR #2.
8. **SMTP e contas de ensaio:** concluir o roteiro `CONFIGURAR-EMAIL-NEXO.md`, mantendo
   confirmação obrigatória. Provisionar duas contas de teste próprias/independentes,
   com caixas autorizadas, sem usar dados de clientes reais. Testar cadastro e
   recuperação por e-mail no ambiente oficial.
9. **Teste autenticado final no ChatGPT:** conectar as duas contas, conferir as quatro
   ferramentas, executar o roteiro abaixo e confrontar recibos/telas do NEXO. Só então
   considerar o serviço liberado para uso financeiro real. Não publicar backend sem
   pré-verificação nem anunciar voz ao vivo como validada.

## Como outro usuário conecta sua própria conta ChatGPT

Os nomes das opções podem variar por plano e workspace.

1. Criar a própria conta NEXO, confirmar o e-mail e conferir login no site oficial.
2. Na conta ChatGPT, verificar disponibilidade de Apps, permissões do workspace e
   instalações de desenvolvimento. Se faltar a opção, o administrador/gestor da conta
   deve verificar as regras e o plano; cadastrar OAuth não libera essa funcionalidade.
   Se a criação não aparecer no celular, realizar a configuração inicial no navegador
   do computador e depois verificar a disponibilidade do app no dispositivo móvel.
3. Se o app NEXO estiver compartilhado/publicado e disponível para aquela conta,
   selecionar **Conectar**, usando o mesmo app registrado, não a sessão de outra pessoa.
4. Se for ensaio de desenvolvimento e a conta permitir criar um app MCP, cadastrar
   o endpoint HTTPS NEXO acima, usando OAuth. Conferir os identificadores exibidos
   pelo ChatGPT: se criar outro registro/callback, o responsável deve autorizar esse
   novo par explicitamente nos três lugares (Supabase, frontend e allowlist MCP).
   Não reutilizar a callback de outra instalação por suposição.
5. No consentimento, entrar com **a própria conta NEXO**, conferir e-mail e permissões,
   e autorizar. Não compartilhar login, tokens ou sessão da primeira pessoa.
6. Conferir as ferramentas `testar_conexao`, `registrar_lancamento`, `consultar_saldo`
   e `consultar_movimentacoes`. Se só houver teste de conexão, conferir versão da função
   e atualizar/reconectar o app; se houver 401 após login, verificar o token OAuth e
   os registros do serviço sem expor o token.
7. Pelo ditado da caixa de mensagem, enviar “Registre receita de R$ 150 por serviço
   particular hoje” e “Registre despesa de R$ 32,50 com alimentação hoje”. Se a categoria
   ou outro dado estiver ambíguo, esclarecer antes de gravar. Permitir a ação de escrita
   quando o ChatGPT solicitar.
8. Aguardar o recibo efetivamente registrado. Pedir “Consulte minhas movimentações de
   hoje” e “Qual é meu saldo dos lançamentos de hoje?”. Conferir valores, categoria,
   data e recibos no NEXO, tanto no celular quanto no computador.
9. Repetir na segunda conta com descrição exclusiva. Nenhum registro da primeira pode
   aparecer na segunda. Repetir uma tentativa com o mesmo ID não pode criar duplicata.
10. Para disponibilização ampla, seguir o processo vigente de compartilhamento/revisão
    de apps da OpenAI e as regras do workspace. Uma instalação “NEXO Test” de
    desenvolvimento não equivale a um app distribuído para todas as contas ChatGPT.
