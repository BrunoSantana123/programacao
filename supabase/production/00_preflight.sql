-- NEXO-APP / tznebgdgdqpbhjdrhprb: conferir o projeto no painel ANTES de executar.
-- Somente metadados. Não consulta linhas financeiras nem altera o banco.
BEGIN TRANSACTION READ ONLY;

SELECT current_database() AS banco,
       to_regclass('public.nexo_data') IS NOT NULL AS tabela_existe;

SELECT c.relrowsecurity AS rls_habilitada, c.relforcerowsecurity AS rls_forcada
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'nexo_data';

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'nexo_data'
ORDER BY ordinal_position;

SELECT conname, contype, pg_get_constraintdef(oid) AS definicao
FROM pg_constraint WHERE conrelid = to_regclass('public.nexo_data');

SELECT policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname = 'public' AND tablename = 'nexo_data'
ORDER BY policyname;

SELECT grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND table_name = 'nexo_data'
ORDER BY grantee, privilege_type;

-- Se já existir uma função, comparar sua definição NO PAINEL antes de substituir.
-- O hash abaixo não expõe o corpo de uma implementação anterior desconhecida.
SELECT p.oid::regprocedure AS assinatura, p.prosecdef AS security_definer,
       p.proconfig AS configuracao, pg_get_userbyid(p.proowner) AS proprietario,
       md5(pg_get_functiondef(p.oid)) AS hash_definicao_existente
FROM pg_proc p
WHERE p.oid = to_regprocedure('public.nexo_registrar_lancamento(uuid,text,bigint,text,text,date)');

ROLLBACK;
