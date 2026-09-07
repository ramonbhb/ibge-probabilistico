"""Nível Splink de data: mês/dia iguais e |Δano| ≤ 1; |Δano| = 10 não entra."""

from __future__ import annotations

import duckdb

MES_DIA_ANO_SQL = """
    mes_l = mes_r
    AND dia_l = dia_r
    AND mes_l IS NOT NULL AND dia_l IS NOT NULL
    AND ano_l IS NOT NULL AND ano_r IS NOT NULL
    AND abs(TRY_CAST(ano_l AS INTEGER) - TRY_CAST(ano_r AS INTEGER)) <= 1
"""


def _nivel(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.execute(
        f"""
        SELECT data_l, data_r,
            CASE
                WHEN data_l = data_r THEN 'exact'
                WHEN {MES_DIA_ANO_SQL} THEN 'ano1'
                ELSE 'else'
            END AS nivel
        FROM pares
        ORDER BY data_l, data_r
        """
    ).fetchall()


def test_delta_1_entra_delta_10_nao_exact_nao_cai_no_nivel() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE pares AS SELECT * FROM (VALUES
            ('1985-05-07', '1985', '05', '07', '1985-05-07', '1985', '05', '07'),
            ('1999-05-07', '1999', '05', '07', '2000-05-07', '2000', '05', '07'),
            ('1990-05-07', '1990', '05', '07', '2000-05-07', '2000', '05', '07')
        ) v(data_l, ano_l, mes_l, dia_l, data_r, ano_r, mes_r, dia_r)
        """
    )
    niveis = { (a, b): n for a, b, n in _nivel(con) }
    con.close()
    assert niveis[("1985-05-07", "1985-05-07")] == "exact"
    assert niveis[("1999-05-07", "2000-05-07")] == "ano1"
    assert niveis[("1990-05-07", "2000-05-07")] == "else"
