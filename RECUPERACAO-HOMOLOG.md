# Recuperação de senha — NEXO-HOMOLOG

## Entrega e isolamento

Implementado exclusivamente em `homolog/`. Os arquivos oficiais `index.html`,
`nexo-teste.html`, a função MCP, o banco e suas regras de acesso não foram alterados.
A tela de login foi reaproveitada, com link “Esqueci minha senha”. A identidade
visual existente foi mantida nas telas de solicitação e nova senha.

O build `python -m tools.build_homolog` gera `dist-homolog/`. Exige URL e chave
**pública publishable** de um projeto Supabase separado. Recusa o projeto oficial
conhecido, chaves administrativas e configuração ausente. Não há fallback para
produção. A página OAuth existente também é incluída com os identificadores
exclusivos de homologação; sem estes, a autorização fica bloqueada.

## Fluxo e proteção

- Solicitação via Supabase Auth `/recover`, com destino fixo na página de recuperação.
- Mensagem de envio neutra, sem informar se o endereço possui uma conta.
- Link com `token_hash` e `type=recovery`, verificado no `/verify` do Supabase.
- Links de cadastro, fragmentos com tokens, parâmetros duplicados e links inválidos
  são recusados. O modelo de e-mail abaixo é obrigatório; o link padrão implícito
  não é aceito por esta tela.
- Tokens removidos do endereço e mantidos apenas em memória. Nenhum token vai
  para localStorage/sessionStorage ou logs do aplicativo. Recarregar a página
  exige solicitar outro link, pois o token de uso único já pode ter sido consumido.
- Nova senha: 12 a 128 caracteres, maiúsculas, minúsculas, números, símbolos,
  confirmação idêntica e sem espaços nas pontas. O Supabase valida sua política
  novamente no servidor. A validação da tela não substitui essa configuração.
- Senha atualizada no `/user` com a sessão do próprio usuário recuperado.
- Tentativa de revogação global das sessões após a alteração, com aviso explícito
  se a revogação não puder ser confirmada. Exige novo login no aplicativo.
- Janela de redefinição limitada à duração do token ou 15 minutos, o menor valor.
- Falhas de rede, limite de tentativas e erros de senha/link exibidos em português.
- Nenhuma chamada de recuperação acessa a tabela financeira ou usa service_role.

## Configurar somente o Supabase de homologação

1. Confirmar qual é o projeto exclusivo de homologação. Não usar o projeto oficial
   `tznebgdgdqpbhjdrhprb`. Não enviar senhas/chaves privadas em chats ou commits.
2. Em Authentication / URL Configuration:
   - Site URL: `https://nexo-homolog-six.vercel.app`.
   - Redirect URL exata: `https://nexo-homolog-six.vercel.app/recuperar.html`.
   - Preservar os destinos legítimos existentes de login/OAuth. Evitar curingas.
3. Manter confirmação de e-mail habilitada. Configurar no servidor mínimo de 12
   caracteres e requisitos de maiúsculas, minúsculas, números e símbolos. Preservar
   limites de tentativas e proteções existentes; avaliar proteção contra senhas
   vazadas conforme o plano disponível.
4. No modelo **Reset Password**, usar o link abaixo (HTML), mantendo o restante do
   conteúdo e a identificação do NEXO. Não usar um link de confirmação de cadastro:

   ```html
   <a href="https://nexo-homolog-six.vercel.app/recuperar.html?token_hash={{ .TokenHash }}&amp;type=recovery">Criar nova senha</a>
   ```

5. Configurar expiração do link (recomendado até uma hora). Manter o template de
   confirmação de cadastro separado. Não desligar a confirmação para resolver envio.
6. Configurar SMTP do ambiente de testes, com remetente/domínio verificado, porta,
   TLS e senha guardados **somente no Supabase**. O SMTP padrão do Supabase pode
   restringir destinatários aos membros autorizados e impor limites baixos; verificar
   o limite efetivo do projeto e as respostas do Auth, sem presumir que esta é a causa.
7. Conferir Auth Logs e registros do provedor: rejeição do SMTP, credencial incorreta,
   destinatário não autorizado, rate limit, bounces e supressões. Conferir SPF, DKIM,
   DMARC e spam. Desabilitar reescrita/rastreamento dos links de autenticação no
   provedor, não as proteções de confirmação. Não copiar tokens dos logs ao relatório.

## Configurar somente o projeto Vercel NEXO-HOMOLOG

O endereço informado não revela qual Supabase está conectado. Não alterei o projeto
Vercel nem publiquei o código. A tentativa de leitura HTTPS do site foi recusada pelo
proxy deste ambiente (403 no túnel), portanto configurações remotas não foram auditadas.

No projeto **NEXO-HOMOLOG**, definir de forma separada das variáveis do NEXO oficial:

- `NEXO_HOMOLOG_SUPABASE_URL`: URL do Supabase exclusivo de homologação.
- `NEXO_HOMOLOG_SUPABASE_PUBLISHABLE_KEY`: sua chave pública publishable.
- Preservar/configurar `NEXO_HOMOLOG_OAUTH_CLIENT_ID` e
  `NEXO_HOMOLOG_OAUTH_CALLBACK` com os identificadores desse ambiente para manter
  a conexão ChatGPT. Não reutilizar registros do projeto oficial por suposição.
- Framework: Other; diretório de trabalho: raiz do repositório.
- Build Command: `python3 tools/build_homolog.py`.
- Output Directory: `dist-homolog`.

`homolog/vercel.example.json` contém a configuração de build e cabeçalhos de
segurança, incluindo CSP específica da recuperação, no-store, no-referrer e bloqueio
contra incorporação em frames. Aplicá-la **somente ao projeto de homologação**, por
exemplo com o recurso `--local-config` da CLI Vercel e vínculo verificado desse projeto.
Não é um `vercel.json` na raiz e não muda os deployments do NEXO oficial. Não executar
um deploy com um vínculo de projeto não conferido. Não publicar o arquivo de exemplo
como se fosse uma configuração ativa: ele precisa ser aplicado pelo Vercel.

## Testes e limites

Executar:

```sh
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m unittest discover -s tests -v
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_recovery_local --directory /workspace/nexo-test-environment
NEXO_CHROMIUM_EXECUTABLE=/usr/bin/chromium python -m tools.validate_local_oauth --directory /workspace/nexo-test-environment
```

Resultado executado: **68 testes aprovados**. A integração OAuth/MCP/finanças
existente também foi executada novamente e aprovada (cadastro, duas contas, RLS,
lançamentos, concorrência, PKCE e recusa de reuso). A suíte tem 68 testes, incluindo 18 novos casos de recuperação/build: solicitação,
resposta neutra, redirecionamento fixo, força/confirmação da senha, uso do token,
remoção da URL/armazenamento, link inválido/expirado, sessão vencida, rate limit,
falha de rede/revogação, configuração fechada, recusa do projeto oficial e telas
320/390/1280 pixels. Casos de erro usam respostas controladas, sem acesso externo.

O ensaio real local cria **somente uma conta fictícia temporária**, gera um token
real de recuperação via API administrativa local, troca a senha pelo navegador,
rejeita o reuso do link e a senha anterior, e confirma o novo login. A conta é
excluída ao final. A chave administrativa permanece fora do frontend/Git e é usada
apenas pelo teste local. Não modifica a configuração de confirmação de e-mail do
ambiente existente. A conta é confirmada administrativamente apenas para o ensaio;
isso não testa nem desabilita a confirmação de cadastro do projeto remoto.

GitHub Actions executa a suíte e o ensaio real de recuperação após preparar o
Supabase local, além da integração OAuth/MCP/finanças existente.

**Não certificados ainda:** entrega SMTP real, confirmação de cadastro por e-mail,
configurações remotas, cabeçalhos aplicados e fluxo no endereço publicado. Não há
acesso ao painel Supabase/Vercel nem configuração confirmada do projeto de testes.
Após aplicar a configuração e publicar somente a homologação, testar com uma caixa
real autorizada: solicitar, receber, redefinir, entrar com a nova senha, recusar a
anterior e o reuso do link; repetir em celular/computador e confirmar o cadastro de
uma segunda conta. Não registrar links ou credenciais no relatório.
