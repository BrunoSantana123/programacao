> Relatório anterior. Para o estado atual (consultas, cadastro oficial preservado, múltiplas contas e voz), veja [CHATGPT-INTEGRACAO.md](CHATGPT-INTEGRACAO.md).

# NEXO — duas entregas para homologação

## Implementado nesta revisão

1. **Cadastro, login e conexão:** cadastro/login existentes reaproveitados;
   conexão OAuth da própria conta; consentimento explícito para lançamentos;
   testes em telas de celular e computador; proteção contra mistura de sessões.
2. **Receitas e despesas:** a função MCP recuperada foi estendida com
   `registrar_lancamento`. Os dados são acrescentados ao JSON existente em
   `nexo_data`, no formato que o NEXO já apresenta. A tela busca alterações
   feitas pelo ChatGPT sem recarregamento manual.

Nenhum sistema financeiro paralelo, processador de voz ou novo armazenamento
foi criado. `testar_conexao` permanece disponível.

## Integridade financeira e privacidade

- Estrutura e políticas da tabela foram fornecidas pelo responsável e reproduzidas somente no banco isolado.
- A migração acrescenta uma função `SECURITY INVOKER`; mantém as políticas existentes e não usa service_role para gravar lançamentos.
- A identidade é `auth.uid()`, derivada do JWT. A ferramenta não aceita user_id.
- O MCP verifica assinatura, emissor, público, validade, papel e Client ID autorizado.
- O formato é o existente: id/date/type/category/amount/description. Centavos inteiros evitam ambiguidade de escala.
- UUID estável torna uma repetição idempotente. Reutilizá-lo com valores diferentes retorna erro, sem substituir o registro.
- Bloqueio transacional e updated_at monotônico preservam a proteção de concorrência já existente no aplicativo.
- Lançamentos e demais propriedades anteriores do JSON são preservados. Um JSON incompatível é recusado em vez de ser apagado/reconstruído.
- A atualização em segundo plano não interrompe formulários e não deve aplicar respostas de outra sessão.

O fonte original recebido continua preservado em `tests/fixtures/nexo-mcp-test-v2.ts`,
SHA256 `70eb6c1a53de3c2770ec2f91319aece2e76f98f083d5818d5c5df443254e206d`.
A versão funcional está em `supabase/functions/nexo-mcp-test/index.ts`.

## Testes essenciais

A suíte automatizada foi reaproveitada. O teste integrado exercita Supabase,
OAuth, MCP, PostgreSQL/RLS e as páginas reais, sem respostas financeiras simuladas.

- Cadastro pelo celular e login no NEXO.
- Consentimento OAuth, aprovação, recusa, state e PKCE; código reutilizado recusado.
- Token comum de login, token inválido, assinatura/claims/cliente incorretos recusados pelo MCP.
- Receitas e despesas gravadas pelo MCP aparecem no Financeiro com os valores corretos.
- Repetição do mesmo pedido não duplica; pedido divergente com o mesmo UUID não substitui dados.
- Duas gravações concorrentes são preservadas; PATCH antigo do app é recusado.
- Dados anteriores do JSON permanecem intactos.
- Duas contas com grants OAuth próprios só acessam seus dados; leitura, atualização, exclusão e inserção na conta alheia são bloqueadas.
- Troca de conta no mesmo navegador, inclusive com uma renovação antiga pendente, não mostra os registros da conta anterior.

Os resultados e a execução final do GitHub Actions estão na aba Checks do PR #1.
As execuções locais concluídas passaram nos fluxos acima. Os 50 testes de regressão
passaram; foi removido apenas o teste do adaptador antigo que se tornou
inativo ao estender a função, mantendo o teste do arquivo original preservado.

## Limite indispensável para homologação real

**Não está publicado para teste dentro do ChatGPT.** Falta definir e configurar
um ambiente HTTPS exclusivo de homologação para NEXO, consentimento e MCP.
A conversa real e o ditado no ChatGPT não podem ser certificados usando apenas
um endpoint local. O backend recebe o mesmo pedido estruturado depois da
transcrição; não foi criado processamento de áudio fora do ChatGPT.

A chave pública, URL e Client ID desse ambiente precisam corresponder ao projeto
isolado e ao callback do conector. Não se deve usar nem modificar a produção para
concluir esse teste. Passos de homologação: [HOMOLOGACAO.md](HOMOLOGACAO.md).

Nenhum dado de produção, política remota, merge ou deploy em produção foi alterado.
