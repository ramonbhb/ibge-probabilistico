# Linkage probabilístico — Censo × CPF

Pipeline interativo (notebooks + DuckDB) para preparar **bases bronze** CPF e Censo (sem empilhar), rodar **Splink link_only** (Censo × CPF) e avaliar contra **ground truth** da coorte (`cohort_dedup`).

Treino e validação são separados: o modelo é treinado sem ver a coorte (`02_treinar`). A aplicação (`02b_aplicar`) só carrega o JSON. Avaliação no [`03_avaliar.ipynb`](notebooks/03_avaliar.ipynb): score no par e recall no cluster. Lista operacional (1 CPF por Censo) no [`04_atribuir.ipynb`](notebooks/04_atribuir.ipynb). Corte: **`THRESHOLD_AVALIACAO`** (default 0,95).

## Pré-requisitos

1. Parquets bronze + `cohort_dedup.parquet` (caminho em `COHORT_DEDUP_ARQUIVO`; default `~/capefe/dados/CohortDados/cohort_dedup.parquet`)
2. `pip install -e .` na raiz deste repositório

## Configuração

### Parâmetros de análise — só em [`config.py`](config.py)

Recorte geográfico e limpeza mudam a cada rodada e ficam versionados, no bloco `PARÂMETROS DE ANÁLISE` no topo do arquivo:

```python
FILTRO_UF: str | int | None = None            # ex.: 42 (SC); None = nacional
FILTRO_MUNICIPIO: str | int | None = 2111300  # IBGE 7 díg.; None = sem filtro
ANO_OBITO_CORTE = 2023                        # ano_obito <= corte sai (NB00b); 0 = não remove ninguém
DATA_REFERENCIA_IDADE = "2022-08-01"           # idade CPF = anos completos nesta data
ANO_NASCIMENTO_MIN = 1900                     # ano fora de [MIN, 2022] anula a data
SEXO_VALIDOS = ("M", "F")                     # fora daqui o sexo vira NULL
```

`ANO_OBITO_CORTE = 0` desliga o filtro de óbito (a regra exige `ano > 0` e `ano <= corte`). Subir o corte (ex. 2030) remove **mais** gente, não desliga.
Corte de clustering/métricas: `THRESHOLD_AVALIACAO` (default `0.95`), também sobrescreve por `export THRESHOLD_AVALIACAO=0.98`.

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
export DUCKDB_MEMORY_LIMIT=370GB   # Splink/DuckDB
export THRESHOLD_AVALIACAO=0.99    # clustering 02b, métricas 03, atribuição 04
```

Também aceitam override por ambiente: `CENSO_DIR`, `CENSO_RAW_DIR`, `CENSO_CEP_ARQUIVO` (default `~/singed/bases/raw/censo/data_cep_uniq.csv`), `CENSO_PESSOAS_ARQUIVO`, `CPF_ARQUIVO`, `COHORT_DIR`, `COHORT_DEDUP_ARQUIVO`, `DUCKDB_TEMP_DIR`.

## Notebooks

| Notebook | Função |
|----------|--------|
| [`00_preparar_bases.ipynb`](notebooks/00_preparar_bases.ipynb) | Bronze → filtro UF/município → mãe → CEP → CPF da coorte no Censo → `censo_registros` + `cpf_registros` (sem stack) |
| [`00b_limpar_dados.ipynb`](notebooks/00b_limpar_dados.ipynb) | Limpa cada base → `censo_limpo` / `cpf_limpo`; óbito ≤ corte; sem nome; sentinelas → NULL; re-carimba CPF da coorte |
| [`01_analise_descritiva.ipynb`](notebooks/01_analise_descritiva.ipynb) | EDA visual: missing, top nomes, sexo, DOB, idade, CEP, UF, município |
| [`02_treinar_splink.ipynb`](notebooks/02_treinar_splink.ipynb) | Profile + blocking + treino `link_only` (1ª passada sem mãe) → `splink_model.json` |
| [`02b_aplicar_splink.ipynb`](notebooks/02b_aplicar_splink.ipynb) | Carrega o JSON (não retreina) → `predict(0,5)` + cluster `THRESHOLD_AVALIACAO` |
| [`03_avaliar.ipynb`](notebooks/03_avaliar.ipynb) | Score no par (`recall_par_ouro`, `fp_amostra`), erros, sweep de threshold e recall no cluster (`recall_cluster_ouro`) |
| [`04_atribuir.ipynb`](notebooks/04_atribuir.ipynb) | Lista 1 CPF por Censo (greedy, fora de mega-cluster) e `recall_atribuicao` vs ouro |

**Pipeline:** `00` → `00b` → `01` → `02` treinar → `02b` aplicar → `03` avaliar → `04` atribuir.

Do NB00b em diante o Splink consome `censo_limpo` ∪ `cpf_limpo` via `materialize_splink_input` (view `splink_input`). Sem `registro_unificado` / `registro_limpo` empilhados.

`predict()` no `02b_aplicar` gera pares ≥0,5 (opcionalmente com
`PREDICT_NUM_CHUNKS_LEFT` / `PREDICT_NUM_CHUNKS_RIGHT`); export via
`SplinkDataFrame.to_parquet` (sem materializar tudo em pandas). **Clustering,
métricas e atribuição usam `THRESHOLD_AVALIACAO`** (default 0,95). Se o JSON não existir, o `02b` falha apontando o notebook de treino — não retreina sozinho. O JSON só é recarregado no 03 para o diagnóstico opcional (curva/waterfall). O 04 não depende das células do 03; gera `splink_atribuicao.parquet`.

**1ª passada do modelo (`02_treinar`):** comparisons e settings em
[`splink_spec.py`](splink_spec.py) (`build_comparisons` / `build_settings`); o
notebook orquestra profile, EM e gravação do JSON. Sem `nome_mae*` (Censo ~34% preenchido no recorte MA; exact dava peso demais). Nomes fonéticos: exact + Jaro-Winkler 0,95 e 0,92. DOB: `data_nascimento` e partes (`ano_nascimento` / `mes_nascimento` / `dia_nascimento`) com Null → Exact → Damerau-Levenshtein ≤ 1 → Else. TF só na data completa e no ano (mês tem 12 valores, dia 31). Data completa exact implica ano+mês+dia exact — o EM ainda estima, mas os pesos se sobrepõem um pouco, como nome completo + partes. Não usamos `DateOfBirthComparison` (diffs de mês/ano em época). Idade: exact e `abs(diff) ≤ 1`. UF no score (`ExactMatch` + TF). **Sexo não entra na nota.** CEP não entra no score; entra numa regra de predição sem nome (DOB+CEP) e no EM. **`cpf_norm`:** no CPF vem do bronze; no Censo, da `cohort_dedup` (`PERSON_ID_CENSO` → `CPF_NORM`, `MIN` se ambíguo; NULL fora da coorte). Entra no prior determinístico e num EM; **não** entra no blocking de predição nem no score — senão a GT sempre seria candidata e o 03 circularia. `NULL = NULL` é falso. Mãe fica para uma 2ª passada. Depois do treino, o `02` grava `splink_model.json` em `OUTPUT_DIR` e uma cópia em [`models/splink_model.json`](models/splink_model.json). JSON antigo com `bayes_factor_column_prefix` (`bf_`) é do contrato anterior — retreinar no `02_treinar`. Depois desta mudança de comparação/blocking, **retreinar**: m/u mudam e o JSON em `models/` continua inválido até esse treino.

**REBUILD:** no NB00, `REBUILD=False` reutiliza `probabilistico.duckdb` sem refazer. **`REFILTER_GEO=True`** refaz só filtro UF/município.

**Blocking Splink:** doze regras OR em [`splink_spec.py`](splink_spec.py) (`02_treinar` e pares distintos do `03_avaliar` importam as mesmas; o `02b` aplica as regras gravadas no JSON). `cpf_norm` **não** está nessa lista (só prior/EM no 02). Partes da data vêm da view `splink_input` (`ano_nascimento` / `mes_nascimento` / `dia_nascimento`, `substr` da ISO) e entram no blocking **e** no score (Damerau nas partes pega transposições `01`↔`10` que na string ISO inteira podem passar de distância 1). Sexo só na regra sem nome DOB+UF. CEP só na regra sem nome DOB+CEP.

- `nome_completo_phon`
- `primeiro_nome_phon` + `ultimo_nome_phon` + `ano_nascimento`
- `primeiro_nome_phon` + `ultimo_nome_phon` + `mes_nascimento` + `dia_nascimento`
- `primeiro_nome_phon` + `ultimo_nome_phon` + `mes_nascimento` + `ano_nascimento`
- `primeiro_nome_phon` + `data_nascimento`
- `ultimo_nome_phon` + `data_nascimento`
- `primeiro_nome_phon` + `mes_nascimento` + `dia_nascimento`
- `primeiro_nome_phon` + `mes_nascimento` + `ano_nascimento`
- `ultimo_nome_phon` + `mes_nascimento` + `dia_nascimento`
- `ultimo_nome_phon` + `mes_nascimento` + `ano_nascimento`
- `data_nascimento` + `cep`
- `data_nascimento` + `uf` + `sexo`

Profile e gráfico cumulativo de pares candidatos rodam **antes** do treino. O `Linker` usa duas views (`splink_censo` / `splink_cpf`) com `link_type='link_only'`.

**Splink:** pin [`splink==5.0.0.dev1`](https://pypi.org/project/splink/5.0.0.dev1/). O `Linker` ainda recebe `db_api=` (contrato desta versão). Saídas de comparação usam prefixo `mw_` (match weight) em vez de `bf_`. `predict()` aceita `num_chunks_left` / `num_chunks_right` para volume grande.

Referências: [`notebooks/_exemplo/`](notebooks/_exemplo/) (Splink + inferência mãe didática).

## Variáveis unificadas

- Nome: completo, primeiro/meio/último (partículas `DA`, `DOS`, etc. e placeholders `DESCONHECIDO`, `MAE` removidos por [`clean_name_sql`](features.py); vazio → `NULL`)
- **`nome_mae`:** CPF direto (`NOM_MAE`); Censo **inferido** por domicílio ([`inferir_pais.py`](inferir_pais.py)). Sofre o mesmo split da pessoa: `primeiro_nome_mae`, `nome_meio_mae`, `ultimo_nome_mae`, com as fonéticas correspondentes. Vazio vira `NULL` (`NULLIF`), para o Splink não casar `'' = ''`
- **`cpf_norm`:** no CPF, `COD_CPF` normalizado (11 díg.). No Censo, join com `cohort_dedup` (`PERSON_ID_CENSO` → `CPF_NORM`; `MIN` se ambíguo; NULL fora da coorte). Coluna estrutural. Treino: prior + EM. Não entra no score nem nas 12 regras de predição.
- **CEP Censo:** join `data_cep_uniq.csv` por `B0000` + quadra/face ([`materialize_censo_cep_lookup`](config.py))
- Sexo, DOB, **idade**, CEP, **UF**, **`cod_municipio`** (IBGE 7 díg.)
- **`ano_obito`:** só CPF, `NULL` no Censo. Não entra em comparação — existe para o filtro do NB00b e para auditoria
- **`idade`:** Censo via `PECP0401`; CPF = anos completos em `DATA_REFERENCIA_IDADE` ([`idade_censo_sql`](config.py), [`idade_cpf_sql`](config.py)). Ver abaixo
- Fonética: `*_phon` (substituições PT-BR; `Ç`→`S` / `Ñ`→`NH` antes do ASCII; `TH`/`RH`). Comparação experimental em [`fonetica_luis.py`](fonetica_luis.py) / [`notebooks/compare_fonetica.ipynb`](notebooks/compare_fonetica.ipynb).

### Idade

No Censo a idade vem de **`PECP0401`** (variável auxiliar calculada, 0–140 anos, universo). No CPF é derivada de `data_nascimento` como anos completos em **`DATA_REFERENCIA_IDADE`** (`2022-08-01`), via `age()` no DuckDB — não é só `2022 - ano`. No Splink a comparação usa exact e `abs(idade_l - idade_r) ≤ 1` (não colunas `idade±1`). As colunas do questionário (`PECP0003`/`PECP0030`) ficam só como contexto no diagnóstico do NB00.

Se a idade vier muito nula, a célula **3b do NB00** aponta a causa: nulos de `PECP0401`, e no CPF os valores crus mais frequentes. Dois casos conhecidos que zeram a idade do CPF inteiro:

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

Duas classes de problema, um passe sobre **cada** base (`censo_registros` / `cpf_registros`).

**Linha que não pode casar.** CPF com `ano_obito <= ANO_OBITO_CORTE` (hoje 2023) sai da base. `ANO_OBITO_CORTE = 0` desliga o filtro. Registro sem `nome_completo` (nulo ou em branco) sai nas duas origens (`sem_nome_sql`). O `ano_obito` vem de `CPF_COL_ANO_OBITO` no bronze; o NB00 falha se a coluna não estiver lá. Ano nulo (vivo, e todo o Censo), zero e valores absurdos no futuro ficam.

**Valor-sentinela que o SQL lê como igualdade.** É o problema mais caro dos dois. `l.cep = r.cep` trata `'' = ''` e `'00000000' = '00000000'` como acordo real, então ausência vira par candidato; nas `deterministic_rules` do `02_treinar` vira até match determinístico, contaminando a estimativa do prior. As três colunas afetadas nascem assim: `normalize_date_sql` devolve `''` quando a data não parseia, `cep_norm_sql` faz `lpad(..., 8, '0')` e transforma CEP ausente do CPF em `'00000000'` (o Censo usa `''` para o mesmo caso), e nome que não normaliza vira `''` — inclusive `primeiro_nome` e `ultimo_nome`. Todos viram `NULL`, que não casa com `NULL`.

Data de nascimento inválida é a que não é data real (`2022-02-30` passa pelo `normalize_date_sql` quando já vem em ISO) ou tem ano fora de `[ANO_NASCIMENTO_MIN, ANO_REFERENCIA_CENSO]`. No NB00b a `idade` do CPF é **recalculada** com `idade_cpf_sql` sobre a DOB validada; se a data cai, a idade cai. A do Censo vem de `PECP0401` e não é tocada.

**Categoria residual de sexo.** O `normalize_sexo_sql` mapeia M/F e devolve a inicial de qualquer outra coisa: `'O'` de outro, `'I'` de ignorado, `'9'` de não informado. Sexo não entra na nota, mas a regra de blocking `data_nascimento` + `uf` + `sexo` ainda exige igualdade. Dois resíduos iguais (`'O'='O'`) virariam candidato sem serem a mesma pessoa. Só `SEXO_VALIDOS` sobrevive. O NB00b imprime a distribuição completa com uma coluna `mantido` antes de aplicar a regra: se a base tiver uma terceira categoria real e com volume, anulá-la joga sinal fora e vale rever a constante.

O notebook separa **reencodado** (`''` que já era ausência e só mudou de grafia) de **descartado** (valor que existia e foi julgado inválido). O segundo número é o que merece revisão. Há também uma checagem de impacto na coorte (CPF e `PERSON_ID_CENSO`): se o filtro de óbito ou de nome remove ground truth, alguma das duas fontes está errada.

Regras em [`config.py`](config.py) (`obito_antes_do_censo_sql`, `sem_nome_sql`, `dob_valida_sql`, `cep_valido_sql`, `limpeza_columns_sql`), cobertas por [`tests/test_limpeza.py`](tests/test_limpeza.py).

## Saídas

`~/data/probabilistico_output/`:

| Arquivo | Origem |
|---------|--------|
| `probabilistico.duckdb`, `censo_registros.parquet`, `cpf_registros.parquet` | NB00 |
| `censo_limpo.parquet`, `cpf_limpo.parquet` | NB00b |
| `splink_model.json` | `02_treinar` |
| `splink_predictions.parquet`, `splink_clusters.parquet`, `dashboards/cluster_studio.html` | `02b_aplicar` |
| `models/splink_model.json` | cópia versionada do modelo (atualizar após retreino no `02_treinar`) |
| `metricas_avaliacao.csv` | `03_avaliar` (pares + clusters, um corte) |
| `metricas_sweep.csv` | `03_avaliar` (recall/fp/`n_censo_com_par` no grid de threshold) |
| `splink_atribuicao.parquet`, `metricas_atribuicao.csv` | `04_atribuir` (1 CPF por Censo) |

## Ground truth

`cohort_dedup.parquet` é **toda confiável**. Avaliação (03/04) usa pares **estruturalmente 1:1** (1 CPF por Censo e 1 Censo por CPF). N:1 / 1:N saem em `n_nao_1a1_descartada` — não há filtro por rótulo “ouro vs prata” do arquivo.

A coorte também **carimba** `cpf_norm` no Censo (NB00/00b) para o treino (prior/EM). O score e o blocking de predição **não** vêem o CPF, então o recall da GT no 03 não é circular.

- **Seção A — pares:** `cobertura_blocking` = fração da GT 1:1 do subset que colide em ≥1 regra; `recall_par_ouro` = GT com par pontuado ≥ `THRESHOLD_AVALIACAO`; `fp_amostra` = fração da amostra de pares distintos conhecidos (cap 5/âncora) com score ≥ threshold — não é precision populacional. O 03 lista amostras de miss de blocking, FN de score e FP da amostra, e grava um sweep SQL (`metricas_sweep.csv`).
- **Seção B — clusters:** cada Censo A deve receber o CPF X. `recall_cluster_ouro` = fração dos A's avaliáveis cujo cluster contém X. O funil também reporta quantos Censos do subset foram linkados a algum CPF; a quebra por tipo (`outros`) mostra inflação por mega-cluster.
- **04 — atribuição:** cada Censo recebe no máximo um CPF (greedy por score, cluster `<> outros`). `recall_atribuicao` = fração da GT 1:1 cujo CPF atribuído é o X.
