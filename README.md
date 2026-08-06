# Linkage probabilístico — Censo × CPF

Pipeline interativo (notebooks + DuckDB) para empilhar **bases bronze** CPF e Censo, rodar **Splink dedupe_only** cross-source e avaliar contra **ground truth** da coorte (`cohort_dedup`).

## Pré-requisitos

1. Parquets bronze + `cohort_dedup.parquet` ([`cohort/`](../cohort/))
2. `pip install -e .` em `probabilistico/`

## Configuração

Edite [`config.py`](config.py) ou exporte:

```bash
export FILTRO_UF=35
export OUTPUT_DIR=~/data/probabilistico_output
export USE_PHONETIC_STRIP_VOWELS=false   # true = colunas *_phon_sv (remove vogais)
# CENSO_CEP_ARQUIVO default: ~/singed/bases/raw/Censo/data_cep_uniq.csv
```

## Notebooks

| Notebook | Função |
|----------|--------|
| [`00_preparar_bases.ipynb`](notebooks/00_preparar_bases.ipynb) | Bronze → filtro UF → inferência mãe → CEP (`data_cep_uniq`) → stack + GT |
| [`00_preparar_bases_leve.ipynb`](notebooks/00_preparar_bases_leve.ipynb) | Igual ao NB00, split SQL rápido (sem fonética) — ideal para iterar Splink |
| [`01_analise_descritiva.ipynb`](notebooks/01_analise_descritiva.ipynb) | EDA visual: missing, top nomes, sexo, DOB, CEP, UF |
| [`01_explorar_variaveis.ipynb`](notebooks/01_explorar_variaveis.ipynb) | Splink: profile, blocking, draft settings |
| [`02_deduplicar_splink.ipynb`](notebooks/02_deduplicar_splink.ipynb) | Splink + métricas vs coorte |

**REBUILD:** no NB00, `REBUILD=False` reutiliza `probabilistico.duckdb` sem refazer.

Referências: [`notebooks/_exemplo/`](notebooks/_exemplo/) (Splink + inferência mãe didática).

## Variáveis unificadas

- Nome: completo, primeiro/meio/último
- **`nome_mae`:** CPF direto (`NOM_MAE`); Censo **inferido** por domicílio ([`inferir_pais.py`](inferir_pais.py))
- **CEP Censo:** join `data_cep_uniq.csv` por `B0000` + quadra/face ([`materialize_censo_cep_lookup`](config.py))
- Sexo, DOB, CEP, **UF** (sem coluna `estado`)
- Fonética **básica** sempre: `*_phon` (substituições PT-BR)
- Fonética **agressiva** opcional: `*_phon_sv` (`USE_PHONETIC_STRIP_VOWELS=true`)

## Saídas

`~/data/probabilistico_output/`: `probabilistico.duckdb`, `registro_unificado.parquet`, `ground_truth_clusters.parquet`, artefatos Splink.

## Ground truth

Somente `cohort_dedup.parquet` — ouro + prata. Listas ouro **não** entram como dado de entrada.
