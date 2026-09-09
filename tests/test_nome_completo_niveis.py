"""Níveis do nome completo: prefixo de tokens vs último diferente (JW alto)."""

from __future__ import annotations

import duckdb

PREFIXO_SQL = """
    least(len(string_split(nome_l, ' ')), len(string_split(nome_r, ' '))) >= 2
    AND len(string_split(nome_l, ' ')) <> len(string_split(nome_r, ' '))
    AND list_slice(
        string_split(nome_l, ' '),
        1,
        least(len(string_split(nome_l, ' ')), len(string_split(nome_r, ' ')))
    ) = list_slice(
        string_split(nome_r, ' '),
        1,
        least(len(string_split(nome_l, ' ')), len(string_split(nome_r, ' ')))
    )
"""

JW_ULTIMO_095_SQL = """
    string_split(nome_l, ' ')[-1] = string_split(nome_r, ' ')[-1]
    AND jaro_winkler_similarity(nome_l, nome_r) >= 0.95
"""

JW_ULTIMO_092_SQL = """
    string_split(nome_l, ' ')[-1] = string_split(nome_r, ' ')[-1]
    AND jaro_winkler_similarity(nome_l, nome_r) >= 0.92
"""


def _niveis(con: duckdb.DuckDBPyConnection) -> dict[tuple[str, str], str]:
    rows = con.execute(
        f"""
        SELECT nome_l, nome_r,
            CASE
                WHEN nome_l = nome_r THEN 'exact'
                WHEN {PREFIXO_SQL} THEN 'prefixo'
                WHEN {JW_ULTIMO_095_SQL} THEN 'jw95'
                WHEN {JW_ULTIMO_092_SQL} THEN 'jw92'
                ELSE 'else'
            END AS nivel
        FROM pares
        """
    ).fetchall()
    return {(a, b): n for a, b, n in rows}


def test_prefixo_jw_ultimo_e_sobrenome_trocado() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE pares AS SELECT * FROM (VALUES
            ('VICTOR GABRIEL SANTOS RODRIGUES',
             'VICTOR GABRIEL SANTOS PEREIRA'),
            ('MARIA JOAQUINA SANTOS PEREIRA',
             'MARIA JOAQUINA SANTOS'),
            ('JOANA COSTA SILVA FERREIRA',
             'JOANA COSTA SILVA'),
            ('JOAO CARLOS SILVA', 'JOAO KARLOS SILVA'),
            ('MARIA CLARA SOUZA', 'MARIA CLRA SOUZA'),
            ('ANA MARIA SILVA', 'ANA MARIA SILVA')
        ) v(nome_l, nome_r)
        """
    )
    niveis = _niveis(con)
    jw_rodrigues = con.execute(
        """
        SELECT jaro_winkler_similarity(
            'VICTOR GABRIEL SANTOS RODRIGUES',
            'VICTOR GABRIEL SANTOS PEREIRA'
        )
        """
    ).fetchone()[0]
    con.close()

    assert jw_rodrigues >= 0.92
    assert niveis[
        ("VICTOR GABRIEL SANTOS RODRIGUES", "VICTOR GABRIEL SANTOS PEREIRA")
    ] == "else"
    assert niveis[
        ("MARIA JOAQUINA SANTOS PEREIRA", "MARIA JOAQUINA SANTOS")
    ] == "prefixo"
    assert niveis[("JOANA COSTA SILVA FERREIRA", "JOANA COSTA SILVA")] == "prefixo"
    assert niveis[("JOAO CARLOS SILVA", "JOAO KARLOS SILVA")] == "jw95"
    assert niveis[("MARIA CLARA SOUZA", "MARIA CLRA SOUZA")] == "jw92"
    assert niveis[("ANA MARIA SILVA", "ANA MARIA SILVA")] == "exact"
