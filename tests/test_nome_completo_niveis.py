"""Níveis do nome completo: prefixo, JW, DL; proporção no primeiro nome."""

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

DL1_SQL = """
    damerau_levenshtein(nome_l, nome_r) <= 1
"""

DL2_SQL = """
    string_split(nome_l, ' ')[-1] = string_split(nome_r, ' ')[-1]
    AND least(
        len(string_split(nome_l, ' ')[1]),
        len(string_split(nome_r, ' ')[1])
    ) >= 6
    AND damerau_levenshtein(nome_l, nome_r) <= 2
    AND damerau_levenshtein(
        string_split(nome_l, ' ')[1],
        string_split(nome_r, ' ')[1]
    ) * 6 <= least(
        len(string_split(nome_l, ' ')[1]),
        len(string_split(nome_r, ' ')[1])
    )
"""

DL_PRIMEIRO_SQL = """
    damerau_levenshtein(a, b) <= 2
    AND least(len(a), len(b)) >= 6
    AND damerau_levenshtein(a, b) * 6 <= least(len(a), len(b))
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
                WHEN {DL1_SQL} THEN 'dl1'
                WHEN {DL2_SQL} THEN 'dl2'
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
            ('ANA MARIA SILVA', 'ANA MARIA SILVA'),
            ('ABIDIAS KLEMENTINO SILVA', 'ABDIAS KLEMENTINO SILVA'),
            ('JOAO CARLOS SILVA', 'JOAO CARLOS SILVX'),
            ('JOSE SILVA', 'JOAO SILVA')
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
    jw_abidias = con.execute(
        """
        SELECT jaro_winkler_similarity(
            'ABIDIAS KLEMENTINO SILVA',
            'ABDIAS KLEMENTINO SILVA'
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
    # JW no completo pode pegar antes do DL; o par não cai no ELSE.
    if jw_abidias >= 0.95:
        assert niveis[
            ("ABIDIAS KLEMENTINO SILVA", "ABDIAS KLEMENTINO SILVA")
        ] == "jw95"
    elif jw_abidias >= 0.92:
        assert niveis[
            ("ABIDIAS KLEMENTINO SILVA", "ABDIAS KLEMENTINO SILVA")
        ] == "jw92"
    else:
        assert niveis[
            ("ABIDIAS KLEMENTINO SILVA", "ABDIAS KLEMENTINO SILVA")
        ] == "dl1"
    assert niveis[("JOAO CARLOS SILVA", "JOAO CARLOS SILVX")] == "dl1"
    assert niveis[("JOSE SILVA", "JOAO SILVA")] == "else"


def test_dl2_sql_completo_nao_pega_jose_joao() -> None:
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT nome_l, nome_r, ({DL2_SQL}) AS dl2
        FROM (VALUES
            ('CONSTANTINO JOSE SILVA', 'CONSTANTXNO JOXE SILVA'),
            ('JOSE SILVA', 'JOAO SILVA')
        ) v(nome_l, nome_r)
        """
    ).fetchall()
    con.close()
    passa = {(a, b): d for a, b, d in rows}
    assert passa[("CONSTANTINO JOSE SILVA", "CONSTANTXNO JOXE SILVA")]
    assert not passa[("JOSE SILVA", "JOAO SILVA")]


def test_proporcao_primeiro_nome() -> None:
    """Gênero ANTONIO/ANTONIA passa no SQL; a trava é sexo no blocking."""
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT a, b, ({DL_PRIMEIRO_SQL}) AS passa
        FROM (VALUES
            ('ABIDIAS', 'ABDIAS'),
            ('MARIA', 'MARIO'),
            ('JOSE', 'JOAO'),
            ('ANA', 'ADA'),
            ('ANTONIO', 'ANTONIA')
        ) v(a, b)
        """
    ).fetchall()
    con.close()
    passa = {(a, b): p for a, b, p in rows}
    assert passa[("ABIDIAS", "ABDIAS")]
    assert not passa[("MARIA", "MARIO")]
    assert not passa[("JOSE", "JOAO")]
    assert not passa[("ANA", "ADA")]
    assert passa[("ANTONIO", "ANTONIA")]
