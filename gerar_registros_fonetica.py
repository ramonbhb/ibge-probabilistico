"""Recalcula só `*_mae_phon` nos parquets e grava (sobrescreve o mesmo path).

Pessoa (`nome_completo_phon` etc.) não muda — continua do join bronze.
Mãe: `phonetic_name_sql` a partir de `nome_mae` limpo + split das partes.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROB_DIR = Path(__file__).resolve().parent
if str(PROB_DIR) not in sys.path:
    sys.path.insert(0, str(PROB_DIR))

from config import (
    CENSO_LIMPO,
    CENSO_LIMPO_APLICACAO,
    CENSO_REGISTROS,
    CPF_LIMPO,
    CPF_LIMPO_APLICACAO,
    CPF_REGISTROS,
    get_connection,
    print_paths,
)
from features import (
    NOME_MAE_COLUMNS,
    name_feature_columns_sql,
    phonetic_name_sql,
    select_list_sql,
)

print_paths()
con = get_connection()

phon_mae = phonetic_name_sql("coalesce(nome_mae, '')")
mae = name_feature_columns_sql(
    "nome_mae", col_map=NOME_MAE_COLUMNS, phon_col="nome_mae_phon"
)
mae_phon = {
    "nome_mae_phon": mae["nome_mae_phon"],
    "primeiro_nome_mae_phon": mae["primeiro_nome_mae_phon"],
    "nome_meio_mae_phon": mae["nome_meio_mae_phon"],
    "ultimo_nome_mae_phon": mae["ultimo_nome_mae_phon"],
}

MAE_PHON_COLS = (
    "nome_mae_phon, primeiro_nome_mae_phon, "
    "nome_meio_mae_phon, ultimo_nome_mae_phon"
)

PARQUETS = [
    ("censo_registros", CENSO_REGISTROS),
    ("cpf_registros", CPF_REGISTROS),
    ("censo_limpo", CENSO_LIMPO),
    ("cpf_limpo", CPF_LIMPO),
    ("censo_limpo_aplicacao", CENSO_LIMPO_APLICACAO),
    ("cpf_limpo_aplicacao", CPF_LIMPO_APLICACAO),
]

for label, src in PARQUETS:
    if not src.exists():
        print(f"{label}: ausente — {src}")
        continue

    src_sql = str(src.resolve()).replace("'", "''")
    tabela = f"_patch_mae_{label}"
    con.execute(f"""
    CREATE OR REPLACE TABLE {tabela} AS
    WITH phon AS (
        SELECT * EXCLUDE ({MAE_PHON_COLS}),
            NULLIF({phon_mae}, '') AS nome_mae_phon
        FROM read_parquet('{src_sql}')
    )
    SELECT
        * EXCLUDE (nome_mae_phon),
        {select_list_sql(mae_phon)}
    FROM phon
    """)

    n, n_distinto, n_mudou = con.execute(f"""
    SELECT
        COUNT(*) AS n,
        COUNT(*) FILTER (
            WHERE b.nome_mae IS NOT NULL
              AND b.nome_mae_phon IS DISTINCT FROM b.nome_mae
        ) AS n_distinto_do_limpo,
        COUNT(*) FILTER (
            WHERE a.nome_mae_phon IS DISTINCT FROM b.nome_mae_phon
        ) AS n_mudou
    FROM read_parquet('{src_sql}') a
    JOIN {tabela} b USING (unique_id)
    """).fetchone()

    sample = con.execute(f"""
    SELECT
        a.nome_mae,
        a.nome_mae_phon AS phon_antes,
        b.nome_mae_phon AS phon_depois
    FROM read_parquet('{src_sql}') a
    JOIN {tabela} b USING (unique_id)
    WHERE a.nome_mae IS NOT NULL
      AND b.nome_mae_phon IS DISTINCT FROM a.nome_mae
    LIMIT 8
    """).df()

    tmp = src.with_suffix(".parquet.tmp")
    tmp_sql = str(tmp.resolve()).replace("'", "''")
    con.execute(f"COPY {tabela} TO '{tmp_sql}' (FORMAT PARQUET)")
    tmp.replace(src)

    print(
        f"{label}: {n:,} linhas | "
        f"mae_phon ≠ mae: {n_distinto:,} | "
        f"mudou vs antes: {n_mudou:,}"
    )
    print(f"gravado: {src}")
    if len(sample):
        print(sample.to_string(index=False))
    print()
    con.execute(f"DROP TABLE IF EXISTS {tabela}")

con.close()
