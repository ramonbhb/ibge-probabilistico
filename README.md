# Linkage probabilístico — Censo × CPF

Pipeline interativo (notebooks + DuckDB) para empilhar **bases bronze** CPF e Censo, rodar **Splink link_only** (Censo × CPF, sem pares intra-base) e avaliar contra **ground truth** da coorte (`cohort_dedup`).

Treino e validação são separados: o modelo é treinado sem ver a coorte (NB02). Labels Splink (qualidade do scoring) no NB03; funil da lista ouro (Censo → CPF) no NB04. Avaliação usa **threshold / clusters 0,95**.

## Pré-requisitos

1. Parquets bronze + `cohort_dedup.parquet` ([`cohort/`](../cohort/))
2. `pip install -e .` em `probabilistico/`

## Configuração

### Parâmetros de análise — só em [`config.py`](config.py)

Recorte geográfico e fonética mudam a cada rodada e ficam versionados, no bloco `PARÂMETROS DE ANÁLISE` no topo do arquivo:

```python
FILTRO_UF: str | int | None = None            # ex.: 42 (SC); None = nacional
FILTRO_MUNICIPIO: str | int | None = 2111300  # IBGE 7 díg.; None = sem filtro
USE_PHONETIC_STRIP_VOWELS = False             # True = colunas *_phon_sv (remove vogais)
ANO_OBITO_CORTE = 2023                        # ano_obito <= corte sai da base (NB00b)
DATA_REFERENCIA_IDADE = "2022-08-01"           # idade CPF = anos completos nesta data
ANO_NASCIMENTO_MIN = 1900                     # ano fora de [MIN, 2022] anula a data
SEXO_VALIDOS = ("M", "F")                     # fora daqui o sexo vira NULL
```

Não existem `export FILTRO_UF` / `export FILTRO_MUNICIPIO`: filtro é parâmetro de análise, não configuração de ambiente.

Para sobrescrever o filtro só na sessão atual de um notebook, use `config.set_filtros()` — nunca reatribua `FILTRO_UF` / `FILTRO_MUNICIPIO`:

```python
import config
config.set_filtros(municipio=2111300)   # None desliga o filtro
print(config.FILTRO_UF, config.FILTRO_MUNICIPIO)
```

`from config import FILTRO_UF` copia o valor no momento do import; reatribuir essa cópia deixa o notebook exibindo o filtro novo enquanto as funções de filtro continuam usando o antigo.

### Caminhos e recursos — variam por máquina

Têm default em `config.py` e aceitam variável de ambiente:

```bash
export OUTPUT_DIR=~/data/probabilistico_output
export DUCKDB_THREADS=20           # Splink/DuckDB
export DUCKDB_MEMORY_LIMIT=300GB   # Splink/DuckDB
```

Também aceitam override por ambiente: `CENSO_DIR`, `CENSO_RAW_DIR`, `CENSO_CEP_ARQUIVO` (default `~/singed/bases/raw/censo/data_cep_uniq.csv`), `CENSO_PESSOAS_ARQUIVO`, `CPF_ARQUIVO`, `COHORT_DIR`, `COHORT_DEDUP_ARQUIVO`, `DUCKDB_TEMP_DIR`.

## Notebooks

| Notebook | Função |
|----------|--------|
| [`00_preparar_bases.ipynb`](notebooks/00_preparar_bases.ipynb) | Bronze → filtro UF/município → inferência mãe → CEP → stack |
| [`00b_limpar_dados.ipynb`](notebooks/00b_limpar_dados.ipynb) | Remove óbito ≤ corte e registros sem nome (Censo e CPF); anula data inválida e sentinelas |
| [`01_analise_descritiva.ipynb`](notebooks/01_analise_descritiva.ipynb) | EDA visual: missing, top nomes, sexo, DOB, idade, CEP, UF, município |
| [`02_deduplicar_splink.ipynb`](notebooks/02_deduplicar_splink.ipynb) | Profile + blocking + treino `link_only` (1ª passada sem mãe) + predict/cluster 0,95 |
| [`03_validar_coorte.ipynb`](notebooks/03_validar_coorte.ipynb) | Labels Splink (matches conhecidos + pares distintos) → P/R, FP/FN a 0,95 |
| [`04_validar_lista_ouro.ipynb`](notebooks/04_validar_lista_ouro.ipynb) | Funil Censo → CPF ouro nos clusters 0,95 (`recall_ouro`) |

**Pipeline:** `00` → `00b` → `01` → `02` → `03` (labels) → `04` (ouro).

Do NB00b em diante tudo consome `registro_limpo`, não `registro_unificado`. O `materialize_splink_input` resolve isso sozinho e avisa alto se cair na tabela suja.

O NB03 recarrega o modelo do JSON (labels, sem reestimar). O NB04 usa `splink_clusters.parquet`. `predict()` no NB02 pode gerar pares ≥0,5; **métricas de validação usam 0,95 / clusters**.

**1ª passada do modelo (NB02):** sem `nome_mae*` (Censo ~29% preenchido; exact dava peso demais). Nomes fonéticos: exact + Jaro-Winkler 0,95 e 0,90. DOB: `ExactMatch('data_nascimento')` + TF (string ISO `YYYY-MM-DD`). Idade: exact e `abs(diff) ≤ 1`. UF no score (`ExactMatch` + TF). Sem CEP no blocking nem no scoring. Mãe fica para uma 2ª passada. Cópia do JSON em [`models/splink_model.json`](models/splink_model.json).

**REBUILD:** no NB00, `REBUILD=False` reutiliza `probabilistico.duckdb` sem refazer. **`REFILTER_GEO=True`** refaz só filtro UF/município.

**Blocking Splink:** cinco regras OR no NB02 (e as mesmas no `pares_distintos` do NB03). Partes da data vêm da view `splink_input` (`ano_nascimento` / `mes_nascimento` / `dia_nascimento`, `substr` da ISO). Sem exigir UF (interestadual entra). CEP não entra.

- `primeiro_nome_phon` + `ultimo_nome_phon` + `sexo` + `ano_nascimento` (mês/dia errados)
- `primeiro_nome_phon` + `ultimo_nome_phon` + `sexo` + `mes_nascimento` + `dia_nascimento` (ano errado)
- `primeiro_nome_phon` + `ultimo_nome_phon` + `sexo` + `mes_nascimento` + `ano_nascimento` (dia errado)
- `primeiro_nome_phon` + `sexo` + `data_nascimento` (último nome errado)
- `ultimo_nome_phon` + `sexo` + `data_nascimento` (primeiro nome errado)

Profile e gráfico cumulativo de pares candidatos rodam **antes** do treino. O `Linker` usa duas views (`splink_censo` / `splink_cpf`) com `link_type='link_only'`.

**Splink:** pin [`splink==5.0.0.dev1`](https://pypi.org/project/splink/5.0.0.dev1/). O `Linker` ainda recebe `db_api=` (contrato desta versão). Saídas de comparação usam prefixo `mw_` (match weight) em vez de `bf_`; JSON antigo com `bayes_factor_column_prefix` é ignorado — retreinar no NB02. `predict()` aceita `num_chunks_left` / `num_chunks_right` para volume grande.

Referências: [`notebooks/_exemplo/`](notebooks/_exemplo/) (Splink + inferência mãe didática).

## Variáveis unificadas

- Nome: completo, primeiro/meio/último (partículas `DA`, `DOS`, etc. e placeholders `DESCONHECIDO`, `MAE` removidos por [`clean_name_sql`](features.py); vazio → `NULL`)
- **`nome_mae`:** CPF direto (`NOM_MAE`); Censo **inferido** por domicílio ([`inferir_pais.py`](inferir_pais.py)). Sofre o mesmo split da pessoa: `primeiro_nome_mae`, `nome_meio_mae`, `ultimo_nome_mae`, com as fonéticas correspondentes. Vazio vira `NULL` (`NULLIF`), para o Splink não casar `'' = ''`
- **CEP Censo:** join `data_cep_uniq.csv` por `B0000` + quadra/face ([`materialize_censo_cep_lookup`](config.py))
- Sexo, DOB, **idade**, CEP, **UF**, **`cod_municipio`** (IBGE 7 díg.)
- **`ano_obito`:** só CPF, `NULL` no Censo. Não entra em comparação — existe para o filtro do NB00b e para auditoria
- **`idade`:** Censo via `PECP0401`; CPF = anos completos em `DATA_REFERENCIA_IDADE` ([`idade_censo_sql`](config.py), [`idade_cpf_sql`](config.py)). Ver abaixo
- Fonética **básica** sempre: `*_phon` (substituições PT-BR)
- Fonética **agressiva** opcional: `*_phon_sv` (`USE_PHONETIC_STRIP_VOWELS=True`)

### Idade

No Censo a idade vem de **`PECP0401`** (variável auxiliar calculada, 0–140 anos, universo). No CPF é derivada de `data_nascimento` como anos completos em **`DATA_REFERENCIA_IDADE`** (`2022-08-01`), via `age()` no DuckDB — não é só `2022 - ano`. No Splink a comparação usa exact e `abs(idade_l - idade_r) ≤ 1` (não colunas `idade±1`). As colunas do questionário (`PECP0003`/`PECP0030`) ficam só no diagnóstico do NB00.

Se a idade vier muito nula, a célula **3b do NB00** aponta a causa: tipos das colunas, contagem de nulos de cada lado e os valores crus mais frequentes. Dois casos conhecidos que zeram a idade do CPF inteiro:

- `DAT_NASCIMENTO` como **inteiro de 8 dígitos** (`19900102`) ou string compacta. O `normalize_date_sql` do `ibge_common` só reconhece data com separador. Por isso existe [`normalize_date_compacta_sql`](features.py), extensão local que aceita `YYYYMMDD` sem tocar na função compartilhada. É estritamente aditiva: só age onde a original falhava, exige 8 dígitos e valida via `strptime`, então `99999999` e `19900230` seguem rejeitados. O diagnóstico mostra `recuperado_compacto`, que é quanto esse formato estava custando.
- Data fora de `[ANO_NASCIMENTO_MIN, ANO_REFERENCIA_CENSO]`, que o NB00b anula junto com a idade.

### Featurização de nomes: SQL, não Python

Normalização (`normalize_text_sql`), limpeza de partículas/placeholders (`clean_name_sql`), split e fonética são expressões SQL do DuckDB geradas por [`features.py`](features.py). A fonética é calculada **uma vez** no nome completo e repartida nas três partes (`nome_meio_phon` incluído). O NB00 monta `*_registros` direto do staging, sem tabela intermediária: pessoa e mãe saem do mesmo passe, apenas com aliases diferentes (`PESSOA_COLUMNS`, `NOME_MAE_COLUMNS`).

A versão anterior trazia a tabela inteira para a memória via `fetch_arrow_table()` antes de distribuir em `ProcessPoolExecutor`. Em SQL o processamento é vetorizado e em streaming, sem teto de RAM.

Duas traduções não são literais, porque o RE2 do DuckDB não tem lookahead nem backreference no padrão:

- `C(?=[EI])` vira `regexp_replace(x, 'C([EI])', 'S\1', 'g')` — o `\1` vale na substituição;
- o dedupe de caracteres repetidos vira `list_reduce` sobre a lista de caracteres.

[`tests/test_featurizacao_sql.py`](tests/test_featurizacao_sql.py) compara SQL e Python coluna a coluna em nomes difíceis. Há **uma divergência conhecida e aceita**: `strip_accents` do DuckDB não decompõe ligaduras tipográficas (`ﬁ`), enquanto o NFKD do Python decompõe. Rode o benchmark com `BENCH_SQL=1 pytest tests/test_featurizacao_sql.py -s`.

## Limpeza (NB00b)

Duas classes de problema, um passe só sobre `registro_unificado`.

**Linha que não pode casar.** CPF com `ano_obito <= ANO_OBITO_CORTE` (hoje 2023) sai da base. Registro sem `nome_completo` (nulo ou em branco) sai nas duas origens (`sem_nome_sql`). O `ano_obito` vem de `CPF_COL_ANO_OBITO` no bronze; o NB00 falha se a coluna não estiver lá. Ano nulo (vivo, e todo o Censo), zero e valores absurdos no futuro ficam.

**Valor-sentinela que o SQL lê como igualdade.** É o problema mais caro dos dois. `l.cep = r.cep` trata `'' = ''` e `'00000000' = '00000000'` como acordo real, então ausência vira par candidato; nas `deterministic_rules` do NB02 vira até match determinístico, contaminando a estimativa do prior. As três colunas afetadas nascem assim: `normalize_date_sql` devolve `''` quando a data não parseia, `cep_norm_sql` faz `lpad(..., 8, '0')` e transforma CEP ausente do CPF em `'00000000'` (o Censo usa `''` para o mesmo caso), e nome que não normaliza vira `''` — inclusive `primeiro_nome` e `ultimo_nome`, que estão na blocking rule principal. Todos viram `NULL`, que não casa com `NULL`.

Data de nascimento inválida é a que não é data real (`2022-02-30` passa pelo `normalize_date_sql` quando já vem em ISO) ou tem ano fora de `[ANO_NASCIMENTO_MIN, ANO_REFERENCIA_CENSO]`. No NB00b a `idade` do CPF é **recalculada** com `idade_cpf_sql` sobre a DOB validada; se a data cai, a idade cai. A do Censo vem de `PECP0401` e não é tocada.

**Categoria residual de sexo.** O `normalize_sexo_sql` mapeia M/F e devolve a inicial de qualquer outra coisa: `'O'` de outro, `'I'` de ignorado, `'9'` de não informado. Para o `ExactMatch('sexo')` do NB02 dois resíduos iguais seriam concordância, e "ambos com sexo desconhecido" não é evidência de serem a mesma pessoa. Só `SEXO_VALIDOS` sobrevive. O NB00b imprime a distribuição completa com uma coluna `mantido` antes de aplicar a regra: se a base tiver uma terceira categoria real e com volume, anulá-la joga sinal fora e vale rever a constante.

O notebook separa **reencodado** (`''` que já era ausência e só mudou de grafia) de **descartado** (valor que existia e foi julgado inválido). O segundo número é o que merece revisão. Há também uma checagem de impacto na coorte: se o filtro de óbito remove ground truth, alguma das duas fontes está errada.

Regras em [`config.py`](config.py) (`obito_antes_do_censo_sql`, `sem_nome_sql`, `dob_valida_sql`, `cep_valido_sql`, `limpeza_columns_sql`), cobertas por [`tests/test_limpeza.py`](tests/test_limpeza.py).

## Saídas

`~/data/probabilistico_output/`:

| Arquivo | Origem |
|---------|--------|
| `probabilistico.duckdb`, `registro_unificado.parquet` | NB00 |
| `registro_limpo.parquet` | NB00b |
| `splink_model.json`, `splink_predictions.parquet`, `splink_clusters.parquet`, `dashboards/cluster_studio.html` | NB02 |
| `models/splink_model.json` | cópia versionada do modelo |
| `metricas_cohort.csv` | NB03 (labels) |
| `metricas_ouro.csv` | NB04 (funil ouro) |

## Ground truth

Somente `cohort_dedup.parquet` — ouro + prata. Listas ouro **não** entram como dado de entrada.

A coorte entra só na validação:

- **NB03 — labels:** amostra de verdade conhecida. `clerical_match_score = 1` = match ouro 1:1 no subset; `= 0` = par distinto conhecido (Censo A × CPF B, blocking). **Positivo/negativo** no texto = decisão no corte 0,95 (aceitou/recusou), não o rótulo. A ouro não é o universo: precision populacional não se mede aqui.
- **NB04 — ouro:** cada Censo A deve receber o CPF X. `recall_ouro` = fração dos A's avaliáveis cujo cluster (0,95) contém X. O funil também reporta quantos Censos do subset foram linkados a algum CPF.
