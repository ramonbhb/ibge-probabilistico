# Linkage probabilístico — Censo × CPF

Pipeline interativo (notebooks + DuckDB) para preparar **bases bronze** CPF e Censo (sem empilhar), rodar **Splink link_only** (Censo × CPF) e avaliar contra **ground truth** da coorte (`cohort_dedup`).

Treino e validação são separados: o modelo é treinado sem ver a coorte (`02_treinar`). A aplicação (`02b_aplicar`) carrega o JSON e aplica as 12 regras de predição. Avaliação no [`03_avaliar.ipynb`](notebooks/03_avaliar.ipynb) (pares, melhor nota, recall ouro nas únicas). Lista operacional no [`04_atribuir.ipynb`](notebooks/04_atribuir.ipynb) (só associações 1:1). Corte: **`THRESHOLD_AVALIACAO`** (default 0,99).

## Pré-requisitos

1. Parquets bronze + `cohort_dedup.parquet` (caminho em `COHORT_DEDUP_ARQUIVO`; default `~/capefe/dados/CohortDados/cohort_dedup.parquet`)
2. `pip install -e .` na raiz deste repositório

## Configuração

### Parâmetros de análise — só em [`config.py`](config.py)

Recorte geográfico e limpeza mudam a cada rodada e ficam versionados, no bloco `PARÂMETROS DE ANÁLISE` no topo do arquivo:

```python
FILTRO_UF = None            # ex.: 42 (SC) ou [21, 22]; None = nacional
FILTRO_MUNICIPIO = 2111300  # ex.: 2111300 ou [2111300, 2105302]; None = sem filtro
ANO_OBITO_CORTE = 2023                        # ano_obito <= corte sai (NB00b); 0 = não remove ninguém
DATA_REFERENCIA_IDADE = "2022-08-01"           # idade CPF = anos completos nesta data
ANO_NASCIMENTO_MIN = 1900                     # ano fora de [MIN, 2022] anula a data
SEXO_VALIDOS = ("M", "F")                     # fora daqui o sexo vira NULL
```

Cada eixo aceita **escalar ou lista**. O recorte usual é **só um** (UF *ou* município). Se os dois estiverem preenchidos, a cláusula é AND (como antes).

`ANO_OBITO_CORTE = 0` desliga o filtro de óbito (a regra exige `ano > 0` e `ano <= corte`). Subir o corte (ex. 2030) remove **mais** gente, não desliga.
Corte operacional (`THRESHOLD_AVALIACAO`, default 0,99): avaliação 03 e export 04. Também `export THRESHOLD_AVALIACAO=0.98`.

Não existem `export FILTRO_UF` / `export FILTRO_MUNICIPIO`: filtro é parâmetro de análise, não configuração de ambiente.

Para sobrescrever o filtro só na sessão atual de um notebook, use `config.set_filtros()` — nunca reatribua `FILTRO_UF` / `FILTRO_MUNICIPIO`:

```python
import config
config.set_filtros(uf=[21, 22])                 # mais de um estado → output em .../uf_21_22/
config.set_filtros(municipio=[2111300, 2105302])  # None desliga o eixo
print(config.FILTRO_UF, config.FILTRO_MUNICIPIO, config.OUTPUT_DIR)
```

`from config import FILTRO_UF` copia o valor no momento do import; reatribuir essa cópia deixa o notebook exibindo o filtro novo enquanto as funções de filtro continuam usando o antigo. O mesmo vale para `OUTPUT_DIR`: depois de `set_filtros()`, use `config.OUTPUT_DIR`.

### Caminhos e recursos — variam por máquina

Têm default em `config.py` e aceitam variável de ambiente:

```bash
export OUTPUT_DIR=~/data/probabilistico_output   # base; o recorte vira subdir (uf_41_42_43, nacional, …)
export DUCKDB_THREADS=20           # Splink/DuckDB
export DUCKDB_MEMORY_LIMIT=370GB   # Splink/DuckDB
export THRESHOLD_AVALIACAO=0.99    # avaliação 03, export 04
```

Também aceitam override por ambiente: `CENSO_DIR`, `CENSO_RAW_DIR`, `CENSO_CEP_ARQUIVO` (default `~/singed/bases/raw/censo/data_cep_uniq.csv`), `CENSO_PESSOAS_ARQUIVO`, `CPF_ARQUIVO`, `COHORT_DIR`, `COHORT_DEDUP_ARQUIVO`, `DUCKDB_TEMP_DIR`.

## Notebooks

| Notebook | Função |
|----------|--------|
| [`00_preparar_bases.ipynb`](notebooks/00_preparar_bases.ipynb) | Bronze → filtro UF/município → mãe → CEP → CPF da coorte no Censo → `censo_registros` + `cpf_registros` (sem stack) |
| [`00b_limpar_dados.ipynb`](notebooks/00b_limpar_dados.ipynb) | Limpa cada base → `censo_limpo` / `cpf_limpo`; óbito ≤ corte; sem nome; sentinelas → NULL; re-carimba CPF da coorte |
| [`01_analise_descritiva.ipynb`](notebooks/01_analise_descritiva.ipynb) | EDA visual: missing, top nomes, sexo, DOB, idade, CEP, UF, município |
| [`02_treinar_splink.ipynb`](notebooks/02_treinar_splink.ipynb) | Profile + treino `link_only` (comparisons, prior, EM) → `splink_model.json` |
| [`02b_aplicar_splink.ipynb`](notebooks/02b_aplicar_splink.ipynb) | 12 regras de predição + JSON do 02 → `predict(0,5)` → parquet estreito (sem clustering) |
| [`03_avaliar.ipynb`](notebooks/03_avaliar.ipynb) | Funil do Censo, exemplos ≥ T e faixa, melhor CPF, discordância nome/DOB, ouro em cinco cortes, 1:1 abaixo de T |
| [`04_atribuir.ipynb`](notebooks/04_atribuir.ipynb) | Exporta só associações únicas (`splink_atribuicao.parquet`) |

**Pipeline:** `00` → `00b` → `01` → `02` treinar → `02b` aplicar → `03` avaliar → `04` exportar lista.

Do NB00b em diante o Splink consome `censo_limpo` ∪ `cpf_limpo` via `materialize_splink_input` (view `splink_input`). Sem `registro_unificado` / `registro_limpo` empilhados.

`predict()` no `02b_aplicar` gera pares ≥0,5 e grava parquet estreito (ids + score); **não clusteriza**. Corte `THRESHOLD_AVALIACAO` (default 0,99) entra no 03/04. Se o JSON não existir, o `02b` falha apontando o notebook de treino. O 04 não depende das células do 03.

**1ª passada do modelo (`02_treinar`):** comparisons, prior e EM estão nas células do [`02_treinar_splink.ipynb`](notebooks/02_treinar_splink.ipynb). O [`02b_aplicar_splink.ipynb`](notebooks/02b_aplicar_splink.ipynb) carrega o JSON e aplica as 12 regras de predição (não estão no treino). Sem `nome_mae*` (Censo ~34% preenchido no recorte MA; exact dava peso demais). Nomes no score: `nome_completo_phon`, `primeiro_nome_phon` e `ultimo_nome_phon` (exact + Jaro-Winkler 0,95 e 0,92 + TF em cada um). Meio e o composto `primeiro_ultimo*` ficam nas tabelas; **não** entram no comparison. Primeiro e último também entram no blocking de predição. DOB: uma comparison (`data_nascimento`) com Null custom → Exact ISO + TF → Damerau ≤ 1 → mês e dia iguais → ELSE `m=1e-6` fixo. Partes da data (`ano_nascimento` / `mes_nascimento` / `dia_nascimento`) entram no blocking e no nível mês/dia da comparison; Damerau na string ISO pega transposições `01`↔`10`. Não usamos `DateOfBirthComparison` (diffs de mês/ano em época). Idade: exact e `abs(diff) ≤ 1`; ELSE `m=1e-6` fixo (só pesa quando a idade do Censo não é nula). UF no score (`ExactMatch` + TF). **Sexo não entra na nota.** CEP não entra no score; entra em quatro regras de predição (`ultimo+mes+dia+sexo+cep`, `ultimo+mes+ano+cep`, DOB+CEP, DOB+UF+sexo+CEP) e no EM. **`cpf_norm`:** no CPF vem do bronze; no Censo, da `cohort_dedup` (`PERSON_ID_CENSO` → `CPF_NORM`, `MIN` se ambíguo; NULL fora da coorte). Entra no prior determinístico e num EM; **não** entra no blocking de predição nem no score — senão a GT sempre seria candidata e o 03 circularia. `NULL = NULL` é falso. Mãe fica para uma 2ª passada. Depois do treino, o `02` grava `splink_model.json` em `OUTPUT_DIR` e uma cópia em [`models/splink_model.json`](models/splink_model.json). JSON antigo com `bayes_factor_column_prefix` (`bf_`) é do contrato anterior — retreinar no `02_treinar`. Depois desta mudança de comparação/blocking, **retreinar**: m/u mudam e o JSON em `models/` continua inválido até esse treino.

**REBUILD:** no NB00, `REBUILD=False` reutiliza `probabilistico.duckdb` sem refazer. **`REFILTER_GEO=True`** reusa o bronze, refaz o filtro UF/município **e reconstrói** `censo_registros` / `cpf_registros` (o 00b não lê `*_filtrado`).

**Blocking Splink:** três listas distintas — predição (12 regras OR, recall) no [`02b_aplicar_splink.ipynb`](notebooks/02b_aplicar_splink.ipynb); prior (`nome_completo+DOB` e `cpf_norm`) e EM (quatro blocos apertados para `m`) no [`02_treinar_splink.ipynb`](notebooks/02_treinar_splink.ipynb). Não unificar. Fonte das 12 regras: célula `blocking_rules` do 02b. `cpf_norm` e `nome_meio` **não** entram na predição. Partes da data vêm da view `splink_input` (`ano_nascimento` / `mes_nascimento` / `dia_nascimento`, `substr` da ISO). Sexo em `ultimo+mes+dia+sexo+cep` e `DOB+UF+sexo+cep`. CEP em quatro regras (não só DOB+CEP).

- `nome_completo_phon`
- `primeiro_nome_phon` + `ultimo_nome_phon` + `ano_nascimento`
- `primeiro_nome_phon` + `ultimo_nome_phon` + `mes_nascimento` + `dia_nascimento`
- `primeiro_nome_phon` + `ultimo_nome_phon` + `mes_nascimento` + `ano_nascimento`
- `primeiro_nome_phon` + `data_nascimento`
- `ultimo_nome_phon` + `data_nascimento`
- `primeiro_nome_phon` + `mes_nascimento` + `dia_nascimento`
- `primeiro_nome_phon` + `mes_nascimento` + `ano_nascimento`
- `ultimo_nome_phon` + `mes_nascimento` + `dia_nascimento` + `sexo` + `cep`
- `ultimo_nome_phon` + `mes_nascimento` + `ano_nascimento` + `cep`
- `data_nascimento` + `cep`
- `data_nascimento` + `uf` + `sexo` + `cep`

Profile e gráfico cumulativo de pares candidatos rodam **antes** do treino. O `Linker` usa duas views (`splink_censo` / `splink_cpf`) com `link_type='link_only'`.

**Splink:** pin [`splink==5.0.0.dev1`](https://pypi.org/project/splink/5.0.0.dev1/). O `Linker` ainda recebe `db_api=` (contrato desta versão). Saídas de comparação usam prefixo `mw_` (match weight) em vez de `bf_`. `predict()` aceita `num_chunks_left` / `num_chunks_right` para volume grande.

Referências: [`notebooks/_exemplo/`](notebooks/_exemplo/) (Splink + inferência mãe didática).

## Variáveis unificadas

- Nome: completo, primeiro/meio/último (partículas `DA`, `DOS`, etc. e placeholders `DESCONHECIDO`, `MAE` removidos por [`clean_name_sql`](features.py); vazio → `NULL`). `primeiro_ultimo` e `primeiro_ultimo_phon` nascem no NB00 (`CONCAT_WS` das pontas); não entram no score.
- **`nome_mae`:** CPF direto (`NOM_MAE`); Censo **inferido** por domicílio ([`inferir_pais.py`](inferir_pais.py)). Sofre o mesmo split da pessoa: `primeiro_nome_mae`, `nome_meio_mae`, `ultimo_nome_mae`, com as fonéticas correspondentes. Vazio vira `NULL` (`NULLIF`), para o Splink não casar `'' = ''`
- **`cpf_norm`:** no CPF, `COD_CPF` normalizado (11 díg.). No Censo, join com `cohort_dedup` (`PERSON_ID_CENSO` → `CPF_NORM`; `MIN` se ambíguo; NULL fora da coorte). Coluna estrutural. Treino: prior + EM. Não entra no score nem nas 12 regras de predição.
- **CEP Censo:** join `data_cep_uniq.csv` por `B0000` + quadra/face ([`materialize_censo_cep_lookup`](config.py))
- Sexo, DOB, **idade**, CEP, **UF**, **`cod_municipio`** (IBGE 7 díg.)
- **`ano_obito`:** só CPF, `NULL` no Censo. Não entra em comparação — existe para o filtro do NB00b e para auditoria
- **`idade`:** Censo via `PECP0401` só quando a data validada é nula (se há DOB, o NB00b zera a idade para o Splink não duplicar a comparison); CPF = anos completos em `DATA_REFERENCIA_IDADE` ([`idade_censo_sql`](config.py), [`idade_cpf_sql`](config.py)). Ver abaixo
- Fonética: `*_phon` (substituições PT-BR; `Ç`→`S` / `Ñ`→`NH` antes do ASCII; `TH`/`RH`). Comparação experimental em [`fonetica_luis.py`](fonetica_luis.py) / [`notebooks/compare_fonetica.ipynb`](notebooks/compare_fonetica.ipynb).

### Idade

No Censo a idade vem de **`PECP0401`** (variável auxiliar calculada, 0–140 anos, universo) no NB00. No NB00b, se a data validada não é nula, a idade do Censo vira `NULL` — a comparison de idade no Splink cai no NullLevel e não duplica a DOB. Sem data, `PECP0401` permanece. No CPF a idade é derivada de `data_nascimento` como anos completos em **`DATA_REFERENCIA_IDADE`** (`2022-08-01`), via `age()` no DuckDB — não é só `2022 - ano`. No Splink a comparação usa exact e `abs(idade_l - idade_r) ≤ 1` (não colunas `idade±1`); o ELSE é `m=1e-6` fixo, igual ao da data — a idade só entra no score quando o Censo não tem DOB (senão é NullLevel). As colunas do questionário (`PECP0003`/`PECP0030`) ficam só como contexto no diagnóstico do NB00.

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

Data de nascimento inválida é a que não é data real (`2022-02-30` passa pelo `normalize_date_sql` quando já vem em ISO) ou tem ano fora de `[ANO_NASCIMENTO_MIN, ANO_REFERENCIA_CENSO]`. No NB00b a `idade` do CPF é **recalculada** com `idade_cpf_sql` sobre a DOB validada; se a data cai, a idade cai. A do Censo fica `NULL` quando a data validada existe (senão permanece `PECP0401`).

**Categoria residual de sexo.** O `normalize_sexo_sql` mapeia M/F e devolve a inicial de qualquer outra coisa: `'O'` de outro, `'I'` de ignorado, `'9'` de não informado. Sexo não entra na nota, mas a regra de blocking `data_nascimento` + `uf` + `sexo` + `cep` ainda exige igualdade. Dois resíduos iguais (`'O'='O'`) virariam candidato sem serem a mesma pessoa. Só `SEXO_VALIDOS` sobrevive. O NB00b imprime a distribuição completa com uma coluna `mantido` antes de aplicar a regra: se a base tiver uma terceira categoria real e com volume, anulá-la joga sinal fora e vale rever a constante.

O notebook separa **reencodado** (`''` que já era ausência e só mudou de grafia) de **descartado** (valor que existia e foi julgado inválido). O segundo número é o que merece revisão. Há também uma checagem de impacto na coorte (CPF e `PERSON_ID_CENSO`): se o filtro de óbito ou de nome remove ground truth, alguma das duas fontes está errada.

Regras em [`config.py`](config.py) (`obito_antes_do_censo_sql`, `sem_nome_sql`, `dob_valida_sql`, `cep_valido_sql`, `limpeza_columns_sql`), cobertas por [`tests/test_limpeza.py`](tests/test_limpeza.py).

## Saídas

`~/data/probabilistico_output/<recorte>/`, com `<recorte>` = slug do filtro (`uf_41_42_43`, `mun_2111300`, `nacional`). DuckDB, parquets, JSON e métricas ficam nesse subdiretório — rodadas de UFs diferentes não se sobrescrevem. A cópia versionada `models/splink_model.json` no repo é única (não é por recorte).

| Arquivo | Origem |
|---------|--------|
| `probabilistico.duckdb`, `censo_registros.parquet`, `cpf_registros.parquet` | NB00 |
| `censo_limpo.parquet`, `cpf_limpo.parquet` | NB00b |
| `splink_model.json` | `02_treinar` |
| `splink_predictions.parquet` | `02b_aplicar` |
| `models/splink_model.json` | cópia versionada do modelo (atualizar após retreino no `02_treinar`) |
| `splink_atribuicao.parquet` | `04_atribuir` (associações únicas, melhor nota) |

## Ground truth

`cohort_dedup.parquet` é **toda confiável**. Avaliação (03) usa pares **estruturalmente 1:1** (1 CPF por Censo e 1 Censo por CPF). N:1 / 1:N saem em `n_nao_1a1_descartada` — não há filtro por rótulo “ouro vs prata” do arquivo.

A coorte também **carimba** `cpf_norm` no Censo (NB00/00b) para o treino (prior/EM). O score e o blocking de predição **não** vêem o CPF, então o recall da GT no 03 não é circular.

- **03:** exemplos ≥ T e na faixa; melhor CPF por Censo; funil do Censo limpo (no parquet / `p ≥ T` / CPF único); discordância nome/DOB no melhor CPF; ouro em cinco cortes (encontrada, única errada, compartilhada, abaixo de T, fora do parquet); 1:1 com `p < T`.
- **04:** exporta só as associações únicas (mesmo SQL do 03).
