# Atribuição depois do pareamento

Trecho para o relatório. A regra está no [`notebooks/04_atribuir.ipynb`](notebooks/04_atribuir.ipynb). Números abaixo: UF 21, Censo de aplicação.

O pareamento só dá uma nota. A atribuição é o que decide se aquela pessoa do Censo fica com aquele CPF.

Cada candidato é um par: uma pessoa do Censo e um CPF, com uma nota de 0 a 1. A nota diz o quanto o nome, a data e a idade puxam para ser a mesma pessoa. O nome da mãe **não entra na nota** do modelo; entra depois, na atribuição. Nota alta não entrega o CPF sozinha, salvo no topo. A partir daí as fichas são revistas de cima para baixo.

## Resultado (UF 21)

| Série | Pessoas | % do Censo limpo |
|---|---:|---:|
| Lista ouro (determinístico) | 510.774 | 7,8% |
| Pareamento (escada) | 4.079.358 | 61,9% |
| Sem CPF | 1.999.672 | 30,3% |

No recorte de aplicação (já sem a lista ouro), a escada atribui **67,1%** (4.079.358 de 6.079.030). Quase sete em cada dez fichas do topo saem só pela nota ≥ 0,99 (`score`).

## Como a ficha entra na fila

Antes de qualquer ficha entrar:

- A nota é pelo menos **0,05**.
- Os dois lados têm primeiro nome, e eles são iguais ou diferem em no máximo uma letra. De 0,95 até 0,99 essa exigência não vale. De 0,99 para cima ela volta.
- Se os dois lados têm nome da mãe e esses nomes não passam nas regras abaixo, a ficha sai — salvo nome completo e data de nascimento iguais. De 0,95 até 0,99 o veto de mãe não vale; de 0,99 para cima ele volta, mas o primeiro nome continua valendo.

**Quando a mãe “passa”**

- Nome igual, começo em comum com pelo menos duas palavras, ou Jaro-Winkler ≥ 0,75 — este último só sozinho a partir de **0,50**.
- Mãe contida no outro nome (pelo menos duas palavras, sem ser só o prefixo), a partir de **0,50**.
- Uma palavra só da mãe dentro do outro nome, a partir de **0,90**.
- Uma das datas nula, nota ≥ **0,35**, e mãe com Jaro-Winkler ≥ 0,75 ou contida.
- Nota entre **0,05 e 0,50**, data nula **ou** datas diferentes com diferença de **ano de nascimento** de no máximo **10 anos**, e ainda: (Jaro-Winkler ≥ 0,75 e primeiro nome da mãe **fora** dos 10 mais comuns) **ou** mãe contida com pelo menos **3 tokens** (aí o top 10 não bloqueia).

Quem sobrou desce uma escada. Cada degrau é uma fatia de 0,025 na nota, do mais certo para o menos certo. Em todo degrau, a pessoa do Censo ainda não pode ter CPF, e o CPF não pode já ter 3 pessoas do Censo. Se neste degrau o CPF passaria de 3, o grupo inteiro desse degrau fica de fora.

**Nota 0,99 ou mais.** A nota basta. Não se pede outra prova, e não se exige que seja o único candidato. Se a mesma pessoa tiver mais de um CPF nessa faixa, fica o de nota mais alta. Empate na nota desempata por CEP igual e nome da mãe igual.

**De 0,975 até 0,80.** A nota pede uma prova extra. Se a mesma pessoa tiver mais de um CPF nessa faixa, fica o de nota mais alta. Um CPF leva até 3. Vale a primeira prova que aparecer, nesta ordem:

1. Nome da mãe passa (regras acima).
2. Nome da rua e município combinam.
3. Data de nascimento igual e o começo do nome completo combina.
4. Data de nascimento igual, último nome igual e primeiro nome parecido (nome com pelo menos 6 letras e diferença pequena em relação ao tamanho).
5. Data igual ou com um pedaço só diferente (dia, mês, ano com um de diferença, ou um caractere), e no máximo uma palavra do nome diferente. Espaço e corte contam. Primeiro nome entre os 10 mais comuns não usa esta prova. Em nome de três palavras, a do meio trocada não entra.
6. Nome completo igual e CEP igual, e o primeiro nome não está entre os 10 mais comuns do Censo.
7. Pelo menos 80% das palavras do nome em comum e CEP igual, com a mesma restrição do primeiro nome comum.

**De 0,775 até 0,05.** A mesma prova extra, e mais uma trava: dentro daquela fatia de nota, a pessoa do Censo só pode ter um CPF candidato e esse CPF só pode ter uma pessoa do Censo. Se houver dois candidatos na mesma fatia, nenhum dos dois entra naquele degrau — salvo quando a trava abre:

- Jaro-Winkler da mãe > 0,90 e nota ≥ 0,50;
- mãe contida e datas iguais, nota ≥ 0,50;
- ramo de data nula (≥ 0,35) ou de baixa nota (0,05–0,50) descritos acima.

Uma pessoa recebe um CPF só. Um CPF recebe no máximo três pessoas do Censo. A ficha aceita guarda o degrau e o motivo: `score` no topo, ou o nome da prova que liberou (`mae`, `logradouro`, `data_prefixo`, `data_primeiro`, `data_uma_palavra`, `nome_cep`, `tokens_cep`).

## O que a escada não consegue pegar no limite de cima

O grosso de quem fica sem CPF **não** está na nota alta: cerca de **1,65 milhão** (82% dos sem CPF) tem melhor par abaixo de 0,25 ou nem chega a virar candidato no blocking. Aí o problema é recall do pareamento, não da atribuição.

O teto que a atribuição ainda encontra, com nota já razoável, é outro. Entre os sem CPF com melhor par **≥ 0,75** (~204 mil, 10% dos sem CPF / 3,4% da aplicação), quase tudo cai em três caixas:

| Motivo | N | O que é |
|---|---:|---|
| Sem corroborador | ~174 mil | Nota boa, primeiro nome e mãe passam (ou mãe vazia), mas **nenhuma prova extra** fecha: sem mãe útil, sem rua+município, sem data+nome alinhados, sem CEP com nome raro. |
| Veto de mãe ou primeiro nome | ~27 mil | Primeiro nome longe demais, ou mães preenchidas que não passam nas regras (Jaro-Winkler baixo, mãe comum na baixa nota, idade afastada demais, etc.). |
| Outro na escada | ~3 mil | Em geral a trava de candidato único: dois CPFs (ou duas pessoas) na mesma fatia, sem a exceção que libera. |

É esse o **limite superior da atribuição**: com a nota que o modelo já deu, não há mais sinal barato para decidir com segurança. Afrouxar a prova extra ou a trava de único candidato nessa faixa aumenta cobertura, mas troca o tipo de erro — passa a aceitar homônimos e fichas sem âncora. Por isso a escada para aí e deixa esses casos para outra fonte (lista ouro, revisão, ou um modelo que use a mãe na nota).

Abaixo de 0,75 ainda sobram faixas intermediárias (~147 mil entre 0,25 e 0,75). Parte foi recuperada com mãe e data nula / baixa nota; o restante esbarra no mesmo teto (prova fraca, mãe frequente, vários candidatos) ou em nota baixa demais para as regras atuais.
