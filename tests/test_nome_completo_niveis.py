"""Níveis do nome completo: prefixo, um ou dois tokens, JW, DL."""

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

def _token_sql(max_tokens: str, ultimo_igual: bool) -> str:
    n_tok = "len(string_split(nome_l, ' '))"
    split_l = "string_split(nome_l, ' ')"
    split_r = "string_split(nome_r, ' ')"
    zip_tok = f"list_zip({split_l}, {split_r})"
    dif_count = (
        "list_aggregate(list_transform("
        f"{zip_tok}, "
        "x -> CASE WHEN x[1] <> x[2] THEN 1 ELSE 0 END"
        "), 'sum')"
    )
    dif_max = (
        "list_aggregate(list_transform("
        f"{zip_tok}, "
        "x -> CASE WHEN x[1] <> x[2] "
        "THEN damerau_levenshtein(x[1], x[2]) ELSE 0 END"
        "), 'max')"
    )
    ultimo = f"AND {split_l}[-1] = {split_r}[-1] " if ultimo_igual else ""
    return (
        f"{n_tok} = len({split_r}) AND {n_tok} >= 3 "
        f"{ultimo}"
        f"AND {dif_count} {max_tokens} AND {dif_max} <= 2"
    )


UM_TOKEN_SQL = _token_sql("= 1", ultimo_igual=True)
DOIS_TOKENS_SQL = _token_sql("BETWEEN 1 AND 2", ultimo_igual=False)

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
                WHEN {UM_TOKEN_SQL} THEN 'um_token'
                WHEN {DOIS_TOKENS_SQL} THEN 'dois_tokens'
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
    con.close()

    assert jw_rodrigues >= 0.92
    assert niveis[
        ("VICTOR GABRIEL SANTOS RODRIGUES", "VICTOR GABRIEL SANTOS PEREIRA")
    ] == "else"
    assert niveis[
        ("MARIA JOAQUINA SANTOS PEREIRA", "MARIA JOAQUINA SANTOS")
    ] == "prefixo"
    assert niveis[("JOANA COSTA SILVA FERREIRA", "JOANA COSTA SILVA")] == "prefixo"
    assert niveis[("JOAO CARLOS SILVA", "JOAO KARLOS SILVA")] == "um_token"
    assert niveis[("MARIA CLARA SOUZA", "MARIA CLRA SOUZA")] == "um_token"
    assert niveis[("ANA MARIA SILVA", "ANA MARIA SILVA")] == "exact"
    assert niveis[
        ("ABIDIAS KLEMENTINO SILVA", "ABDIAS KLEMENTINO SILVA")
    ] == "um_token"
    assert niveis[("JOAO CARLOS SILVA", "JOAO CARLOS SILVX")] == "dois_tokens"
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


def test_um_token_e_dois_tokens() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE pares AS SELECT * FROM (VALUES
            ('ALICE ISADORA BARBOSA MACIEL', 'ALICIA ISADORA BARBOSA MACIEL'),
            ('LARA SAFIA SILVA', 'LARA SOFIA SILVA'),
            ('JAQUES DOLGAS PENHA FILHO', 'JAQUES DOUGLAS PENHA FILHO'),
            ('CLEONITO COSTA RODRIGUES', 'CLEONILDO COSTA RODRIGUES'),
            ('WEVERDOR MORAIS SILVA', 'WEVERTON MORAES SILVA'),
            ('VANIKELY CINCEICAO SILVA SOUSA', 'VANIKELY CONCEICAO SILVA SOUZA'),
            ('VALDINOR VIERA OLIVEIRA', 'VALDIONOR VIEIRA OLIVEIRA'),
            ('RAIMUNDO SILVA', 'RAIMUNDO SILBA'),
            ('HELENA FERREIRA SILVA', 'HELLENA LIMA SILVA'),
            ('JHONATA FILIPE ROSA SILVA', 'JONATHAN FELIPE ROSA SILVA'),
            ('VICTOR GABRIEL SANTOS RODRIGUES', 'VICTOR GABRIEL SANTOS PEREIRA')
        ) v(nome_l, nome_r)
        """
    )
    niveis = _niveis(con)
    con.close()
    for par in (
        ("ALICE ISADORA BARBOSA MACIEL", "ALICIA ISADORA BARBOSA MACIEL"),
        ("LARA SAFIA SILVA", "LARA SOFIA SILVA"),
        ("JAQUES DOLGAS PENHA FILHO", "JAQUES DOUGLAS PENHA FILHO"),
        ("CLEONITO COSTA RODRIGUES", "CLEONILDO COSTA RODRIGUES"),
    ):
        assert niveis[par] == "um_token"
    for par in (
        ("WEVERDOR MORAIS SILVA", "WEVERTON MORAES SILVA"),
        ("VANIKELY CINCEICAO SILVA SOUSA", "VANIKELY CONCEICAO SILVA SOUZA"),
        ("VALDINOR VIERA OLIVEIRA", "VALDIONOR VIEIRA OLIVEIRA"),
    ):
        assert niveis[par] == "dois_tokens"
    assert niveis[("RAIMUNDO SILVA", "RAIMUNDO SILBA")] not in ("um_token", "dois_tokens")
    assert niveis[("HELENA FERREIRA SILVA", "HELLENA LIMA SILVA")] not in (
        "um_token",
        "dois_tokens",
    )
    assert niveis[("JHONATA FILIPE ROSA SILVA", "JONATHAN FELIPE ROSA SILVA")] not in (
        "um_token",
        "dois_tokens",
    )
    assert niveis[
        ("VICTOR GABRIEL SANTOS RODRIGUES", "VICTOR GABRIEL SANTOS PEREIRA")
    ] == "else"
