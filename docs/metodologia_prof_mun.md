# Força de trabalho da administração municipal — CNES

## Pergunta
Quantos profissionais de saúde têm **vínculo direto com a Prefeitura/Secretaria Municipal de Saúde** em cada município, por ocupação (CBO)?
Não é "quem trabalha geograficamente no município".

## Base
Arquivos **PF (Profissionais)** do CNES/DATASUS — `ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/PF/PF{UF}{AAMM}.dbc`, uma linha por vínculo profissional × estabelecimento × CBO, competência mais recente publicada.

Campos usados: `CODUFMUN` (IBGE do estabelecimento), `CNES`, `CNS_PROF` (gravado só como hash SHA-1 truncado), `NOMEPROF`, `CBO`, `NAT_JUR` (natureza jurídica do estabelecimento), `TPGESTAO` (gestão M/E/D), `ESFERA_A`, `TP_UNID`, `VINCULAC`, `PROF_SUS`/`PROFNSUS`, `HORA_AMB`/`HORAHOSP`/`HORAOUTR`, `COMPETEN`.

## Limitação central
O CNES registra o vínculo do profissional **com o estabelecimento**; não há campo de empregador/CNPJ do contratante. A comprovação de vínculo direto é feita por **dois campos oficiais combinados**: a natureza jurídica do estabelecimento e o código de vínculo. Onde esses campos não comprovam o empregador, o vínculo fica como **não confirmado (B)**. Folha de pagamento (SIOPS, portais de transparência, RAIS/eSocial) é a fonte para confirmação nominal.

## Natureza jurídica municipal (Tabela CONCLA/RFB)
1031 Órgão Público do Poder Executivo Municipal · 1066 Órgão Público do Poder Legislativo Municipal · 1120 Autarquia Municipal · 1155 Fundação Pública de Direito Público Municipal · 1180 Órgão Público Autônomo Municipal · 1244 Município · 1279 Fundação Pública de Direito Privado Municipal · 1309 Fundo Público da Administração Indireta Municipal · 1333 Fundo Público da Administração Direta Municipal.
Fora: 1xxx estaduais/federais, 1210/1228 consórcios públicos, 2xxx empresariais (inclui empresas públicas, que podem ser de qualquer esfera), 3xxx sem fins lucrativos (filantrópicas, associações, OS), 4xxx pessoas físicas.

## Código de vínculo (VINCULAC = vinculação + tipo + subtipo)
Decodificado consultando, para cada código presente na base nacional, profissionais reais no serviço do próprio CNES (`services/estabelecimentos-profissionais`).

| Código | CNES | Situação |
|---|---|---|
| 010101 | Vínculo empregatício · Estatutário efetivo · Servidor próprio | A |
| 010202 | Vínculo empregatício · Empregado público celetista · Próprio | A |
| 010301 | Vínculo empregatício · Contratado temporário/prazo determinado · Público | A |
| 010403 | Vínculo empregatício · Cargo comissionado · Servidor público próprio | A |
| 010405 | Vínculo empregatício · Cargo comissionado · Sem vínculo com o setor público | A |
| 010102 | Vínculo empregatício · Estatutário efetivo · Servidor cedido | B |
| 010203 | Vínculo empregatício · Empregado público celetista · Cedido | B |
| 010404 | Vínculo empregatício · Cargo comissionado · Servidor público cedido | B |
| 010500 | Vínculo empregatício · Celetista (sem indicação de empregador público) | B |
| 050101 | Residência · Residente · Próprio | B |
| 070101 | Bolsa · Bolsista · Próprio | B |
| 010302 | Vínculo empregatício · Contratado temporário · Privado | C |
| 020900 / 021000 / 021100 | Autônomo · Pessoa jurídica / Pessoa física / Cooperado | C |
| 0801xx–0807xx | Intermediado (empregado público celetista, temporário, comissionado, celetista, autônomo PJ/PF, cooperado, servidor cedido) | C |
| 050102 / 060102 / 070102 | Residência / Estágio / Bolsa subsidiados por outro ente/entidade | C |
| 060101 | Estágio · Próprio | C |
| 090100 / 090200 | Informal · Contratado verbalmente / Voluntariado | C |
| 1001xx–1003xx | Servidor público cedido para a iniciativa privada | C |

## Regra de classificação
- **A — vínculo municipal direto confirmado**: natureza jurídica municipal **e** vínculo da lista A.
- **B — provável, não confirmado**: natureza jurídica municipal, mas vínculo que não comprova empregador municipal (cedidos, celetista genérico, residência/bolsa próprias, código não decodificado).
- **C — não municipal ou indireto**: natureza jurídica não municipal (qualquer vínculo) **ou** vínculo intermediado, autônomo, cooperado, subsidiado por outro ente, estágio, informal, cedido à iniciativa privada.
- Gestão municipal (`TPGESTAO`), atendimento SUS ou recurso municipal **não** entram como critério de inclusão.

## Contagem
- Profissional = hash do CNS (sem CNS: hash do nome). Contado uma vez no total do município; por CBO, uma vez por ocupação.
- Vínculos e carga horária somados apenas nos vínculos da categoria considerada.
- Múltiplos vínculos (ex.: UBS municipal + hospital estadual + clínica): só o vínculo A entra no quantitativo principal; os demais ficam em C.

## Indicadores por município
- **Força de trabalho própria (A)** — quantitativo principal.
- **Prováveis (B)** — auditoria.
- **Rede própria municipal** — profissionais em estabelecimentos de natureza jurídica municipal, qualquer vínculo.
- **Rede sob gestão municipal** — profissionais em estabelecimentos com `TPGESTAO` M ou D (inclui privados contratados).
- **Profissionais no município** — qualquer estabelecimento.

## Saídas (GitHub `dados/`)
`prof_mun/<UF>.csv.gz` (vínculos em estabelecimentos municipais, com situação e critério) · `prof_mun_resumo.csv.gz` · `prof_mun_indicadores.csv.gz` · `prof_mun_exclusoes.csv.gz` · `prof_mun_resumo_A.xlsx` · `cbo.csv`. Atualização mensal automática após a rodada do CNES.
