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

_SL = "string_split(nome_l, ' ')"
_SR = "string_split(nome_r, ' ')"
_NL = f"len({_SL})"
_NR = f"len({_SR})"


def _sem_token(split: str, k: int) -> str:
    n = f"len({split})"
    if k == 1:
        return f"list_slice({split}, 2, {n})"
    return (
        f"list_concat(list_slice({split}, 1, {k - 1}), "
        f"list_slice({split}, {k + 1}, {n}))"
    )


_ORS_TOKEN = []
for _k in range(1, 11):
    _ORS_TOKEN.append(f"({_NL} >= {_k} AND {_sem_token(_SL, _k)} = {_SR})")
    _ORS_TOKEN.append(f"({_NR} >= {_k} AND {_sem_token(_SR, _k)} = {_SL})")

TOKEN_A_MAIS_SQL = (
    f"abs({_NL} - {_NR}) = 1 AND least({_NL}, {_NR}) >= 3 AND ("
    + " OR ".join(_ORS_TOKEN)
    + ")"
)
ORDEM_SQL = (
    f"{_NL} = {_NR} AND {_NL} >= 3 "
    f"AND list_sort({_SL}) = list_sort({_SR}) "
    f"AND {_SL} <> {_SR}"
)

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
                WHEN {TOKEN_A_MAIS_SQL} THEN 'token_a_mais'
                WHEN {ORDEM_SQL} THEN 'ordem'
                WHEN {JW_ULTIMO_095_SQL} THEN 'jw95'
                WHEN {JW_ULTIMO_092_SQL} THEN 'jw92'
                WHEN {DL1_SQL} THEN 'dl1'
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


def test_token_a_mais_e_ordem() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE pares AS SELECT * FROM (VALUES
            ('NEUZIN PAULINO GUAJAJARA', 'NEUZIN PAULINO PINTO GUAJAJARA'),
            ('LAUANE ALMEIDA SANTOS', 'LAUANE ALMEIDA DOA SANTOS'),
            ('KAUAN MARTINS BRITO', 'KAUAN MARTINS DS BRITO'),
            ('ELAINE FERREIRA COSTA MATOS', 'ELAINE COSTA FERREIRA MATOS'),
            ('MARIA SILVA', 'MARIA APARECIDA SILVA'),
            ('JOAO VIRTO LIMA CANTANHEDE', 'JOAO VITOR LIMA CANTANHEDE'),
            ('EDYANNE MENDES', 'EDYANNE MENDES CARVALHO')
        ) v(nome_l, nome_r)
        """
    )
    niveis = _niveis(con)
    con.close()
    for par in (
        ("NEUZIN PAULINO GUAJAJARA", "NEUZIN PAULINO PINTO GUAJAJARA"),
        ("LAUANE ALMEIDA SANTOS", "LAUANE ALMEIDA DOA SANTOS"),
        ("KAUAN MARTINS BRITO", "KAUAN MARTINS DS BRITO"),
    ):
        assert niveis[par] == "token_a_mais"
    assert niveis[
        ("ELAINE FERREIRA COSTA MATOS", "ELAINE COSTA FERREIRA MATOS")
    ] == "ordem"
    assert niveis[("MARIA SILVA", "MARIA APARECIDA SILVA")] != "token_a_mais"
    assert niveis[
        ("JOAO VIRTO LIMA CANTANHEDE", "JOAO VITOR LIMA CANTANHEDE")
    ] == "um_token"
    assert niveis[("EDYANNE MENDES", "EDYANNE MENDES CARVALHO")] == "prefixo"
