# Atribuição depois do pareamento

Trecho para o relatório. A regra está no [`notebooks/04_atribuir.ipynb`](notebooks/04_atribuir.ipynb).

O pareamento só dá uma nota. A atribuição é o que decide se aquela pessoa do Censo fica com aquele CPF.

Cada candidato é um par: uma pessoa do Censo e um CPF, com uma nota de 0 a 1. A nota diz o quanto o nome, a data e a idade puxam para ser a mesma pessoa. Nota alta não entrega o CPF sozinha, salvo no topo. A partir daí as fichas são revistas de cima para baixo.

Antes de qualquer ficha entrar na fila, três coisas têm de ser verdade:

- A nota é pelo menos 0,10.
- Os dois lados têm primeiro nome, e eles são iguais ou diferem em no máximo uma letra. De 0,95 até 0,99 essa exigência não vale. De 0,99 para cima ela volta.
- Se os dois lados têm nome da mãe e esses nomes não combinam, a ficha sai. Combinar vale o nome inteiro, o começo em comum com pelo menos duas palavras, ou Jaro-Winkler ≥ 0,75. A exceção é nome completo e data de nascimento iguais nos dois lados: aí a ficha fica mesmo com a mãe diferente. De 0,95 para cima o veto de mãe não vale.

Quem sobrou desce uma escada. Cada degrau é uma fatia de 0,025 na nota, do mais certo para o menos certo. Em todo degrau, a pessoa do Censo ainda não pode ter CPF, e o CPF não pode já ter 3 pessoas do Censo. Se neste degrau o CPF passaria de 3, o grupo inteiro desse degrau fica de fora.

**Nota 0,99 ou mais.** A nota basta. Não se pede outra prova, e não se exige que seja o único candidato. Se a mesma pessoa tiver mais de um CPF nessa faixa, fica o de nota mais alta. Empate na nota desempata por CEP igual e nome da mãe igual.

**De 0,975 até 0,80.** A nota pede uma prova extra. Se a mesma pessoa tiver mais de um CPF nessa faixa, fica o de nota mais alta. Um CPF leva até 3. Vale a primeira prova que aparecer, nesta ordem:

1. Nome da mãe combina (igual, começo em comum, ou Jaro-Winkler ≥ 0,75).
2. Nome da rua e município combinam.
3. Data de nascimento igual e o começo do nome completo combina.
4. Data de nascimento igual, último nome igual e primeiro nome parecido (nome com pelo menos 6 letras e diferença pequena em relação ao tamanho).
5. Data igual ou com um pedaço só diferente (dia, mês, ano com um de diferença, ou um caractere), e no máximo uma palavra do nome diferente. Espaço e corte contam. Primeiro nome entre os 10 mais comuns não usa esta prova. Em nome de três palavras, a do meio trocada não entra.
6. Nome completo igual e CEP igual, e o primeiro nome não está entre os 10 mais comuns do Censo.
7. Pelo menos 80% das palavras do nome em comum e CEP igual, com a mesma restrição do primeiro nome comum.

**De 0,775 até 0,10.** A mesma prova extra, e mais uma trava: dentro daquela fatia de nota, a pessoa do Censo só pode ter um CPF candidato e esse CPF só pode ter uma pessoa do Censo. Se houver dois candidatos na mesma fatia, nenhum dos dois entra naquele degrau. De 0,70 para cima, nome da mãe com Jaro-Winkler > 0,90 passa nessa trava, mesmo com data diferente ou vazia. De 0,90 para cima, a mãe contida no outro nome também é prova, ainda que não seja o começo do nome e o Jaro-Winkler fique abaixo de 0,75.

Uma pessoa recebe um CPF só. Um CPF recebe no máximo três pessoas do Censo. A ficha aceita guarda o degrau e o motivo: `score` no topo, ou o nome da prova que liberou (`mae`, `logradouro`, `data_prefixo`, `data_primeiro`, `data_uma_palavra`, `nome_cep`, `tokens_cep`).
