# Pacote de produção — NEXO-APP

Destino: projeto **NEXO-APP**, referência `tznebgdgdqpbhjdrhprb`.
Site oficial: https://brunosantana123.github.io/programacao/.

Os arquivos estão na branch **`fix/nexo-oauth-consent`**, no **PR #1**. Enquanto o
PR não for integrado, abrir `main` não mostra este pacote. Este documento orienta
a operação pela conexão administrativa Supabase já disponível ao responsável;
não solicita que sejam enviadas credenciais ao chat. Adicionar arquivos ao GitHub
não aplica SQL, não publica a Edge Function e não atualiza o GitHub Pages.

## Arquivos necessários — uma única fonte por componente

| Arquivo no repositório | Uso |
| --- | --- |
| `supabase/production/00_preflight.sql` | Conferir esquema, RLS, privilégios e existência da função, sem consultar registros |
| `supabase/migrations/20261115000100_registrar_lancamento.sql` | Instalar somente a função transacional de gravação e suas permissões |
| `supabase/production/02_verify_install.sql` | Conferir instalação e permissões, sem gravar lançamentos |
| `supabase/functions/nexo-mcp-test/index.ts` | Servidor MCP: OAuth, ferramentas e acesso individual |
| `supabase/functions/nexo-mcp-test/finance.mjs` | Cálculos/consultas e validação dos recibos; precisa acompanhar `index.ts` |
| `oauth-consent.html`, `oauth-config.js`, `oauth-policy.js` | Consentimento e lista de pares cliente/callback confiáveis |
| `index.html`, `nexo-teste.html` | NEXO com atualização de lançamentos externos e autenticação oficial preservada |
| `auth-config.js`, `auth-client.js`, `confirmar.html`, `confirm-email.js`, `recuperar.html`, `recovery.js` | Arquivos de cadastro, confirmação e recuperação já incorporados à branch |
| `CONFIGURAR-EMAIL-NEXO.md` | SMTP e confirmação/recuperação de e-mail |
| `CHATGPT-INTEGRACAO.md` | Relatório técnico, testes e conexão de outro usuário |

A definição original da tabela e RLS está em
`tests/integration/nexo-data-schema.sql`, **somente como referência/fixture local**.
Não executar esse arquivo em produção. Não recriar a tabela nem as políticas.
Consultas de saldo e movimentações usam a leitura existente com RLS e não precisam
de novas tabelas, funções SQL ou migrações adicionais.

## 1. Conferir antes de instalar

Na conexão administrativa, selecionar explicitamente NEXO-APP e executar
`00_preflight.sql`. O script inicia uma transação de leitura e termina com ROLLBACK;
não exporta linhas financeiras. Conferir:

- Tabela `public.nexo_data`, PK `user_id` uuid ligada a `auth.users(id)`, `data` jsonb
  obrigatório com default `{}` e `updated_at` timestamptz obrigatório.
- RLS habilitada. Políticas SELECT/INSERT/UPDATE/DELETE para `authenticated`,
  restringindo a identidade a `auth.uid() = user_id`, inclusive WITH CHECK em escrita.
  Considerar todas as políticas: uma política permissiva adicional pode ampliar acesso.
- Permissões compatíveis com o esquema fornecido. Não remover acessos administrativos
  de postgres/service_role nem ampliar acesso anônimo para resolver erro.
- Se a função `nexo_registrar_lancamento` já existir, examinar sua definição no painel
  e comparar com a migração revisada. O hash do preflight apenas identifica a versão;
  não comprova equivalência. Não substituir uma implementação desconhecida sem revisão.

Se houver divergência, interromper a instalação e revisar; não reparar dados nem
políticas automaticamente. A migração pressupõe a tabela existente e não é bootstrap.

## 2. Instalar SQL e conferir permissões

Executar **somente** o conteúdo de
`supabase/migrations/20261115000100_registrar_lancamento.sql` no SQL Editor ou pela
conexão administrativa. A migração tem BEGIN/COMMIT próprios. Não a envolver em
outra transação e não executar todos os SQL do repositório indiscriminadamente.

A função é SECURITY INVOKER, deriva o dono de `auth.uid()`, valida campos, serializa
as gravações da conta e preserva histórico. Não aceita `user_id` como argumento.
O UUID permite repetir a mesma operação sem duplicação. A instalação não executa
a função nem escreve lançamentos de usuários.

Depois, executar `02_verify_install.sql`. Esperado:

- `funcao_instalada = true` e exatamente uma linha de metadados da função.
- `executa_com_permissoes_do_usuario = true`, retorno jsonb e search_path vazio.
- `authenticated_pode_executar = true`, `anon_bloqueado = true`, `public_bloqueado = true`.
- RLS habilitada e políticas da tabela preservadas em relação ao preflight.

Essas conferências não substituem o teste real de isolamento entre duas contas.

## 3. Publicar o MCP

Publicar **os dois arquivos**, no nome **`nexo-mcp-test`**, preservando o endpoint:

`https://tznebgdgdqpbhjdrhprb.supabase.co/functions/v1/nexo-mcp-test`

Usar a conexão administrativa de Edge Functions ou CLI Supabase já autenticada.
Na CLI, a partir da raiz desta branch:

```sh
supabase functions deploy nexo-mcp-test --project-ref tznebgdgdqpbhjdrhprb --no-verify-jwt
```

O flag é específico desta função: o gateway legado não valida o token OAuth ES256
como o verificador próprio. **Não desativar a validação JWT no código nem globalmente.**
`index.ts` exige assinatura ES256/RS256, issuer, audience, expiração, role e client_id.
Se a configuração atual do gateway já permite chegar ao verificador próprio,
preservar o comportamento equivalente. Nunca publicar o fonte original v2 do arquivo
`tests/fixtures/`: ele não contém as quatro ferramentas financeiras atuais.

Configuração de execução:

- `NEXO_OAUTH_CLIENT_IDS`: `451c10f2-5062-45a7-b4df-94664ecf212c`, mais apenas os
  outros clientes efetivamente registrados e aprovados, separados por vírgula.
- `SUPABASE_URL`: fornecida pelo ambiente do próprio NEXO-APP.
- `SUPABASE_ANON_KEY`: chave pública fornecida pelo ambiente Supabase. Não substituir
  por `service_role` ou outra chave administrativa nas operações financeiras.
- Não configurar `NEXO_TEST_MODE=local` nem copiar `local-functions.env`/`private.json`.
- Client Secret e credenciais de administração ficam somente nas conexões/painéis
  seguros, nunca no GitHub, no frontend, em argumentos públicos ou em logs.

As ferramentas esperadas são `testar_conexao`, `registrar_lancamento`,
`consultar_saldo` e `consultar_movimentacoes`. Uma publicação do frontend não instala
esta função; publicar apenas `index.ts` sem `finance.mjs` também é insuficiente.

## 4. Conferir OAuth e publicar o frontend validado

No OAuth Server do NEXO-APP:

- Consentimento: `https://brunosantana123.github.io/programacao/oauth-consent.html`.
- Client ID confirmado: `451c10f2-5062-45a7-b4df-94664ecf212c`.
- Callback exata: `https://chatgpt.com/connector/oauth/jtfRMxXsq31B`.
- Usar Authorization Code com PKCE S256. Se o ChatGPT solicitar Client Secret,
  configurar exclusivamente no painel seguro correspondente.

`oauth-config.js` já contém esse par. Para outra instalação de desenvolvimento que
receba outro Client ID/callback, registrar o par exato no Supabase, em TRUSTED_CLIENTS
no frontend e na allowlist do MCP. Não cadastrar um cliente por usuário quando todos
usam o mesmo app compartilhado: cada pessoa autentica a própria conta NEXO.

A publicação do site oficial usa GitHub Pages, `main`, pasta `/`. Integrar a branch
validada somente na etapa autorizada de publicação; não basta enviar os arquivos
para esta branch. Preservar os arquivos de cadastro/recuperação listados acima.
Não apontar o site para um projeto de homologação. Conferir o deploy do Pages.

Para SMTP, seguir `CONFIGURAR-EMAIL-NEXO.md`, mantendo confirmação obrigatória.
Não usar confirmação administrativa em massa nem desligar e-mails para contornar SMTP.

## 5. Validação real e conexão de outra pessoa

1. Usar duas contas NEXO de teste próprias, confirmadas por e-mail, e duas contas
   independentes ChatGPT com permissão para conectar o app. Conferir o plano e as
   regras do workspace na interface vigente.
2. Na conta ChatGPT de cada pessoa, conectar o app NEXO disponível para ela. Em
   instalação de desenvolvimento, cadastrar o endpoint MCP acima e OAuth; conferir
   se o registro usa o par existente ou exige autorizar outro par conforme a etapa 4.
3. Entrar no consentimento com a conta NEXO da própria pessoa e conferir o e-mail.
   Atualizar/reconectar o NEXO Test para carregar a nova lista de ferramentas e revisar
   as permissões de consulta e gravação. Nunca compartilhar sessão ou token da outra conta.
4. Conferir descoberta pública (metadata HTTP 200), token OAuth e as quatro ferramentas.
   Requisição sem OAuth deve retornar 401 com WWW-Authenticate; isso é esperado.
   Token de login comum ou service_role não substitui o token OAuth da integração.
5. Com dados fictícios, registrar receita de R$ 150 e despesa de R$ 32,50 com categoria
   explícita. Aguardar recibo, consultar saldo/movimentações e conferir o mesmo registro
   no NEXO, no celular e computador. Em caso de retry, usar o mesmo UUID e argumentos.
6. Repetir com a segunda pessoa e descrição exclusiva. Conferir que cada conta vê
   exclusivamente seus registros. Não testar contra dados de clientes reais.
7. Testar ditado na caixa de mensagem, revisar transcrição e enviar. Confirmar que
   houve chamada da ferramenta e recibo, não apenas uma resposta de intenção.
   Conversa de voz ao vivo e reprodução por áudio dependem do suporte do ChatGPT e
   **não estão certificadas**. Não anunciar esse modo como concluído.
8. Testar cadastro, confirmação e recuperação por e-mail após configurar SMTP.
9. Registrar resultado e versão publicada sem copiar tokens, senhas ou dados financeiros
   de pessoas reais. Só então liberar uso financeiro real.

Não executar as ferramentas `setup_local_test`/`validate_*_local` apontadas para produção.
Elas recusam esse destino e são ensaios locais. Não executar scripts de limpeza/reset
em produção. A checagem pública não substitui os ensaios autenticados acima.

## Evidência já disponível

No commit `536c5f1`: 108 regressões aprovadas e ensaios reais locais de OAuth,
renovação, MCP, duas contas isoladas, gravação/consulta, concorrência e recuperação.

- https://github.com/BrunoSantana123/programacao/actions/runs/43753427596
- https://github.com/BrunoSantana123/programacao/actions/runs/43753427585

Essa evidência é local/CI, não uma certificação de deploy ou voz no ChatGPT real.
