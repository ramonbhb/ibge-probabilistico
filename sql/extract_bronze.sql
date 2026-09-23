-- Snippets de referência para o NB00 (copiar/adaptar).

-- UF CPF: substr(COD_UFMUN, 1, 2) via cpf_uf_expr('c')
-- UF Censo: substr(B0000, 1, 2) via censo_uf_expr('p')
-- CEP/logradouro Censo: seção 5 do NB00
--   especie ⋈ endereco ⋈ face ⋈ logr; cod_seglogr vem da face
--   pessoa: B0000, NUM_QUADRA, NUM_FACE, B0006, COD_SEQ_ESPECIE

-- Inferência nome da mãe (após filtro UF): inferir_nome_mae_duckdb(con, source_table='censo_pessoas_filtrado')
-- Join: censo_staging LEFT JOIN censo_pais_inferidos ON person_id_censo
