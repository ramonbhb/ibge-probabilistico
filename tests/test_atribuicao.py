"""Melhor nota por Censo; lista = CPF com até MAX_CENSOS_POR_CPF Censos no topo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MAX_CENSOS_POR_CPF


def _criar_pessoas(con: duckdb.DuckDBPyConnection, rows: list[tuple] | None = None) -> None:
    con.execute(
        """
        CREATE TABLE pessoas (
            unique_id VARCHAR,
            cep VARCHAR,
            nome_mae_phon VARCHAR,
            nome_completo_phon VARCHAR,
            data_nascimento VARCHAR
        )
        """
    )
    if rows:
        filled = [tuple(r) + (None,) * (5 - len(r)) for r in rows]
        con.executemany("INSERT INTO pessoas VALUES (?, ?, ?, ?, ?)", filled)


def _melhor_e_lista(
    con: duckdb.DuckDBPyConnection,
    threshold: float = 0.95,
    max_censos: int = MAX_CENSOS_POR_CPF,
) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE melhor_por_censo AS
        SELECT p.unique_id_censo, p.unique_id_cpf, p.match_probability
        FROM splink_predictions p
        LEFT JOIN pessoas ca ON ca.unique_id = p.unique_id_censo
        LEFT JOIN pessoas pb ON pb.unique_id = p.unique_id_cpf
        WHERE p.match_probability >= {threshold}
          AND (
                ca.nome_mae_phon IS NULL
                OR pb.nome_mae_phon IS NULL
                OR ca.nome_mae_phon = pb.nome_mae_phon
                OR jaro_winkler_similarity(ca.nome_mae_phon, pb.nome_mae_phon) >= 0.75
                OR (
                    least(
                        len(string_split(ca.nome_mae_phon, ' ')),
                        len(string_split(pb.nome_mae_phon, ' '))
                    ) >= 2
                    AND list_slice(
                        string_split(ca.nome_mae_phon, ' '),
                        1,
                        least(
                            len(string_split(ca.nome_mae_phon, ' ')),
                            len(string_split(pb.nome_mae_phon, ' '))
                        )
                    ) = list_slice(
                        string_split(pb.nome_mae_phon, ' '),
                        1,
                        least(
                            len(string_split(ca.nome_mae_phon, ' ')),
                            len(string_split(pb.nome_mae_phon, ' '))
                        )
                    )
                )
                OR (
                    ca.nome_completo_phon IS NOT NULL
                    AND pb.nome_completo_phon IS NOT NULL
                    AND ca.nome_completo_phon = pb.nome_completo_phon
                    AND ca.data_nascimento IS NOT NULL
                    AND pb.data_nascimento IS NOT NULL
                    AND ca.data_nascimento = pb.data_nascimento
                )
          )
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY p.unique_id_censo
            ORDER BY
                p.match_probability DESC,
                (
                    CAST(
                        ca.cep IS NOT NULL AND pb.cep IS NOT NULL
                        AND ca.cep = pb.cep AS INTEGER
                    )
                    + CAST(
                        ca.nome_mae_phon IS NOT NULL AND pb.nome_mae_phon IS NOT NULL
                        AND (
                            ca.nome_mae_phon = pb.nome_mae_phon
                            OR jaro_winkler_similarity(
                                ca.nome_mae_phon, pb.nome_mae_phon
                            ) >= 0.75
                            OR (
                                least(
                                    len(string_split(ca.nome_mae_phon, ' ')),
                                    len(string_split(pb.nome_mae_phon, ' '))
                                ) >= 2
                                AND list_slice(
                                    string_split(ca.nome_mae_phon, ' '),
                                    1,
                                    least(
                                        len(string_split(ca.nome_mae_phon, ' ')),
                                        len(string_split(pb.nome_mae_phon, ' '))
                                    )
                                ) = list_slice(
                                    string_split(pb.nome_mae_phon, ' '),
                                    1,
                                    least(
                                        len(string_split(ca.nome_mae_phon, ' ')),
                                        len(string_split(pb.nome_mae_phon, ' '))
                                    )
                                )
                            )
                        ) AS INTEGER
                    )
                ) DESC,
                p.unique_id_cpf
        ) = 1
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE associacoes_unicas AS
        SELECT m.*
        FROM melhor_por_censo m
        JOIN (
            SELECT unique_id_cpf
            FROM melhor_por_censo
            GROUP BY 1
            HAVING COUNT(*) <= {max_censos}
        ) c ON c.unique_id_cpf = m.unique_id_cpf
        """
    )


def _rows(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    return {
        r[0]: r[1]
        for r in con.execute(
            f"SELECT unique_id_censo, unique_id_cpf FROM {table}"
        ).fetchall()
    }


def test_dois_censos_mesmo_cpf_ficam() -> None:
    """C1-X 0,99, C2-X 0,98 → os dois ficam (n_censo = 2 ≤ 3)."""
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_B', 'cpf_Y', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert melhor == {"censo_A": "cpf_X", "censo_B": "cpf_X"}
    assert lista == {"censo_A": "cpf_X", "censo_B": "cpf_X"}


def test_tres_censos_mesmo_cpf_ficam() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_C', 'cpf_X', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert lista == {
        "censo_A": "cpf_X",
        "censo_B": "cpf_X",
        "censo_C": "cpf_X",
    }


def test_quatro_censos_mesmo_cpf_saem_todos() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_C', 'cpf_X', 0.97),
            ('censo_D', 'cpf_X', 0.96)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert lista == {}


def test_dois_pares_distintos_entram() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_Y', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert lista == {"censo_A": "cpf_X", "censo_B": "cpf_Y"}


def test_empate_p_escolhe_cep_e_mae_phon() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", "80000000", "MARIA"),
            ("cpf_X", "00000001", "JOANA"),
            ("cpf_Z", "80000000", "MARIA"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_A', 'cpf_Z', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {"censo_A": "cpf_Z"}


def test_empate_p_e_atributos_cai_no_unique_id_cpf() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_A', 'cpf_W', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert melhor == {"censo_A": "cpf_W"}
    assert lista == {"censo_A": "cpf_W"}


def test_veto_mae_escolhe_segundo() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, "MARIA JOANA CORREA"),
            ("cpf_X", None, "PEDRO SOUZA"),
            ("cpf_Z", None, "MARIA JOANA CORREA SILVA"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.995),
            ('censo_A', 'cpf_Z', 0.991)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {"censo_A": "cpf_Z"}


def test_veto_mae_ambos_discordam_sai() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, "MARIA JOANA CORREA"),
            ("cpf_X", None, "PEDRO SOUZA"),
            ("cpf_Z", None, "ANA LIMA"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.995),
            ('censo_A', 'cpf_Z', 0.991)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {}


def test_jw_mae_aceita_um_token() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, "MARIA"),
            ("cpf_X", None, "MARIA SILVA"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {"censo_A": "cpf_X"}


def test_mae_nula_nao_veta() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, None),
            ("cpf_X", None, "PEDRO SOUZA"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {"censo_A": "cpf_X"}


def test_empate_prefixo_mae_vence() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, "MARIA JOANA CORREA"),
            ("cpf_X", None, "PEDRO SOUZA"),
            ("cpf_Z", None, "MARIA JOANA CORREA SILVA"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_A', 'cpf_Z', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {"censo_A": "cpf_Z"}


def test_mae_discorda_nome_e_dob_iguais_nao_veta() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, "MARIA JOANA CORREA", "JOAO SILVA", "1990-01-15"),
            ("cpf_X", None, "PEDRO SOUZA", "JOAO SILVA", "1990-01-15"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {"censo_A": "cpf_X"}


def test_mae_discorda_nome_igual_dob_diferente_veta() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, "MARIA JOANA CORREA", "JOAO SILVA", "1990-01-15"),
            ("cpf_X", None, "PEDRO SOUZA", "JOAO SILVA", "1991-01-15"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {}


def test_mae_discorda_dob_igual_nome_diferente_veta() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", None, "MARIA JOANA CORREA", "JOAO SILVA", "1990-01-15"),
            ("cpf_X", None, "PEDRO SOUZA", "JOAO SANTOS", "1990-01-15"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {}


_NB04 = Path(__file__).resolve().parent.parent / "notebooks" / "04_atribuir.ipynb"
_NB05 = Path(__file__).resolve().parent.parent / "notebooks" / "05_adicionar_regras.ipynb"


def _celula_04(cell_id: str) -> str:
    nb = json.loads(_NB04.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell.get("id") == cell_id:
            return "".join(cell["source"])
    raise AssertionError(cell_id)


def _criar_pessoas_escada(con: duckdb.DuckDBPyConnection, rows: list[tuple]) -> None:
    con.execute(
        """
        CREATE TABLE pessoas (
            unique_id VARCHAR,
            origem VARCHAR,
            cep VARCHAR,
            nome_mae_phon VARCHAR,
            nome_completo_phon VARCHAR,
            data_nascimento VARCHAR,
            primeiro_nome_phon VARCHAR,
            ultimo_nome_phon VARCHAR,
            logradouro_norm VARCHAR,
            cod_municipio VARCHAR
        )
        """
    )
    con.executemany(
        "INSERT INTO pessoas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def _preds(con: duckdb.DuckDBPyConnection, rows: list[tuple]) -> None:
    con.execute(
        """
        CREATE TABLE splink_predictions (
            unique_id_censo VARCHAR,
            unique_id_cpf VARCHAR,
            match_probability DOUBLE
        )
        """
    )
    con.executemany("INSERT INTO splink_predictions VALUES (?, ?, ?)", rows)


def _escada(con: duckdb.DuckDBPyConnection) -> dict[str, tuple]:
    ns = {"con": con, "SPLINK_INPUT_VIEW": "pessoas", "PISO": 0.10, "TETO": 3}
    exec(_celula_04("elegiveis"), ns)
    exec(_celula_04("degraus"), ns)
    return {
        censo: (cpf, round(degrau, 3), regra)
        for censo, cpf, degrau, regra in con.execute(
            "SELECT unique_id_censo, unique_id_cpf, degrau, regra FROM atribuicao"
        ).fetchall()
    }


def _pessoa(
    unique_id: str,
    primeiro: str,
    *,
    origem: str = "censo",
    cep: str | None = None,
    mae: str | None = None,
    nome: str | None = None,
    data: str | None = None,
    ultimo: str | None = None,
    logradouro: str | None = None,
    municipio: str | None = None,
) -> tuple:
    return (
        unique_id,
        origem,
        cep,
        mae,
        nome,
        data,
        primeiro,
        ultimo,
        logradouro,
        municipio,
    )


def _frequentes() -> list[tuple]:
    linhas = []
    for i in range(10):
        nome = "MARIA" if i == 0 else f"NOME{i:02d}"
        for k in range(2):
            linhas.append(_pessoa(f"freq_{i}_{k}", nome))
    return linhas


def test_grupo_que_passa_de_3_cai() -> None:
    con = duckdb.connect()
    pessoas = [_pessoa(f"censo_{i}", "ANA") for i in range(4)]
    pessoas.append(_pessoa("cpf_X", "ANA", origem="cpf"))
    _criar_pessoas_escada(con, pessoas)
    _preds(con, [(f"censo_{i}", "cpf_X", 0.99) for i in range(4)])
    lista = _escada(con)
    con.close()
    assert lista == {}


def test_dois_ja_atribuidos_e_dois_novos_caem() -> None:
    con = duckdb.connect()
    pessoas = [
        _pessoa("censo_A", "ANA"),
        _pessoa("censo_B", "ANA"),
        _pessoa("censo_C", "ANA", mae="MARIA SILVA"),
        _pessoa("censo_D", "ANA", mae="MARIA SILVA"),
        _pessoa("cpf_X", "ANA", origem="cpf", mae="MARIA SILVA"),
    ]
    _criar_pessoas_escada(con, pessoas)
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.99),
            ("censo_B", "cpf_X", 0.991),
            ("censo_C", "cpf_X", 0.98),
            ("censo_D", "cpf_X", 0.981),
        ],
    )
    lista = _escada(con)
    con.close()
    assert set(lista) == {"censo_A", "censo_B"}
    assert lista["censo_A"][1:] == (0.99, "score")


def test_terceiro_ainda_cabe() -> None:
    con = duckdb.connect()
    pessoas = [
        _pessoa("censo_A", "ANA"),
        _pessoa("censo_B", "ANA"),
        _pessoa("censo_C", "ANA", mae="MARIA SILVA"),
        _pessoa("cpf_X", "ANA", origem="cpf", mae="MARIA SILVA"),
    ]
    _criar_pessoas_escada(con, pessoas)
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.99),
            ("censo_B", "cpf_X", 0.991),
            ("censo_C", "cpf_X", 0.98),
        ],
    )
    lista = _escada(con)
    con.close()
    assert set(lista) == {"censo_A", "censo_B", "censo_C"}
    assert lista["censo_C"] == ("cpf_X", 0.975, "mae")


def test_jw_mae_entra_como_mae() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "ANA", mae="JEANE PEREIRA SERRA"),
            _pessoa("cpf_X", "ANA", origem="cpf", mae="GEANE PEREIRA SERRA"),
        ],
    )
    _preds(con, [("censo_A", "cpf_X", 0.96)])
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.95, "mae")


def test_entre_095_e_099_nao_aplica_veto() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa(
                "censo_A",
                "JOAO",
                mae="MARIA JOANA CORREA",
                logradouro="RUA A",
                municipio="2111300",
            ),
            _pessoa(
                "cpf_X",
                "JOSE",
                origem="cpf",
                mae="PEDRO SOUZA",
                logradouro="RUA A",
                municipio="2111300",
            ),
            _pessoa(
                "censo_B",
                "JOAO",
                mae="MARIA JOANA CORREA",
                logradouro="RUA A",
                municipio="2111300",
            ),
            _pessoa(
                "cpf_Y",
                "JOSE",
                origem="cpf",
                mae="PEDRO SOUZA",
                logradouro="RUA A",
                municipio="2111300",
            ),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.96),
            ("censo_B", "cpf_Y", 0.94),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.95, "logradouro")
    assert "censo_B" not in lista


def test_acima_de_099_nao_veta_mae() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "ANA", mae="MARIA JOANA CORREA"),
            _pessoa("cpf_X", "ANA", origem="cpf", mae="PEDRO SOUZA"),
            _pessoa("censo_B", "ANA", mae="MARIA JOANA CORREA"),
            _pessoa("cpf_Y", "ANA", origem="cpf", mae="PEDRO SOUZA"),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.991),
            ("censo_B", "cpf_Y", 0.94),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.99, "score")
    assert "censo_B" not in lista


def test_primeiro_nome_levenshtein_2_nao_entra() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "JOAO"),
            _pessoa("cpf_X", "JOSE", origem="cpf"),
            _pessoa("censo_B", "JOAO"),
            _pessoa("cpf_Y", "JOA", origem="cpf"),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.99),
            ("censo_B", "cpf_Y", 0.99),
        ],
    )
    lista = _escada(con)
    con.close()
    assert "censo_A" not in lista
    assert lista["censo_B"] == ("cpf_Y", 0.99, "score")


def test_corroborador_escolhe_a_primeira_regra() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa(
                "censo_A",
                "ANA",
                mae="MARIA SILVA",
                logradouro="RUA A",
                municipio="210140",
            ),
            _pessoa(
                "cpf_X",
                "ANA",
                origem="cpf",
                mae="MARIA SILVA",
                logradouro="RUA A",
                municipio="210140",
            ),
        ],
    )
    _preds(con, [("censo_A", "cpf_X", 0.98)])
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.975, "mae")


def test_nome_frequente_bloqueia_regras_5_e_6_e_quatro_em_cinco_passa() -> None:
    con = duckdb.connect()
    pessoas = _frequentes()
    pessoas += [
        _pessoa("censo_M", "MARIA", nome="MARIA SILVA SANTOS", cep="65000000"),
        _pessoa(
            "cpf_M",
            "MARIA",
            origem="cpf",
            nome="MARIA SILVA SANTOS",
            cep="65000000",
        ),
        _pessoa(
            "censo_Z",
            "ZAQUEU",
            nome="ZAQUEU PAULA SOUZA LIMA COSTA",
            cep="65000001",
        ),
        _pessoa(
            "cpf_Z",
            "ZAQUEU",
            origem="cpf",
            nome="ZAQUEU PAULA SOUZA LIMA SILVA",
            cep="65000001",
        ),
        _pessoa(
            "censo_R",
            "RUTE",
            nome="RUTE ALFA BETA GAMA DELTA",
            cep="65000002",
        ),
        _pessoa(
            "cpf_R",
            "RUTE",
            origem="cpf",
            nome="RUTE ALFA BETA XXXX YYYY",
            cep="65000002",
        ),
    ]
    _criar_pessoas_escada(con, pessoas)
    _preds(
        con,
        [
            ("censo_M", "cpf_M", 0.98),
            ("censo_Z", "cpf_Z", 0.98),
            ("censo_R", "cpf_R", 0.98),
        ],
    )
    lista = _escada(con)
    con.close()
    assert "censo_M" not in lista
    assert "censo_R" not in lista
    assert lista["censo_Z"] == ("cpf_Z", 0.975, "tokens_cep")


def test_ate_080_dois_censos_no_mesmo_cpf_entram() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "ANA", mae="MARIA SILVA"),
            _pessoa("censo_B", "ANA", mae="MARIA SILVA"),
            _pessoa("cpf_X", "ANA", origem="cpf", mae="MARIA SILVA"),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.91),
            ("censo_B", "cpf_X", 0.90),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.9, "mae")
    assert lista["censo_B"] == ("cpf_X", 0.9, "mae")


def test_jw_mae_alto_ate_070_entra_com_data_diferente() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "ANA", mae="JEANE PEREIRA SERRA", data="2006-07-05"),
            _pessoa("censo_B", "ANA", mae="JEANE PEREIRA SERRA"),
            _pessoa(
                "cpf_X",
                "ANA",
                origem="cpf",
                mae="GEANE PEREIRA SERRA",
                data="2004-07-05",
            ),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.72),
            ("censo_B", "cpf_X", 0.71),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.7, "mae")
    assert lista["censo_B"] == ("cpf_X", 0.7, "mae")


def test_mae_contida_de_050_entra() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "ANA", mae="MARIA OLIVEIRA"),
            _pessoa(
                "cpf_X",
                "ANA",
                origem="cpf",
                mae="MARIA CRECENCIA CONCEICAO OLIVEIRA",
            ),
            _pessoa("censo_B", "LIA", mae="MARIA OLIVEIRA"),
            _pessoa(
                "cpf_Y",
                "LIA",
                origem="cpf",
                mae="MARIA CRECENCIA CONCEICAO OLIVEIRA",
            ),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.88),
            ("censo_B", "cpf_Y", 0.49),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.875, "mae")
    assert "censo_B" not in lista


def test_jw_mae_alto_ate_050_entra_com_dois_censos() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "ANA", mae="JEANE PEREIRA SERRA"),
            _pessoa("censo_B", "ANA", mae="JEANE PEREIRA SERRA"),
            _pessoa("cpf_X", "ANA", origem="cpf", mae="GEANE PEREIRA SERRA"),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.69),
            ("censo_B", "cpf_X", 0.68),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_X", 0.675, "mae")
    assert lista["censo_B"] == ("cpf_X", 0.675, "mae")


def test_um_para_um_abaixo_de_050_recusa_cpf_com_dois_censos() -> None:
    con = duckdb.connect()
    _criar_pessoas_escada(
        con,
        [
            _pessoa("censo_A", "ANA", mae="MARIA SILVA"),
            _pessoa("censo_B", "ANA", mae="MARIA SILVA"),
            _pessoa("cpf_X", "ANA", origem="cpf", mae="MARIA SILVA"),
            _pessoa("censo_C", "LIA", mae="JOANA SOUZA"),
            _pessoa("cpf_Y", "LIA", origem="cpf", mae="JOANA SOUZA"),
        ],
    )
    _preds(
        con,
        [
            ("censo_A", "cpf_X", 0.49),
            ("censo_B", "cpf_X", 0.48),
            ("censo_C", "cpf_Y", 0.485),
        ],
    )
    lista = _escada(con)
    con.close()
    assert "censo_A" not in lista
    assert "censo_B" not in lista
    assert lista["censo_C"] == ("cpf_Y", 0.475, "mae")


def test_data_uma_palavra_aceita_uma_palavra_diferente() -> None:
    con = duckdb.connect()
    pessoas = _frequentes()
    pessoas += [
        _pessoa(
            "censo_J",
            "JONARA",
            nome="JONARA SOUZA NUNIS",
            data="1993-12-31",
        ),
        _pessoa(
            "cpf_J",
            "DIONARIA",
            origem="cpf",
            nome="DIONARIA SOUZA NUNIS",
            data="1993-12-31",
        ),
        _pessoa(
            "censo_V",
            "JEAN",
            nome="JEAN KARLUS VELOZU VILAR",
            data="1983-02-17",
        ),
        _pessoa(
            "cpf_V",
            "JEAN",
            origem="cpf",
            nome="JEAN KARLUS BAROZU VILAR",
            data="1983-02-17",
        ),
        _pessoa(
            "censo_P",
            "ANTONIU",
            nome="ANTONIU PENHA SANTUS",
            data="1981-08-22",
        ),
        _pessoa(
            "cpf_P",
            "ANTONIU",
            origem="cpf",
            nome="ANTONIU LEAU SANTUS",
            data="1981-08-22",
        ),
        _pessoa(
            "censo_M",
            "MARIA",
            nome="MARIA JOSE SANTOS",
            data="1990-01-01",
        ),
        _pessoa(
            "cpf_M",
            "MARIA",
            origem="cpf",
            nome="MARIA JOZE SANTOS",
            data="1990-01-01",
        ),
    ]
    _criar_pessoas_escada(con, pessoas)
    _preds(
        con,
        [
            ("censo_J", "cpf_J", 0.92),
            ("censo_V", "cpf_V", 0.92),
            ("censo_P", "cpf_P", 0.92),
            ("censo_M", "cpf_M", 0.92),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_J"] == ("cpf_J", 0.9, "data_uma_palavra")
    assert lista["censo_V"] == ("cpf_V", 0.9, "data_uma_palavra")
    assert "censo_P" not in lista
    assert "censo_M" not in lista


def test_data_uma_palavra_aceita_data_com_um_ano() -> None:
    con = duckdb.connect()
    pessoas = _frequentes()
    pessoas += [
        _pessoa(
            "censo_A",
            "ZZZ",
            nome="ISVANIR ZESTEVES CONSAGRADU KLECILDES",
            data="2001-05-01",
        ),
        _pessoa(
            "cpf_A",
            "ZZZ",
            origem="cpf",
            nome="ISVANIR ZESTEVES CONSAGRADU KLECILDES",
            data="2002-05-01",
        ),
        _pessoa(
            "censo_N",
            "ZZY",
            nome="ISVANIR ZESTEVES CONSAGRADU KLECILDES",
        ),
        _pessoa(
            "cpf_N",
            "ZZY",
            origem="cpf",
            nome="ISVANIR ZESTEVES CONSAGRADU KLECILDES",
        ),
    ]
    _criar_pessoas_escada(con, pessoas)
    _preds(
        con,
        [
            ("censo_A", "cpf_A", 0.92),
            ("censo_N", "cpf_N", 0.92),
        ],
    )
    lista = _escada(con)
    con.close()
    assert lista["censo_A"] == ("cpf_A", 0.9, "data_uma_palavra")
    assert "censo_N" not in lista


def test_05_nao_tem_sql() -> None:
    nb = json.loads(_NB05.read_text(encoding="utf-8"))
    assert all(cell["cell_type"] != "code" for cell in nb["cells"])
    texto = "\n".join("".join(cell["source"]) for cell in nb["cells"])
    assert "04_atribuir.ipynb" in texto
    assert "SELECT" not in texto
