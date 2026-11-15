-- Estrutura e políticas fornecidas pelo responsável, sem dados de produção.
CREATE TABLE public.nexo_data (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.nexo_data ENABLE ROW LEVEL SECURITY;
CREATE POLICY nexo_select_own ON public.nexo_data FOR SELECT TO authenticated USING ((SELECT auth.uid()) = user_id);
CREATE POLICY nexo_insert_own ON public.nexo_data FOR INSERT TO authenticated WITH CHECK ((SELECT auth.uid()) = user_id);
CREATE POLICY nexo_update_own ON public.nexo_data FOR UPDATE TO authenticated USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id);
CREATE POLICY nexo_delete_own ON public.nexo_data FOR DELETE TO authenticated USING ((SELECT auth.uid()) = user_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.nexo_data TO authenticated;
