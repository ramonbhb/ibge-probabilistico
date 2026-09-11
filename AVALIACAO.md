# Avaliação na lista de ouro

Rodada do [`notebooks/03b_avaliar_lista_ouro.ipynb`](notebooks/03b_avaliar_lista_ouro.ipynb) (2026-09-10). Definição das métricas: [`README_validacao_ouro.md`](README_validacao_ouro.md).

## Tabela geral

Há **661.042** pares 1:1 no limpo.

| Corte | N | % da ouro | O que aconteceu |
|---|---:|---:|---|
| `associou_cpf_ouro` | 571.754 | 86,49% | Saiu em `associacoes_unicas` com o CPF da verdade |
| `associou_cpf_errado` | 6.403 | 0,97% | Associou **outro** CPF |
| `melhor_par_mas_cpf_repartilhado` | 13 | ~0% | Tinha `M`, CPF com 4+ Censos |
| `teve_par_abaixo_de_T` | 34.960 | 5,29% | Entrou no predict (`p ≥ 0,5`) e não passou em `T` / veto de mãe |
| `nenhum_par` | 47.912 | 7,25% | Nenhuma linha no predict |

Soma: `571754 + 6403 + 13 + 34960 + 47912 = 661042`.

Quem associou: `571754 + 6403 = 578157`.

- **Recall 86,49%** = `571754 / 661042`
- **FN 13,51%** = os quatro cortes que não são acerto
- **Precisão 98,89%** = `571754 / 578157`
- **FP da associação 1,11%** = `6403 / 578157` — “associei e errei?”

Se o 04 entrega um CPF, na ouro a chance de não ser o da lista é **1,11%**. 

## Onde está o FN (89.288 pessoas)

| Origem | N | % do FN |
|---|---:|---:|
| Blocking não gerou candidato | 47.912 | 54% |
| Candidato existiu, `p` / veto não passou em `T` | 34.960 | 39% |
| Associou o CPF errado | 6.403 | 7% |
| Teto de 3 Censos/CPF | 13 | ~0% |


## Blocking vs atribuição

O par ouro aparece no predict (`p ≥ 0,5`) em **608.333** casos → **recall do par 92,03%**.

O buraco até a associação (86,49%) são **36.579** pessoas que já tinham o par ouro no parquet e mesmo assim não saíram com `A = Y` - quase tudo o corte `T` / veto (34.960).

Complemento do predict: `661042 − 608333 = 52.709` sem o par ouro no parquet.

- 47.912: blocking vazio
- 4.797: o predict trouxe **outro** CPF, não o ouro

Ou seja: ~8% da ouro o blocking não entrega o certo; ~5,3% o score entrega e o `T` segura.

## FN

34.960 = algum candidato ≥ 0,5, não passou em T / veto. O ouro pode nem estar no parquet.
36.579 = o ouro está no parquet e mesmo assim A ≠ Y. Isso inclui quem perdeu o argmax (associou outro) ou caiu no teto, não só quem ficou abaixo de T.


## Quadrantes nome × DOB

Mesmo pacote no par **Censo ouro × CPF ouro**. Nome = fonética; nulo não conta como igual.

| Recorte | n | % da ouro | Certo | Errado | Recall | FP |
|---|---:|---:|---:|---:|---:|---:|
| nome ≠, DOB ≠ | 719 | 0,1% | 133 | 10 | **18,50%** | **6,99%** |
| nome ≠, DOB = | 164.302 | 24,9% | 88.912 | 2.747 | **54,11%** | 3,00% |
| nome =, DOB ≠ | 37.129 | 5,6% | 26.035 | 1.428 | **70,12%** | **5,20%** |
| nome =, DOB = | 458.892 | 69,4% | 456.674 | 2.218 | **99,52%** | **0,48%** |


- Sem nome fonético, o blocking/score acha pouco (54% com DOB igual; 18% se os dois diferem).
- Sem DOB igual, quando associa erra mais (FP 5,2% com nome igual — mais que o dobro do nome diferente com DOB igual). Homônimo com data errada passa mais que nome diferente com data certa.

Em volume, o lastro do recall é o caso fácil: `456674 / 661042 = 69,1` pontos dos 86,5. O grupo grande que puxa para baixo é **nome diferente + DOB igual** (165 mil, 25% da ouro, recall 54%).

## Média dos 4 quadrantes (e o estado)

O FP 1,11% **é** a média dos quatro FPs, com peso = quem associou na ouro (não `n_ouro`):

`FP = Σ_q FP(q) × n_associou(q) / 578157`

| q | n associou | Peso | FP |
|---|---:|---:|---:|
| nome=, DOB= | 458.892 | 79,4% | 0,48% |
| nome≠, DOB= | 91.659 | 15,9% | 3,00% |
| nome=, DOB≠ | 27.463 | 4,8% | 5,20% |
| nome≠, DOB≠ | 143 | 0,02% | 6,99% |

`0,794×0,48 + 0,159×3,00 + 0,048×5,20 + 0,0002×6,99 = 1,11%`.

No estado, a mesma soma com os pesos de `associacoes_unicas` do 04 (Censo × CPF associado). Se a fração fácil for maior que 79%, o FP cai; se o 04 associar mais gente com nome ou DOB diferente, sobe. O 1,11% não se copia: só os quatro FPs. Intervalo binomial da ouro (~0,03 ponto) não é incerteza de transporte.

Ainda é um pouco otimista: a ouro só tem quem tem par verdadeiro 1:1. Quem o 04 associou sem par verdadeiro a ouro não vê.

### Por que só nome × DOB

O pipeline usa mãe, CEP, sexo, UF, idade. Esta média não. Motivo: estrato de transporte precisa mudar o risco, existir no estado sem rótulo, e ter n.

Nome fonético e DOB já abrem 0,48% → 7%. Dá para classificar o par associado no 04 do mesmo jeito. Mãe já filtrou quem entrou em `A` (veto). CEP só desempata e é nulo demais. Sexo/UF o blocking já igualou. Idade repete DOB. Mais cruzamentos: a célula dura tem 10 erros — fatiar é ruído.

Mãe/CEP/sexo continuam no modelo e na atribuição. Só não entram no número que se repondera para o estado.

## Como não ler

- Não é acurácia com TN (o TN seria o estado inteiro).
- Precisão/FP valem **só entre quem associou**.
- Esta ouro ainda pode ser otimista frente ao morador médio; só está menos fácil que a anterior.
- O teto de 3 continua subestimado em relação ao 04 da aplicação.
