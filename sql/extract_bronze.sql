-- Snippets de referência para o NB00 (copiar/adaptar).

-- UF CPF: substr(COD_UFMUN, 1, 2) via cpf_uf_expr('c')
-- UF Censo: substr(B0000, 1, 2) via censo_uf_expr('p')
-- CEP Censo: materialize_censo_logr_lookup(con) + LEFT JOIN censo_morador_cep
--   ON B0000=COD_SETOR, NUM_QUADRA, NUM_FACE (especie.parquet ⋈ logr.parquet)

-- Inferência nome da mãe (após filtro UF): inferir_nome_mae_duckdb(con, source_table='censo_pessoas_filtrado')
-- Join: censo_staging LEFT JOIN censo_pais_inferidos ON person_id_censo
