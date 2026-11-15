-- Executar no NEXO-APP após instalar a migração. Somente metadados.
-- NÃO é um ensaio de gravação, nem substitui os testes com duas contas OAuth.
BEGIN TRANSACTION READ ONLY;

SELECT to_regprocedure('public.nexo_registrar_lancamento(uuid,text,bigint,text,text,date)')
       IS NOT NULL AS funcao_instalada;

SELECT p.oid::regprocedure AS assinatura,
       NOT p.prosecdef AS executa_com_permissoes_do_usuario,
       p.prorettype = 'jsonb'::regtype AS retorno_jsonb,
       p.proconfig AS configuracao_search_path,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated_pode_executar,
       NOT has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_bloqueado,
       NOT EXISTS (
         SELECT 1 FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) a
         WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'
       ) AS public_bloqueado
FROM pg_proc p
WHERE p.oid = to_regprocedure('public.nexo_registrar_lancamento(uuid,text,bigint,text,text,date)');

SELECT c.relrowsecurity AS rls_permanece_habilitada
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'nexo_data';

SELECT policyname, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname = 'public' AND tablename = 'nexo_data'
ORDER BY policyname;

ROLLBACK;
