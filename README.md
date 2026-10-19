# APS · CNES por INE (todos os municípios)

Foto mensal das equipes da Atenção Primária por **INE** e dos profissionais vinculados, para todos os municípios do Brasil, extraída do serviço público do CNES (cnes.datasus.gov.br). Alimenta as páginas "Equipes por INE" do Power BI **RELATÓRIO SITUACIONAL APS 2026**.

## Como funciona
- O GitHub Actions roda `scripts/extrair.py` **todo dia 5** (e quando você clicar em *Run workflow*), em 54 partes paralelas (UFs grandes divididas).
- Resultado em `dados/`:
  - `dados/atual/` — foto mais recente (`UF-parte_equipes.csv.gz`, `UF-parte_profissionais.csv.gz`, `_arquivos.txt`)
  - `dados/anterior/` — foto do mês anterior (para comparar INE a INE)
  - `dados/historico/AAAA-MM/` — todas as fotos guardadas
- O Power BI lê direto do link "raw" do GitHub — funciona em qualquer computador e na atualização agendada do Power BI Service.

## Campos (equipes)
`data_ref, ibge, cnes, estabelecimento, ine, tipo (eSF/eAP/eSB/eMulti/eCR/eAPP/Outra), nome_equipe, n_medico, n_enfermeiro, n_tec_enf, n_acs, n_dentista, n_asb_tsb, n_outros, n_total, faltando, situacao (Completa/Incompleta/Desativada/Sem regra), ult_entrada, entradas_120d`

Regra de "faltando": eSF sem médico, enfermeiro ou téc./aux. de enfermagem; eAP sem médico ou enfermeiro; eSB sem dentista ou ASB/TSB. ACS aparece na composição, mas não entra na regra.

## Power BI
Parâmetro `CNES_URL_BASE` = `https://raw.githubusercontent.com/fabiodiehl0402/aps-cnes-ine/main/dados/` e as consultas em `powerbi/`.
