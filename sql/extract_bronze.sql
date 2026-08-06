-- Snippets de referência para o NB00 (copiar/adaptar no notebook).
-- Parametrize FILTRO_UF via config.py antes de executar.

-- ---------------------------------------------------------------------------
-- 1. Inspecionar bronze
-- ---------------------------------------------------------------------------
-- DESCRIBE SELECT * FROM read_parquet('~/singed/bases/bronze/cpf/cpf.parquet') LIMIT 0;
-- DESCRIBE SELECT * FROM read_parquet('.../censo_pessoas_....parquet') LIMIT 0;
-- DESCRIBE SELECT * FROM read_parquet('.../censo_especie2_....parquet') LIMIT 0;

-- ---------------------------------------------------------------------------
-- 2. Filtro UF — Censo (código IBGE nos 2 primeiros dígitos do setor)
-- ---------------------------------------------------------------------------
-- WHERE :filtro_uf IS NULL
--    OR substr(lpad(regexp_replace(CAST(p.B0000 AS VARCHAR), '[^0-9]', '', 'g'), 12, '0'), 1, 2) = :filtro_uf

-- ---------------------------------------------------------------------------
-- 3. Filtro UF — CPF (ajustar coluna em config.CPF_COL_UF)
-- ---------------------------------------------------------------------------
-- WHERE :filtro_uf IS NULL OR CAST(cpf."SIGLA_UF" AS VARCHAR) = :filtro_uf

-- ---------------------------------------------------------------------------
-- 4. Join Censo pessoas + espécie2 (CEP domiciliar)
-- ---------------------------------------------------------------------------
-- FROM censo_pessoas_filtrado p
-- LEFT JOIN censo_especie2_filtrado e
--   ON p.B0000 = e.COD_SETOR
--  AND p.NUM_QUADRA = e.NUM_QUADRA
--  AND p.NUM_FACE = e.NUM_FACE
--  AND p.B0006 = e.COD_ENDERECO
--  AND p.COD_SEQ_ESPECIE = e.SEQ_ESPECIE
