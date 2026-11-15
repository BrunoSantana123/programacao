-- Requer a tabela nexo_data existente. Não recria tabela, políticas ou registros.
BEGIN;
CREATE OR REPLACE FUNCTION public.nexo_registrar_lancamento(
  p_id uuid, p_tipo text, p_centavos bigint, p_categoria text,
  p_descricao text, p_data date
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
  owner_id uuid := auth.uid();
  document jsonb;
  entry jsonb;
  previous jsonb;
  categories jsonb;
  category_list jsonb;
  item_type text;
BEGIN
  IF owner_id IS NULL THEN
    RAISE EXCEPTION 'Autenticação necessária' USING ERRCODE = '42501';
  END IF;
  IF p_id IS NULL OR p_tipo IS NULL OR p_tipo NOT IN ('receita', 'despesa')
     OR p_centavos IS NULL OR p_centavos <= 0 OR p_centavos > 10000000000
     OR p_data IS NULL OR p_categoria IS NULL OR length(btrim(p_categoria)) NOT BETWEEN 1 AND 120
     OR p_descricao IS NULL OR length(p_descricao) > 200 THEN
    RAISE EXCEPTION 'Lançamento inválido' USING ERRCODE = '22023';
  END IF;
  item_type := CASE p_tipo WHEN 'receita' THEN 'income' ELSE 'expense' END;
  entry := jsonb_build_object('id', p_id, 'date', p_data, 'type', item_type,
    'category', btrim(p_categoria), 'amount', p_centavos::numeric / 100,
    'description', btrim(p_descricao));

  -- A identidade vem exclusivamente do JWT, e o invocador continua sujeito à RLS.
  INSERT INTO public.nexo_data(user_id) VALUES (owner_id)
    ON CONFLICT (user_id) DO NOTHING;
  SELECT data INTO document FROM public.nexo_data WHERE user_id = owner_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Conta indisponível' USING ERRCODE = '42501';
  END IF;
  IF document = '{}'::jsonb THEN
    document := '{"entries":[],"bills":[],"events":[],"goals":[],"tasks":[],"reserves":[],"categories":{"income":[],"expense":[],"reserve":[]},"settings":{}}'::jsonb;
  END IF;
  IF jsonb_typeof(document) <> 'object' OR EXISTS (
    SELECT 1 FROM unnest(ARRAY['entries','bills','events','goals','tasks']) AS k
    WHERE jsonb_typeof(document->k) IS DISTINCT FROM 'array'
  ) THEN
    RAISE EXCEPTION 'Formato existente incompatível; nenhum dado foi alterado' USING ERRCODE = '22023';
  END IF;
  SELECT value INTO previous FROM jsonb_array_elements(document->'entries')
    WHERE value->>'id' = p_id::text LIMIT 1;
  IF previous IS NOT NULL THEN
    IF NOT previous @> entry THEN
      RAISE EXCEPTION 'Identificador já utilizado com outros dados' USING ERRCODE = '22023';
    END IF;
    RETURN jsonb_build_object('lancamento', previous, 'repetido', true);
  END IF;
  categories := COALESCE(document->'categories', '{"income":[],"expense":[],"reserve":[]}'::jsonb);
  IF jsonb_typeof(categories) <> 'object' THEN
    RAISE EXCEPTION 'Categorias existentes incompatíveis' USING ERRCODE = '22023';
  END IF;
  category_list := COALESCE(categories->item_type, '[]'::jsonb);
  IF jsonb_typeof(category_list) <> 'array' THEN
    RAISE EXCEPTION 'Categorias existentes incompatíveis' USING ERRCODE = '22023';
  END IF;
  IF NOT category_list @> jsonb_build_array(btrim(p_categoria)) THEN
    category_list := category_list || jsonb_build_array(btrim(p_categoria));
  END IF;
  document := jsonb_set(document, '{entries}', (document->'entries') || jsonb_build_array(entry));
  document := jsonb_set(document, '{categories}', jsonb_set(categories, ARRAY[item_type], category_list));
  UPDATE public.nexo_data SET data = document,
    updated_at = greatest(clock_timestamp(), updated_at + interval '1 millisecond')
    WHERE user_id = owner_id;
  RETURN jsonb_build_object('lancamento', entry, 'repetido', false);
END;
$$;
REVOKE ALL ON FUNCTION public.nexo_registrar_lancamento(uuid,text,bigint,text,text,date) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.nexo_registrar_lancamento(uuid,text,bigint,text,text,date) TO authenticated;
COMMIT;
