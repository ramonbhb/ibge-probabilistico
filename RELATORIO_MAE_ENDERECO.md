# Relatório — atribuição mãe + endereço (modelo + resgate + baixo)

Recorte UF 21. Pipeline: treino/aplicação Splink com mãe e endereço no score
([`02c`](notebooks/02c_treinar_splink_mae_endereco.ipynb) /
[`02d`](notebooks/02d_aplicar_splink_mae_endereco.ipynb)); atribuição com
faixas e regras R1/R2/R3
([`04_atribuir_mae_endereco`](notebooks/04_atribuir_mae_endereco.ipynb));
avaliação ([`05`](notebooks/05_avaliar_mae_endereco.ipynb)), números finais
([`06`](notebooks/06_numeros_finais.ipynb)) e validação na lista de ouro
([`03c`](notebooks/03c_avaliar_lista_ouro_mae_endereco.ipynb)).

O relatório da escada antiga (sem mãe no score) fica em
[`RELATORIO_ATRIBUICAO.md`](RELATORIO_ATRIBUICAO.md) — não misturar.

Universo de aplicação: **6.079.030** Censos (já sem a lista ouro determinística).

---

## Resultado na aplicação (UF 21)

| Versão | Atribuídos | Cobertura aplicação |
|---|---:|---:|
| Escada antiga (mãe só na atribuição) | 4.092.388 | 67,3% |
| Piso simples 0,50 (sem corroborador) | 4.352.929 | 71,6% |
| **Modelo ≥0,90 + R1/R2/R3 + baixo** | **4.304.328** | **70,8%** |

Ganha **~212k** vs escada antiga (−3,5 p.p. a menos de sem CPF).
Perde **~49k** vs piso 0,50 puro: cortou `0,50–0,90` e `0,25–0,50` sem âncora.

No `censo_limpo` (ouro + pareamento + sem CPF):

| Origem | n | % |
|---|---:|---:|
| lista ouro | 510.774 | 7,8% |
| pareamento | 4.304.328 | 65,3% |
| sem CPF | 1.774.702 | 26,9% |

`nos_dois = 0` (ouro e pareamento não se sobrepõem).

---

## De onde veio a atribuição

| Faixa | Regra | n | % dos atribuídos |
|---|---|---:|---:|
| modelo | score | 4.130.020 | 96,0% |
| resgate | R1 | 62.354 | 1,4% |
| resgate | R2 | 20.897 | 0,5% |
| resgate | R3 | 20.040 | 0,5% |
| baixo | R1 | 62.882 | 1,5% |
| baixo | R2 | 8.135 | 0,2% |

Resgate+baixo = **174.308** (4,0%). Quase tudo é modelo alto (`p ≥ 0,90`).
R3 só no resgate (`0,50–0,90`); foi removido do baixo.

1:1 dominante: 4,08M CPF com 1 Censo; 109k com 2; 1,8k com 3
(4.192.135 CPF distintos).

### Qualidade dos atribuídos

| Indicador | % |
|---|---:|
| Data igual | 83,1% |
| \|Δano\| = 0 | 87,3% |
| CEP igual | 65,7% |
| Logradouro igual | 25,2% |
| Mãe preenchida nos dois | 41,6% |
| Mãe igual | 24,1% |

### Quem ficou de fora

| Melhor p | n | % aplicação |
|---|---:|---:|
| ≥ 0,50 | 119.281 | 2,0% |
| 0,25–0,50 | 132.252 | 2,2% |
| 0,05–0,25 | 242.856 | 4,0% |
| sem par | 1.280.313 | 21,1% |

Dos ~119k com `p ≥ 0,50` sem CPF, só **386** são teto — o resto falhou R1/R2/R3.
O buraco grande continua sendo **blocking** (1,28M sem par), não threshold.

---

## Regras da atribuição

| Faixa | Decisão |
|---|---|
| `p ≥ 0,90` | aceita pelo modelo (`score`) |
| `0,50 ≤ p < 0,90` | R1 ou R2 ou R3 |
| `0,25 ≤ p < 0,50` | R1 forte ou R2 (**sem R3**) |
| `p < 0,25` | não resgata |

Teto 3 cumulativo entre faixas. No par elegível: maior `p`, depois desempate
(mãe preenchida / logradouro / CEP).

- **R1** — data exata + primeiro nome compatível + (nome contido ou cobertura de tokens ≥ 0,75; ≥ 0,80 no baixo)
- **R2** — nome completo igual/contido + data plausível (≠ exata): \|Δdias\|≤1, ou mesmo dia/mês com \|Δano\|∈{1,10}
- **R3** — primeiro compatível + cobertura nominal + mãe presente + JW mãe ≥ 0,75; **apenas** em `0,50–0,90`

Diferença em relação à escada antiga: **mãe e endereço entram no score do Splink**,
não só como prova na atribuição. A escada abaixo de 0,90 pede corroborador
explícito (R1/R2/R3) para não repetir o piso 0,50 “solto”.

---

## Validação na lista de ouro

Notebook:
[`03c_avaliar_lista_ouro_mae_endereco.ipynb`](notebooks/03c_avaliar_lista_ouro_mae_endereco.ipynb).

Modelo `SPLINK_MODEL_MAE_ENDERECO`, blocking do 02d, `predict ≥ 0,25`, atribuição
igual ao 04 (modelo + resgate + baixo). Métricas = pacote de associação 1:1
([`README_validacao_ouro.md`](README_validacao_ouro.md)), **não** o PR pairwise do Splink.

Ouro 1:1 no limpo: **G = 661.722**.

### Pacote (pipeline completo)

| Métrica | v1 (escada antiga) | **v2 (mãe+endereço)** |
|---|---:|---:|
| Recall associação | 86,49% | **91,67%** |
| FN | 13,51% | **8,33%** |
| Precisão associação | 98,89% | **99,37%** |
| FP associação (“associei e errei?”) | 1,11% | **0,63%** |
| FP da escolha (antes do teto) | — | **0,63%** |
| Recall do par ouro no predict | 92,03% | **94,18%** |

Na ouro o teto não retirou ninguém (`melhor_par_mas_cpf_repartilhado = 0`);
FP da escolha = FP da associação.

### Cortes (decomposição)

| Corte | n | % da ouro |
|---|---:|---:|
| `associou_cpf_ouro` | 606.585 | 91,67% |
| `associou_cpf_errado` | 3.825 | 0,58% |
| `teve_par_abaixo_de_T` | 14.473 | 2,19% |
| `nenhum_par` | 36.839 | 5,57% |

Associações na ouro: **610.410** (modelo 590.519 + resgate 9.315 + baixo 10.576).

### Quadrantes nome × DOB (par Censo ouro × CPF ouro)

| Recorte | n | Recall | FP associação |
|---|---:|---:|---:|
| nome ≠, DOB = | 152.038 | **73,44%** | 1,12% |
| nome =, DOB ≠ | 38.509 | 67,03% | 1,93% |
| nome =, DOB = | 471.175 | 99,56% | 0,44% |

O ganho grande vs v1 está em **nome diferente + DOB igual** (antes ~54% de recall).
Caso fácil (nome= DOB=) continua ~99,5%.

### O que não usar da ouro

ROC / Precision–Recall do Splink (`labels_clericais`) medem **ranking pairwise**,
não a associação 1:1. Nesta rodada há poucos rivais no predict (~64k negativos
vs 662k positivos); a curva PR sobe de novo no fim quando todos os negativos
já entraram — formato estranho e **esperado**. Os números de operação são os
da tabela do pacote acima.

---

## Leitura final

1. **Cobertura sobe e erro cai** na ouro ao mesmo tempo: recall 86,5% → 91,7%,
   FP 1,11% → 0,63%. Isso é o teste que importa para “se o pipeline entregou um
   CPF, qual a chance de não ser o certo?”.
2. **96% dos atribuídos na aplicação** vêm do modelo (`p ≥ 0,90`); resgate/baixo
   são ~174k com âncora R1/R2/(R3 só no meio).
3. Trade-off vs piso 0,50: −0,8 p.p. de cobertura (~49k) por exigir corroborador
   abaixo de 0,90 — alinhado ao objetivo anti-FP.
4. O que ainda falta na aplicação é sobretudo **blocking** (1,28M sem par), não
   afrouxar o piso do modelo.
5. R3 ficou só no resgate; amostras com nome forte + mãe parecida e data distante
   motivaram tirar R3 do baixo.

**Conclusão:** o pipeline mãe+endereço (modelo ≥ 0,90 + resgate R1/R2/R3 + baixo
R1/R2, teto 3) é a versão a reportar para a UF 21.
