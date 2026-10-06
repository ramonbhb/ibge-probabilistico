"""Spec do modelo v2 (mãe + endereço) e atribuição por faixas + resgate."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
NB02C = ROOT / "notebooks" / "02c_treinar_splink_mae_endereco.ipynb"
NB04 = ROOT / "notebooks" / "04_atribuir_mae_endereco.ipynb"


def _celula(nb_path: Path, cell_id: str) -> str:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell.get("id") == cell_id:
            return "".join(cell["source"])
    raise AssertionError(cell_id)


def test_02c_comparisons_mae_endereco_sem_uf() -> None:
    src = _celula(NB02C, "0b32ea1f")
    assert "output_column_name='nome_completo_phon'" in src
    assert "output_column_name='data_nascimento'" in src
    assert "output_column_name='nome_mae_phon'" in src
    assert "output_column_name='endereco'" in src
    assert "label_for_charts='Contida'" in src
    assert "Logradouro e CEP exact" in src
    assert "ExactMatch('uf')" not in src
    assert 'ExactMatch("uf")' not in src


def test_02c_em_mae_e_endereco() -> None:
    src = _celula(NB02C, "em-cpf")
    assert "em_mae" in src
    assert "em_endereco" in src
    assert "block_on('nome_completo_phon', 'data_nascimento')" in src


def test_04_escada_resgate_spec() -> None:
    nb = json.loads(NB04.read_text(encoding="utf-8"))
    texto = "\n".join("".join(c["source"]) for c in nb["cells"])
    assert "PISO_MODELO = 0.90" in texto
    assert "PISO_RESGATE = 0.50" in texto
    assert "PISO_BAIXO = 0.25" in texto
    assert "regra_medio" in texto
    assert "regra_baixo" in texto
    assert "r1_medio" in texto
    assert "data_plausivel" in texto
    assert "libera_11" not in texto
    assert "degraus = [" not in texto
    assert "faixa VARCHAR" in texto
    assert "coalesce(j.n_ja, 0) + g.n_novo <= {TETO}" in texto


def test_atribuicao_faixas_teto_e_desempate() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE pares (
            unique_id_censo VARCHAR,
            unique_id_cpf VARCHAR,
            match_probability DOUBLE,
            desempate INTEGER,
            regra_medio VARCHAR,
            regra_baixo VARCHAR
        )
        """
    )
    # A: empate 0.80 (resgate) — X tem desempate maior → X
    # B: 0.70 resgate com regra → Y
    # C: 0.95 modelo → Z (n_ja=1)
    # D,E: resgate no Z → 1+2<=3, entram; F+G no mesmo lote fariam 1+4>3
    #     então só D,E (2 novos) com regra; F sem regra no resgate
    # H: 0.40 baixo sem regra → fora
    # I: 0.40 baixo com regra_baixo → W
    # J: baixo no Z com regra → Z já tem 3 → bloqueado (COUNT >= TETO)
    con.executemany(
        "INSERT INTO pares VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("censo_A", "cpf_X", 0.80, 3, "R1", None),
            ("censo_A", "cpf_Y", 0.80, 1, "R1", None),
            ("censo_B", "cpf_Y", 0.70, 0, "R2", None),
            ("censo_C", "cpf_Z", 0.95, 0, None, None),
            ("censo_D", "cpf_Z", 0.88, 0, "R1", None),
            ("censo_E", "cpf_Z", 0.87, 0, "R1", None),
            ("censo_F", "cpf_Z", 0.86, 0, None, None),
            ("censo_H", "cpf_W", 0.40, 0, None, None),
            ("censo_I", "cpf_W", 0.40, 0, None, "R1"),
            ("censo_J", "cpf_Z", 0.40, 0, None, "R1"),
        ],
    )
    ns = {
        "con": con,
        "PISO_MODELO": 0.90,
        "PISO_RESGATE": 0.50,
        "PISO_BAIXO": 0.25,
        "TETO": 3,
    }
    exec(_celula(NB04, "atribuir"), ns)
    lista = {
        r[0]: (r[1], r[2], r[3])
        for r in con.execute(
            "SELECT unique_id_censo, unique_id_cpf, faixa, regra FROM atribuicao"
        ).fetchall()
    }
    con.close()

    assert lista["censo_A"] == ("cpf_X", "resgate", "R1")
    assert lista["censo_B"] == ("cpf_Y", "resgate", "R2")
    assert lista["censo_C"] == ("cpf_Z", "modelo", "score")
    # Z: C (modelo) + D + E (resgate) = 3; F sem regra; J bloqueado (teto)
    assert lista["censo_D"] == ("cpf_Z", "resgate", "R1")
    assert lista["censo_E"] == ("cpf_Z", "resgate", "R1")
    assert "censo_F" not in lista
    assert "censo_H" not in lista
    assert lista["censo_I"] == ("cpf_W", "baixo", "R1")
    assert "censo_J" not in lista
