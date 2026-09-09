"""Tokens únicos de nome_completo (Censo + CPF) para revisar grafias.

Rode da raiz: python data/_tokens_unicos_nomes.py

Usa o nome limpo original (sem a lista de variantes). Saída:
data/tokens_unicos_nomes.csv — token, n, n_censo, n_cpf, n_primeiro, na_lista
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    CENSO_LIMPO,
    CPF_LIMPO,
    TABELA_CENSO_LIMPA,
    TABELA_CENSO_REGISTROS,
    TABELA_CPF_LIMPA,
    TABELA_CPF_REGISTROS,
    get_connection,
    list_tables,
)

LISTA = Path(__file__).resolve().parent / "nomes_variantes.csv"
SAIDA = Path(__file__).resolve().parent / "tokens_unicos_nomes.csv"


def main() -> None:
    na_lista: set[str] = set()
    with LISTA.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            variante = (row.get("variante") or "").strip().upper()
            canonico = (row.get("canonico") or "").strip().upper()
            if variante:
                na_lista.add(variante)
            for tok in canonico.split():
                na_lista.add(tok)

    con = get_connection()
    tabelas = list_tables(con)
    if TABELA_CENSO_LIMPA in tabelas:
        censo = TABELA_CENSO_LIMPA
    elif TABELA_CENSO_REGISTROS in tabelas:
        censo = TABELA_CENSO_REGISTROS
    else:
        censo = None
    if TABELA_CPF_LIMPA in tabelas:
        cpf = TABELA_CPF_LIMPA
    elif TABELA_CPF_REGISTROS in tabelas:
        cpf = TABELA_CPF_REGISTROS
    else:
        cpf = None

    if censo is None and CENSO_LIMPO.exists():
        con.execute(
            f"CREATE VIEW censo_nomes AS SELECT nome_completo "
            f"FROM read_parquet('{CENSO_LIMPO}')"
        )
        censo = "censo_nomes"
    if cpf is None and CPF_LIMPO.exists():
        con.execute(
            f"CREATE VIEW cpf_nomes AS SELECT nome_completo "
            f"FROM read_parquet('{CPF_LIMPO}')"
        )
        cpf = "cpf_nomes"

    if censo is None or cpf is None:
        con.close()
        raise SystemExit(
            "Não achei censo/cpf limpo (tabela DuckDB nem parquet). "
            "Rode o NB00/NB00b antes."
        )

    print(f"lendo {censo} e {cpf}")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE nomes AS
        SELECT 'censo' AS origem, nome_completo AS nome
        FROM {censo}
        WHERE nome_completo IS NOT NULL AND nome_completo <> ''
        UNION ALL
        SELECT 'cpf', nome_completo
        FROM {cpf}
        WHERE nome_completo IS NOT NULL AND nome_completo <> ''
        """
    )
    con.execute("CREATE TEMP TABLE lista (token VARCHAR)")
    con.executemany(
        "INSERT INTO lista VALUES (?)", [(t,) for t in sorted(na_lista)]
    )
    con.execute(
        f"""
        COPY (
          SELECT
            t.token,
            t.n,
            t.n_censo,
            t.n_cpf,
            coalesce(p.n_primeiro, 0) AS n_primeiro,
            CASE WHEN l.token IS NULL THEN 'nao' ELSE 'sim' END AS na_lista
          FROM (
            SELECT
              token,
              count(*) AS n,
              count(*) FILTER (WHERE origem = 'censo') AS n_censo,
              count(*) FILTER (WHERE origem = 'cpf') AS n_cpf
            FROM (
              SELECT origem, unnest(string_split(nome, ' ')) AS token
              FROM nomes
            )
            WHERE token <> ''
            GROUP BY token
          ) t
          LEFT JOIN (
            SELECT split_part(nome, ' ', 1) AS token, count(*) AS n_primeiro
            FROM nomes
            WHERE split_part(nome, ' ', 1) <> ''
            GROUP BY 1
          ) p ON t.token = p.token
          LEFT JOIN (SELECT DISTINCT token FROM lista) l ON t.token = l.token
          ORDER BY n_primeiro DESC, n DESC
        ) TO '{SAIDA}' (HEADER, DELIMITER ',')
        """
    )
    n_tok, n_fora, n_primeiro_fora = con.execute(
        f"""
        SELECT
          count(*),
          count(*) FILTER (WHERE na_lista = 'nao'),
          count(*) FILTER (WHERE na_lista = 'nao' AND n_primeiro > 0)
        FROM read_csv_auto('{SAIDA}')
        """
    ).fetchone()
    print(f"{SAIDA.name}: {n_tok:,} tokens ({n_fora:,} fora da lista)")
    print(f"primeiros nomes fora da lista: {n_primeiro_fora:,}")
    print("top 30 primeiros nomes ainda fora da lista:")
    print(
        con.execute(
            f"""
            SELECT token, n_primeiro, n, n_censo, n_cpf
            FROM read_csv_auto('{SAIDA}')
            WHERE na_lista = 'nao' AND n_primeiro > 0
            ORDER BY n_primeiro DESC
            LIMIT 30
            """
        ).df().to_string(index=False)
    )
    con.close()


if __name__ == "__main__":
    main()
