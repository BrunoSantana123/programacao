# Cadastro e recuperação — NEXO oficial / NEXO-APP

Endereço oficial confirmado: https://brunosantana123.github.io/programacao/.
Projeto confirmado: NEXO-APP (`tznebgdgdqpbhjdrhprb`).

## O que foi corrigido

- Cadastro envia o destino de confirmação explicitamente; mensagem orienta a
  confirmar o e-mail e conferir spam. Nova opção de reenviar confirmação.
- Página `confirmar.html` verifica a confirmação no Supabase e exige novo login.
- “Esqueci minha senha”, solicitação por e-mail, definição e confirmação de senha.
- Links padrão do Supabase (fragmento de sessão) e links customizados `token_hash`
  são aceitos. A sessão padrão é validada no servidor antes de qualquer alteração;
  a página não confia somente nos parâmetros recebidos.
- Tokens removidos da URL, sem armazenamento persistente. Links expirados,
  reutilizados ou de tipo errado são recusados. Senha de recuperação permanece
  disponível por até 15 minutos, respeitando o prazo menor da sessão.
- Nova senha/cadastro exigem 12–128 caracteres, maiúsculas, minúsculas, números
  e símbolos. O login continua aceitando senhas existentes. Configurar também a
  política do servidor, conforme abaixo.
- A recuperação tenta revogar globalmente as sessões após salvar e avisa caso
  não consiga confirmar a revogação. O usuário deve entrar novamente.
- Conta nova com documento financeiro exatamente `{}` abre o painel vazio **em
  memória**, sem sobrescrever o documento. Documentos inválidos não são apagados
  nem reconstruídos. Nenhuma migração ou alteração em RLS/tabelas é necessária.
- Resposta tardia da renovação de uma conta anterior não substitui outra sessão.
- Nenhuma alteração na função MCP ou nas demais funcionalidades pendentes do PR #1.

## Diagnóstico confirmado e limites

O endpoint público `/auth/v1/settings` do projeto respondeu HTTP 200:
cadastro habilitado, acesso por e-mail habilitado e confirmação obrigatória
(`mailer_autoconfirm=false`). Não foi desabilitada nenhuma proteção.

Não é possível determinar o motivo exato de uma falha SMTP usando a chave pública.
Não há ferramenta administrativa do Supabase ou credencial SMTP disponível nesta
sessão. A conexão mencionada no ChatGPT não está exposta às ferramentas desta tarefa.
Não foram disparados e-mails reais nem acessados dados de usuários de produção.
A ausência de SMTP foi informada pelo responsável; não foi inferida de um erro de rede.

## Configurações exatas no painel Supabase

Abra o projeto **NEXO-APP**. Os nomes das seções podem variar conforme a versão do painel.

1. **Authentication → Providers / Sign In → Email**:
   - Email provider: habilitado.
   - Confirm email: **habilitado**, mantendo a confirmação obrigatória.
   - Não alterar usuários já existentes nem confirmar contas em massa.
2. **Authentication → URL Configuration**:
   - Site URL: `https://brunosantana123.github.io/programacao/`.
   - Adicionar Redirect URLs exatas:
     - `https://brunosantana123.github.io/programacao/confirmar.html`
     - `https://brunosantana123.github.io/programacao/recuperar.html`
   - Preservar URLs legítimas de OAuth/ChatGPT e demais destinos existentes.
     Não substituir a lista inteira nem adicionar curingas para contornar erros.
3. **Authentication → Email / SMTP Settings → Custom SMTP**:
   - Ativar custom SMTP.
   - Sender email: endereço verificado no provedor escolhido, por exemplo um
     endereço do domínio que você controla. Não usar um remetente inventado.
   - Sender name: `NEXO`.
   - Host: servidor SMTP fornecido pelo provedor (não é a URL do Supabase).
   - Port: a porta TLS/STARTTLS recomendada pelo provedor, normalmente 465/587.
   - Username e password: credenciais SMTP do provedor, inseridas **somente no painel**.
   - Manter transporte seguro e limites de envio; não colocar a senha em GitHub,
     HTML, Vercel ou no chat. Não é preciso alterar a chave pública do aplicativo.
   - Confirmar domínio/remetente no provedor e publicar os registros SPF/DKIM
     indicados por ele; verificar DMARC. Se o provedor estiver em modo sandbox,
     autorizar a caixa de teste ou obter liberação para os destinatários reais.
4. **Authentication → Email Templates**:
   - Confirm signup: manter botão/link com `{{ .ConfirmationURL }}`.
   - Reset password: manter botão/link com `{{ .ConfirmationURL }}`.
   - Não misturar os modelos. Os links padrão agora funcionam; não é obrigatório
     substituir os templates. Preservar conteúdo/identidade existentes.
   - Caso já use links customizados, os destinos corretos são:
     - Cadastro: `https://brunosantana123.github.io/programacao/confirmar.html?token_hash={{ .TokenHash }}&type=signup`
     - Recuperação: `https://brunosantana123.github.io/programacao/recuperar.html?token_hash={{ .TokenHash }}&type=recovery`
     - Em HTML, escrever o separador como `&amp;` dentro do atributo `href`.
   - Desativar rastreamento/reescrita de links de autenticação no provedor de e-mail,
     se habilitado; não desabilitar a confirmação ou expiração dos links.
5. **Authentication → Password / Security**:
   - Política do servidor: mínimo 12 caracteres, maiúsculas, minúsculas, números
     e símbolos. A regra vale para novas definições de senha; não redefinir senhas
     existentes em massa. Preservar expiração de OTP, limites e demais proteções.
   - Se houver CAPTCHA já obrigatório, informar a configuração pública da integração
     para incorporá-la; não desligar o CAPTCHA para contornar falhas.
6. **Auth Logs e painel do provedor de e-mail**:
   - Verificar rejeição SMTP, remetente não verificado, bloqueio de destinatários,
     credenciais incorretas, limite de envio, bounce, spam ou supressão.
   - Não compartilhar links, tokens, senhas ou conteúdo financeiro dos registros.

As configurações Host/Port/Username/Password dependem do provedor contratado;
não podem ser preenchidas corretamente por suposição. O SMTP padrão do Supabase
pode restringir destinatários e ter limites baixos; verificar o plano/configuração.

## Publicação

O NEXO oficial está configurado no GitHub Pages, branch `main`, pasta `/`.
Esta correção é preparada em branch própria a partir de `main`, sem juntar as
alterações amplas do PR #1. A publicação do código depende de testes aprovados e
atualização dessa branch principal. A autorização para publicar foi dada pelo
responsável nesta solicitação. Nenhuma publicação na Vercel é necessária para o
endereço oficial confirmado.

SMTP e URLs do Auth são configurados separadamente no Supabase: publicar o HTML
não configura o remetente. Portanto a publicação do frontend, sozinha, não certifica
cadastro/recuperação reais com entrega de e-mail.

## Testes

```sh
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m unittest discover -s tests -v
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_auth_local --directory /workspace/nexo-test-environment
```

**Resultado local: 25 testes de navegador aprovados.** O ensaio real local
também passou, incluindo preservação de documento vazio e histórico financeiro
com propriedades extras. A suíte de navegador testa cadastro, reenvio, confirmação, senha forte, erros em
português, dois formatos de link, validação no servidor, expiração, reuso/links
inválidos, limpeza de tokens, falha de rede/revogação e layouts móveis/computador.
Requisições externas são interceptadas; não chama produção. GitHub Actions executa
essa suíte em PRs e em `main`.

O ensaio real exige o Supabase local já disponível. Usa somente API em loopback,
conta fictícia temporária e tokens reais gerados pela API local. Verifica bloqueio
antes da confirmação, confirmação, recuperação, senha antiga recusada, reuso
recusado, novo login e preservação de documento vazio. Exclui a própria conta ao
final; não desativa confirmação nem altera dados de contas existentes.

Depois de configurar SMTP, executar em uma caixa autorizada e com dados fictícios:

1. Criar uma conta nova; conferir que não entra antes de confirmar.
2. Receber e abrir a confirmação; entrar no celular e no computador.
3. Reenviar confirmação de outra conta ainda pendente e conferir recebimento.
4. Solicitar recuperação; receber e definir senha forte com confirmação.
5. Conferir novo login, recusa da senha antiga e recusa de reuso do link.
6. Confirmar que uma conta já existente continua vendo apenas seus próprios dados.

A entrega real dos e-mails e as configurações administrativas ainda precisam ser
verificadas no NEXO-APP. Não declarar o fluxo de e-mail concluído apenas porque o
HTML ou o pipeline foi publicado.
