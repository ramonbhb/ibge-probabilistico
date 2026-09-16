"""Recalcula `*_phon` dos registros e grava parquets novos (não sobrescreve).

Mesma regra do 00: sem CSV de variantes; 3 tokens + epêntese D + fonética atual.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROB_DIR = Path(__file__).resolve().parent
if str(PROB_DIR) not in sys.path:
    sys.path.insert(0, str(PROB_DIR))

from config import (
    CENSO_REGISTROS,
    CPF_REGISTROS,
    export_parquet,
    get_connection,
    print_paths,
    require_input,
)
from features import (
    NOME_MAE_COLUMNS,
    PESSOA_COLUMNS,
    name_feature_columns_sql,
    phonetic_name_sql,
    select_list_sql,
)

print_paths()
require_input(CENSO_REGISTROS, label="CENSO_REGISTROS")
require_input(CPF_REGISTROS, label="CPF_REGISTROS")
con = get_connection()

phon_pessoa = phonetic_name_sql("coalesce(nome_completo, '')")
phon_mae = phonetic_name_sql("coalesce(nome_mae, '')")
pessoa = name_feature_columns_sql(
    "nome_completo", col_map=PESSOA_COLUMNS, phon_col="nome_completo_phon"
)
mae = name_feature_columns_sql(
    "nome_mae", col_map=NOME_MAE_COLUMNS, phon_col="nome_mae_phon"
)
pessoa_phon = {
    "nome_completo_phon": pessoa["nome_completo_phon"],
    "primeiro_nome_phon": pessoa["primeiro_nome_phon"],
    "nome_meio_phon": pessoa["nome_meio_phon"],
    "ultimo_nome_phon": pessoa["ultimo_nome_phon"],
    "primeiro_ultimo_phon": pessoa["primeiro_ultimo_phon"],
}
mae_phon = {
    "nome_mae_phon": mae["nome_mae_phon"],
    "primeiro_nome_mae_phon": mae["primeiro_nome_mae_phon"],
    "nome_meio_mae_phon": mae["nome_meio_mae_phon"],
    "ultimo_nome_mae_phon": mae["ultimo_nome_mae_phon"],
}

PHON_COLS = """
    nome_completo_phon, primeiro_nome_phon, nome_meio_phon,
    ultimo_nome_phon, primeiro_ultimo_phon,
    nome_mae_phon, primeiro_nome_mae_phon, nome_meio_mae_phon,
    ultimo_nome_mae_phon
"""

for origem, src, tabela in [
    ("censo", CENSO_REGISTROS, "censo_registros_fonetica"),
    ("cpf", CPF_REGISTROS, "cpf_registros_fonetica"),
]:
    src_sql = str(src).replace("'", "''")
    con.execute(f"""
    CREATE OR REPLACE TABLE {tabela} AS
    WITH phon AS (
        SELECT * EXCLUDE ({PHON_COLS}),
            {phon_pessoa} AS nome_completo_phon,
            {phon_mae} AS nome_mae_phon
        FROM read_parquet('{src_sql}')
    )
    SELECT
        * EXCLUDE (nome_completo_phon, nome_mae_phon),
        {select_list_sql(pessoa_phon)},
        {select_list_sql(mae_phon)}
    FROM phon
    """)
    dest = export_parquet(con, tabela)
    n, n_mudou = con.execute(f"""
    SELECT
        COUNT(*) AS n,
        COUNT(*) FILTER (
            WHERE a.nome_completo_phon IS DISTINCT FROM b.nome_completo_phon
        ) AS n_mudou
    FROM read_parquet('{src_sql}') a
    JOIN {tabela} b USING (unique_id)
    """).fetchone()
    print(f"{origem}: {n:,} linhas | nome_completo_phon mudou: {n_mudou:,}")
    print(f"gravado: {dest}")
    sample = con.execute(f"""
    SELECT
        a.nome_completo,
        a.nome_completo_phon AS phon_antes,
        b.nome_completo_phon AS phon_depois
    FROM read_parquet('{src_sql}') a
    JOIN {tabela} b USING (unique_id)
    WHERE a.nome_completo_phon IS DISTINCT FROM b.nome_completo_phon
    LIMIT 10
    """).df()
    print(sample.to_string(index=False))
    print()
