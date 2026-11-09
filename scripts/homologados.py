"""Relação de equipes (INE) e estabelecimentos (CNES) homologados — e-Gestor/Relatórios APS.
Mesma planilha do botão Download Excel de relatorioaps.saude.gov.br (ines-cnes-homologados).
Uso: python scripts/homologados.py dados/egestor/ines-cnes-homologados.xlsx"""
import json, sys, time, urllib.request
from openpyxl import Workbook
API = 'https://relatorioaps-prd.saude.gov.br/financiamento/homologacao'
OUT = sys.argv[1] if len(sys.argv) > 1 else 'ines-cnes-homologados.xlsx'
def get(p):
    for i in range(5):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(f'{API}/{p}', headers={'User-Agent': 'Mozilla/5.0'}), timeout=300).read())
        except Exception as e:
            print('falha', p, e, flush=True); time.sleep(15 * (i + 1))
    raise SystemExit('não foi possível baixar ' + p)
eq, es = get('equipes'), get('estabelecimentos')
if len(eq) < 10000 or len(es) < 1000:
    raise SystemExit(f'resposta pequena demais ({len(eq)} equipes, {len(es)} estabelecimentos); arquivo mantido')
CE = ['UF', 'MUNICÍPIO', 'IBGE', 'INE', 'CÓDIGO DO TIPO DE EQUIPE', 'TIPO DE EQUIPE', 'SUBTIPO DE EQUIPE', 'PORTARIA', 'ESFERA ADMINISTRATIVA']
CS = ['UF', 'MUNICÍPIO', 'IBGE', 'CNES', 'TIPO DO ESTABELECIMENTO', 'PORTARIA']
wb = Workbook(); wb.remove(wb.active)
def aba(nome, cab, linhas):
    ws = wb.create_sheet(nome); ws.append(cab)
    for l in linhas: ws.append(l)
for nome, tp, sub in [('eSF', '70', 'Convencional'), ('eSF Ribeirinha', '70', 'Ribeirinha'), ('eAP', '76', None), ('eSB', '71', None), ('eCR', '73', None), ('eAPP', '74', None), ('eMULTI', '72', None)]:
    aba(nome, CE, [[r['siglaUf'], r['nomeMunicipio'], r['codigoMunicipio'], r['codigoEquipe'], r['codigoTipoEquipe'], r['descricaoTipoEquipe'], r['descricaoSubtipoEquipe'], r['descricaoPortariaHomologacao'], r['descricaoEsferaAdministrativa']]
                   for r in eq if r['codigoTipoEquipe'] == tp and (sub is None or r['descricaoSubtipoEquipe'] == sub)])
aba('Estabelecimentos', CS, [[r['siglaUf'], r['nomeMunicipio'], r['codigoMunicipio'], r['codigoCnes'], r['descricaoDominioUnidade'], r['descricaoPortariaHomologacao']] for r in es])
aba('Dicionário de Dados', ['NOME DA COLUNA', 'DESCRIÇÃO DA COLUNA'], [['', ''], ['UF', 'Unidade da Federação'], ['MUNICÍPIO', 'Nome do Município'], ['IBGE', 'Código IBGE do Município'], ['INE', 'Código INE da Equipe'], ['TIPO DE EQUIPE', 'Tipo da Equipe'], ['PORTARIA', 'Portaria de publicação de homologação do INE'], ['', ''], ['UF', 'Unidade da Federação'], ['MUNICÍPIO', 'Nome do Município'], ['IBGE', 'Código IBGE do Município'], ['CNES', 'Código CNES do Estabelecimento'], ['TIPO DO ESTABELECIMENTO', 'Tipo do Estabelecimento'], ['PORTARIA', 'Portaria de publicação de homologação do CNES']])
wb.save(OUT)
print('ok', OUT, len(eq), 'equipes', len(es), 'estabelecimentos', {ws.title: ws.max_row - 1 for ws in wb})
