"""Faixa 0,95–0,99: regras mae_phon / nome+cep / pontas+cep; CPF do 04 não entra."""

from __future__ import annotations

import duckdb


def _montar_05(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE extra_regras AS
        SELECT
            m.unique_id_censo,
            m.unique_id_cpf,
            m.match_probability,
            CASE
                WHEN ca.nome_mae_phon IS NOT NULL AND pb.nome_mae_phon IS NOT NULL
                     AND (
                         ca.nome_mae_phon = pb.nome_mae_phon
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
                     )
                    THEN 'mae_phon'
                WHEN ca.nome_completo_phon IS NOT NULL
                     AND pb.nome_completo_phon IS NOT NULL
                     AND ca.nome_completo_phon = pb.nome_completo_phon
                     AND ca.cep IS NOT NULL AND pb.cep IS NOT NULL AND ca.cep = pb.cep
                    THEN 'nome_cep'
                WHEN ca.primeiro_nome_phon IS NOT NULL
                     AND pb.primeiro_nome_phon IS NOT NULL
                     AND ca.primeiro_nome_phon = pb.primeiro_nome_phon
                     AND ca.ultimo_nome_phon IS NOT NULL
                     AND pb.ultimo_nome_phon IS NOT NULL
                     AND ca.ultimo_nome_phon = pb.ultimo_nome_phon
                     AND ca.cep IS NOT NULL AND pb.cep IS NOT NULL AND ca.cep = pb.cep
                    THEN 'pontas_cep'
            END AS regra
        FROM melhor_faixa m
        JOIN pessoas ca ON ca.unique_id = m.unique_id_censo
        JOIN pessoas pb ON pb.unique_id = m.unique_id_cpf
        WHERE (
            ca.nome_mae_phon IS NOT NULL AND pb.nome_mae_phon IS NOT NULL
            AND (
                ca.nome_mae_phon = pb.nome_mae_phon
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
            )
        )
        OR (
            ca.nome_completo_phon IS NOT NULL AND pb.nome_completo_phon IS NOT NULL
            AND ca.nome_completo_phon = pb.nome_completo_phon
            AND ca.cep IS NOT NULL AND pb.cep IS NOT NULL AND ca.cep = pb.cep
        )
        OR (
            ca.primeiro_nome_phon IS NOT NULL AND pb.primeiro_nome_phon IS NOT NULL
            AND ca.primeiro_nome_phon = pb.primeiro_nome_phon
            AND ca.ultimo_nome_phon IS NOT NULL AND pb.ultimo_nome_phon IS NOT NULL
            AND ca.ultimo_nome_phon = pb.ultimo_nome_phon
            AND ca.cep IS NOT NULL AND pb.cep IS NOT NULL AND ca.cep = pb.cep
        )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE extra_unicas AS
        SELECT e.*
        FROM extra_regras e
        JOIN (
            SELECT unique_id_cpf FROM extra_regras
            GROUP BY 1 HAVING COUNT(*) <= 3
        ) c ON c.unique_id_cpf = e.unique_id_cpf
        """
    )


def _ids(con, table: str) -> set[str]:
    return {
        r[0]
        for r in con.execute(f"SELECT unique_id_censo FROM {table}").fetchall()
    }


def test_faixa_mae_phon_entra() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', 'MARIA', 'JOAO', 'SILVA', 'AAAA', NULL),
            ('cpf_X', 'MARIA', 'JOAO', 'SOUZA', 'BBBB', NULL)
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    assert _ids(con, "extra_unicas") == {"censo_A"}
    regra = con.execute(
        "SELECT regra FROM extra_unicas WHERE unique_id_censo = 'censo_A'"
    ).fetchone()[0]
    assert regra == "mae_phon"
    con.close()


def test_faixa_mae_prefixo_entra() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', 'MARIA JOANA CORREA', 'JOAO', 'SILVA', 'AAAA', NULL),
            ('cpf_X', 'MARIA JOANA CORREA SILVA', 'PEDRO', 'SOUZA', 'BBBB', NULL)
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    regra = con.execute("SELECT regra FROM extra_unicas").fetchone()[0]
    assert regra == "mae_phon"
    con.close()


def test_faixa_mae_um_token_nao_prefixa() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', 'MARIA', 'JOAO', 'SILVA', 'AAAA', NULL),
            ('cpf_X', 'MARIA SILVA', 'PEDRO', 'SOUZA', 'BBBB', NULL)
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    assert _ids(con, "extra_unicas") == set()
    con.close()


def test_faixa_pontas_cep_entra() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.96)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', CAST(NULL AS VARCHAR), 'JOAO', 'SILVA', 'JOAO MEIO SILVA', '80000000'),
            ('cpf_X', CAST(NULL AS VARCHAR), 'JOAO', 'SILVA', 'JOAO SILVA', '80000000')
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    assert _ids(con, "extra_unicas") == {"censo_A"}
    regra = con.execute("SELECT regra FROM extra_unicas").fetchone()[0]
    assert regra == "pontas_cep"
    con.close()


def test_prioridade_mae_vence_nome_cep() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.96)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', 'MARIA', 'JOAO', 'SILVA', 'JOAO SILVA', '80000000'),
            ('cpf_X', 'MARIA', 'JOAO', 'SILVA', 'JOAO SILVA', '80000000')
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    regra = con.execute("SELECT regra FROM extra_unicas").fetchone()[0]
    assert regra == "mae_phon"
    con.close()


def test_prioridade_nome_cep_vence_pontas() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.96)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', CAST(NULL AS VARCHAR), 'JOAO', 'SILVA', 'JOAO SILVA', '80000000'),
            ('cpf_X', CAST(NULL AS VARCHAR), 'JOAO', 'SILVA', 'JOAO SILVA', '80000000')
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    regra = con.execute("SELECT regra FROM extra_unicas").fetchone()[0]
    assert regra == "nome_cep"
    con.close()


def test_faixa_sem_regra_nao_entra() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.96)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', 'MARIA', 'JOAO', 'SILVA', 'AAAA', '80000000'),
            ('cpf_X', 'JOANA', 'PEDRO', 'SOUZA', 'BBBB', '90000000')
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    assert _ids(con, "extra_unicas") == set()
    con.close()


def test_mae_nula_nao_casa() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE melhor_faixa AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE pessoas AS SELECT * FROM (VALUES
            ('censo_A', CAST(NULL AS VARCHAR), 'JOAO', 'SILVA', 'AAAA', NULL),
            ('cpf_X', CAST(NULL AS VARCHAR), 'PEDRO', 'SOUZA', 'BBBB', NULL)
        ) v(unique_id, nome_mae_phon, primeiro_nome_phon, ultimo_nome_phon,
            nome_completo_phon, cep)
        """
    )
    _montar_05(con)
    assert _ids(con, "extra_unicas") == set()
    con.close()
