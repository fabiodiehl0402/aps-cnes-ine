"""Força de trabalho da administração municipal por município (CNES/DATASUS, arquivos PF - Profissionais).

Metodologia (resumo; detalhes em docs/metodologia_prof_mun.md):
  O CNES registra VÍNCULOS de profissionais com ESTABELECIMENTOS. Não é folha de pagamento: o empregador
  jurídico não é um campo próprio. A classificação combina dois campos oficiais do arquivo PF:
    NAT_JUR  - natureza jurídica do estabelecimento (Tabela de Natureza Jurídica CONCLA/RFB)
    VINCULAC - vínculo do profissional: 2 dígitos de vinculação + 2 de tipo + 2 de subtipo
               (decodificado contra o próprio CNES, services/estabelecimentos-profissionais)
  A = vínculo municipal direto CONFIRMADO: estabelecimento da administração pública municipal
      E vínculo empregatício direto e próprio (estatutário próprio, empregado público celetista próprio,
      temporário público, comissionado).
  B = PROVÁVEL, NÃO CONFIRMADO: estabelecimento municipal, mas o vínculo não comprova empregador municipal
      (servidor/empregado cedido, celetista sem indicação de empregador público, residência/bolsa próprias).
  C = NÃO MUNICIPAL OU INDIRETO: estabelecimento não municipal (privado, filantrópico, estadual, federal,
      consórcio, OS) ou vínculo intermediado/autônomo/cooperado/subsidiado por outro ente/estágio/informal.
  Só A compõe o quantitativo principal.

Uso: python scripts/prof_mun.py dados/ [UFs separadas por espaço, vazio = todas]
Gera:
  dados/prof_mun/<UF>.csv.gz        vínculos em estabelecimentos municipais (A, B e C), com situação e critério
  dados/prof_mun/_arquivos.txt
  dados/prof_mun_resumo.csv.gz      UF, município, IBGE, competência, CBO, profissão, situação, critério,
                                    profissionais distintos, vínculos, carga horária (todos os estabelecimentos)
  dados/prof_mun_indicadores.csv.gz por município: força de trabalho própria (A), rede própria municipal,
                                    rede sob gestão municipal, total no município
  dados/prof_mun_exclusoes.csv.gz   por município e motivo: o que ficou fora do quantitativo principal
  dados/prof_mun_resumo_A.xlsx      planilha com indicadores e o quantitativo principal (A) por CBO
  dados/cbo.csv                     nome e grupo de cada CBO
O identificador do profissional é um hash (SHA-1 truncado) do CNS; o CNS não é gravado."""
import csv, datetime, ftplib, gzip, hashlib, json, os, sys, time, urllib.request
import concurrent.futures as cf
import dbfread, pyreaddbc
import pandas as pd

OUT = sys.argv[1] if len(sys.argv) > 1 else 'dados'
TODAS = ['RO', 'AC', 'AM', 'RR', 'PA', 'AP', 'TO', 'MA', 'PI', 'CE', 'RN', 'PB', 'PE', 'AL', 'SE', 'BA', 'MG', 'ES', 'RJ', 'SP', 'PR', 'SC', 'RS', 'MS', 'MT', 'GO', 'DF']
UFS = sys.argv[2].split() if len(sys.argv) > 2 and sys.argv[2].strip() else TODAS
H = {'Referer': 'https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp', 'User-Agent': 'Mozilla/5.0 (aps-cnes-ine)'}
TMP = '/tmp/pf'
PASTA = os.path.join(OUT, 'prof_mun')
os.makedirs(TMP, exist_ok=True)
os.makedirs(PASTA, exist_ok=True)

# Natureza jurídica (CONCLA/RFB) - administração pública municipal
NAT_MUN = {'1031': 'Órgão Público do Poder Executivo Municipal', '1066': 'Órgão Público do Poder Legislativo Municipal',
           '1120': 'Autarquia Municipal', '1155': 'Fundação Pública de Direito Público Municipal',
           '1180': 'Órgão Público Autônomo Municipal', '1244': 'Município',
           '1279': 'Fundação Pública de Direito Privado Municipal', '1309': 'Fundo Público da Administração Indireta Municipal',
           '1333': 'Fundo Público da Administração Direta Municipal'}
NAT_FED = {'1015', '1040', '1074', '1104', '1139', '1163', '1252', '1287', '1317', '1341'}
NAT_EST = {'1023', '1058', '1082', '1112', '1147', '1171', '1236', '1260', '1295', '1325'}
NAT_CONS = {'1210', '1228'}

# VINCULAC (vinculação + tipo + subtipo), conforme o próprio CNES
VINC = {
    '010101': ('A', 'Estatutário efetivo - servidor próprio'),
    '010202': ('A', 'Empregado público celetista - próprio'),
    '010301': ('A', 'Contrato temporário/prazo determinado - público'),
    '010403': ('A', 'Cargo comissionado - servidor público próprio'),
    '010405': ('A', 'Cargo comissionado - sem vínculo com o setor público'),
    '010102': ('B', 'Estatutário efetivo - servidor CEDIDO (empregador pode ser outro ente)'),
    '010203': ('B', 'Empregado público celetista - CEDIDO (empregador pode ser outro ente)'),
    '010404': ('B', 'Cargo comissionado - servidor público CEDIDO'),
    '010500': ('B', 'Celetista sem indicação de empregador público'),
    '050101': ('B', 'Residência - própria (não é vínculo empregatício)'),
    '070101': ('B', 'Bolsa - própria (não é vínculo empregatício)'),
    '010302': ('C', 'Contrato temporário - PRIVADO'),
    '020900': ('C', 'Autônomo - pessoa jurídica'),
    '021000': ('C', 'Autônomo - pessoa física'),
    '021100': ('C', 'Autônomo - cooperado'),
    '050102': ('C', 'Residência subsidiada por outro ente/entidade'),
    '060101': ('C', 'Estágio (sem vínculo empregatício)'),
    '060102': ('C', 'Estágio subsidiado por outro ente/entidade'),
    '070102': ('C', 'Bolsa subsidiada por outro ente/entidade (ex.: programas federais)'),
    '090100': ('C', 'Informal - contratado verbalmente'),
    '090200': ('C', 'Informal - voluntariado'),
    '100100': ('C', 'Servidor público cedido para a iniciativa privada'),
    '100200': ('C', 'Servidor público cedido para a iniciativa privada'),
    '100300': ('C', 'Servidor público cedido para a iniciativa privada'),
}


def classifica(nat, vinc):
    if nat not in NAT_MUN:
        if nat in NAT_EST: return 'C', 'Estabelecimento da administração estadual'
        if nat in NAT_FED: return 'C', 'Estabelecimento da administração federal'
        if nat in NAT_CONS: return 'C', 'Estabelecimento de consórcio público'
        if nat.startswith('1'): return 'C', f'Estabelecimento público não municipal (natureza {nat})'
        if nat.startswith('2'): return 'C', 'Estabelecimento empresarial/privado'
        if nat.startswith('3'): return 'C', 'Entidade sem fins lucrativos (filantrópica, associação, OS)'
        if nat.startswith('4'): return 'C', 'Pessoa física (consultório)'
        return 'C', f'Natureza jurídica não informada/não municipal ({nat or "vazio"})'
    if vinc.startswith('08'): return 'C', 'Vínculo intermediado (OS, OSCIP, empresa, cooperativa) em estabelecimento municipal'
    if vinc in VINC: return VINC[vinc]
    return 'B', f'Vínculo não decodificado ({vinc or "vazio"}) em estabelecimento municipal'


def grupo(c):
    if c.startswith('225') or c.startswith('2231'): return 'Médico'
    if c.startswith('2235'): return 'Enfermeiro'
    if c in ('515105', '322255'): return 'Agente comunitário de saúde'
    if c in ('515140', '352210'): return 'Agente de combate às endemias'
    if c.startswith('3222'): return 'Técnico/auxiliar de enfermagem'
    if c.startswith('2232'): return 'Cirurgião-dentista'
    if c.startswith('3224'): return 'Técnico/auxiliar de saúde bucal'
    if c.startswith('2236'): return 'Fisioterapeuta'
    if c.startswith('2241'): return 'Profissional de educação física'
    if c.startswith('2515'): return 'Psicólogo'
    if c.startswith('2234'): return 'Farmacêutico'
    if c.startswith('2237'): return 'Nutricionista'
    if c.startswith('2238'): return 'Fonoaudiólogo'
    if c.startswith('2239'): return 'Terapeuta ocupacional'
    if c.startswith('2516'): return 'Assistente social'
    if c.startswith('2212') or c.startswith('2211'): return 'Biomédico/biólogo'
    if c.startswith('2233'): return 'Médico veterinário'
    if c.startswith('32') or c.startswith('3135'): return 'Outros técnicos de saúde'
    if c.startswith('4') or c.startswith('1') or c.startswith('2521') or c.startswith('3513'): return 'Gestão e administrativo'
    if c.startswith('5') or c.startswith('7') or c.startswith('9'): return 'Apoio e serviços gerais'
    return 'Outros'


def conectar():
    f = ftplib.FTP('ftp.datasus.gov.br', timeout=180)
    f.login()
    f.cwd('/dissemin/publicos/CNES/200508_/Dados/PF')
    return f


def baixar(ftp, nome):
    dst = f'{TMP}/{nome}'
    for i in range(3):
        try:
            with open(dst, 'wb') as fh:
                ftp.retrbinary('RETR ' + nome, fh.write)
            return ftp, dst
        except Exception as e:
            print('falha', nome, e, flush=True)
            time.sleep(10 * (i + 1))
            try:
                ftp.close()
            except Exception:
                pass
            ftp = conectar()
    return ftp, None


def g(r, *ks):
    for k in ks:
        v = r.get(k)
        if v not in (None, ''):
            return str(v).strip()
    return ''


def num(s):
    try:
        return int(float(s))
    except Exception:
        return 0


def api(url):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40).read()
            if b[:2] == b'\x1f\x8b':
                b = gzip.decompress(b)
            return json.loads(b) if b else None
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def hid(cns, nome):
    base = cns if cns else 'NOME:' + nome
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def main():
    ftp = conectar()
    disp = {n.upper(): n for n in ftp.nlst()}
    d = datetime.date.today().replace(day=1)
    comps = []
    for _ in range(4):
        comps.append(d.strftime('%y%m'))
        d = (d - datetime.timedelta(days=1)).replace(day=1)
    amostra, leves = {}, []
    cols = ['competencia', 'ibge', 'cnes', 'cbo', 'nome', 'id_prof', 'sus', 'ch', 'vinculo', 'tp_unid', 'nat_jur', 'tpgestao', 'situacao', 'criterio']
    for uf in UFS:
        nome = next((disp[f'PF{uf}{c}.DBC'] for c in comps if f'PF{uf}{c}.DBC' in disp), None)
        if not nome:
            print('sem arquivo PF para', uf, flush=True)
            continue
        ftp, p = baixar(ftp, nome)
        if not p:
            continue
        dbf = p[:-4] + '.dbf'
        pyreaddbc.dbc2dbf(p, dbf)
        n = nm = 0
        with gzip.open(os.path.join(PASTA, f'{uf}.csv.gz'), 'wt', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter=';')
            w.writeheader()
            for r in dbfread.DBF(dbf, encoding='iso-8859-1'):
                cbo = g(r, 'CBO')
                ibge, cnes = g(r, 'CODUFMUN'), g(r, 'CNES')
                amostra.setdefault(cbo, (ibge, cnes))
                nat, vinc, gest = g(r, 'NAT_JUR', 'NATUREZA'), g(r, 'VINCULAC'), g(r, 'TPGESTAO')
                sit, crit = classifica(nat, vinc)
                pid = hid(g(r, 'CNS_PROF'), g(r, 'NOMEPROF'))
                ch = num(g(r, 'HORA_AMB')) + num(g(r, 'HORAHOSP')) + num(g(r, 'HORAOUTR'))
                comp = g(r, 'COMPETEN') or '20' + nome[4:8]
                leves.append((uf, ibge, comp, cbo, pid, ch, sit, crit, nat in NAT_MUN, gest in ('M', 'D')))
                n += 1
                if nat in NAT_MUN:
                    w.writerow(dict(competencia=comp, ibge=ibge, cnes=cnes, cbo=cbo, nome=g(r, 'NOMEPROF'), id_prof=pid,
                                    sus='S' if g(r, 'PROF_SUS') == '1' else ('N' if g(r, 'PROFNSUS') == '1' else ''),
                                    ch=ch, vinculo=vinc, tp_unid=g(r, 'TP_UNID'), nat_jur=nat, tpgestao=gest, situacao=sit, criterio=crit))
                    nm += 1
        os.remove(dbf)
        os.remove(p)
        print(f'{nome}: {n} vínculos no estado, {nm} em estabelecimentos municipais', flush=True)
    try:
        ftp.quit()
    except Exception:
        pass
    with open(os.path.join(PASTA, '_arquivos.txt'), 'w') as fh:
        fh.write('\n'.join(sorted(f for f in os.listdir(PASTA) if f.endswith('.csv.gz') and not f.startswith('_'))) + '\n')

    # ---- nomes de CBO (cache; o que faltar vem do próprio CNES)
    fc = os.path.join(OUT, 'cbo.csv')
    nomes = {}
    if os.path.exists(fc):
        with open(fc, encoding='utf-8') as fh:
            for r in csv.DictReader(fh, delimiter=';'):
                if r.get('ocupacao'):
                    nomes[r['cbo']] = r['ocupacao']
    falta = {c: v for c, v in amostra.items() if c and c not in nomes}
    print('CBOs sem nome:', len(falta), flush=True)

    def busca(item):
        c, (ibge, cnes) = item
        try:
            return api(f'https://cnes.datasus.gov.br/services/estabelecimentos-profissionais/{int(ibge):06d}{int(cnes):07d}') or []
        except Exception:
            return []
    with cf.ThreadPoolExecutor(8) as ex:
        for lst in ex.map(busca, sorted(falta.items())):
            for p in lst:
                c, ds = str(p.get('cbo') or ''), (p.get('dsCbo') or '').strip()
                if c and ds and c not in nomes:
                    nomes[c] = ds
    todos = sorted(set(nomes) | set(c for c in amostra if c))
    with open(fc, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['cbo', 'ocupacao', 'grupo'])
        for c in todos:
            w.writerow([c, nomes.get(c, ''), grupo(c)])

    # ---- nomes dos municípios (IBGE)
    mun = {}
    try:
        lst = json.loads(urllib.request.urlopen('https://servicodados.ibge.gov.br/api/v1/localidades/municipios', timeout=60).read())
        mun = {str(m['id'])[:6]: m['nome'] for m in lst}
    except Exception as e:
        print('sem nomes do IBGE:', e, flush=True)

    # ---- agregados
    df = pd.DataFrame(leves, columns=['uf', 'ibge', 'competencia', 'cbo', 'id_prof', 'ch', 'situacao', 'criterio', 'rede_propria', 'gestao_mun'])
    del leves
    for c in ('uf', 'ibge', 'competencia', 'cbo', 'situacao', 'criterio'):
        df[c] = df[c].astype('category')
    df['municipio'] = df['ibge'].astype(str).map(mun).fillna('')
    df['profissao'] = df['cbo'].astype(str).map(nomes).fillna('')
    chave = ['uf', 'municipio', 'ibge', 'competencia', 'cbo', 'profissao', 'situacao', 'criterio']
    res = df.groupby(chave, observed=True).agg(profissionais_distintos=('id_prof', 'nunique'), vinculos=('id_prof', 'size'),
                                               carga_horaria=('ch', 'sum')).reset_index()
    res.to_csv(os.path.join(OUT, 'prof_mun_resumo.csv.gz'), sep=';', index=False, encoding='utf-8', compression='gzip')
    exc = df[df.situacao != 'A'].groupby(['uf', 'municipio', 'ibge', 'competencia', 'situacao', 'criterio'], observed=True).agg(
        profissionais_distintos=('id_prof', 'nunique'), vinculos=('id_prof', 'size')).reset_index()
    exc.to_csv(os.path.join(OUT, 'prof_mun_exclusoes.csv.gz'), sep=';', index=False, encoding='utf-8', compression='gzip')
    k = ['uf', 'municipio', 'ibge', 'competencia']
    tot = df.groupby(k, observed=True).agg(profissionais_no_municipio=('id_prof', 'nunique'))
    a = df[df.situacao == 'A'].groupby(k, observed=True).agg(forca_propria_A=('id_prof', 'nunique'), vinculos_A=('id_prof', 'size'), carga_horaria_A=('ch', 'sum'))
    b = df[df.situacao == 'B'].groupby(k, observed=True).agg(provaveis_B=('id_prof', 'nunique'))
    rp = df[df.rede_propria].groupby(k, observed=True).agg(rede_propria_municipal=('id_prof', 'nunique'))
    gm = df[df.gestao_mun].groupby(k, observed=True).agg(rede_sob_gestao_municipal=('id_prof', 'nunique'))
    ind = tot.join([a, b, rp, gm], how='left').fillna(0).astype(int).reset_index()
    ind.to_csv(os.path.join(OUT, 'prof_mun_indicadores.csv.gz'), sep=';', index=False, encoding='utf-8', compression='gzip')
    try:
        with pd.ExcelWriter(os.path.join(OUT, 'prof_mun_resumo_A.xlsx')) as xw:
            ind.to_excel(xw, sheet_name='Indicadores', index=False)
            ra = res[res.situacao == 'A'].drop(columns=['situacao', 'criterio'])
            ra.head(1_000_000).to_excel(xw, sheet_name='Vinculo direto (A) por CBO', index=False)
    except Exception as e:
        print('xlsx não gerado:', e, flush=True)
    print('ok:', len(df), 'vínculos;', res.shape[0], 'linhas de resumo;', int(ind.forca_propria_A.sum()), 'profissionais A (soma dos municípios)', flush=True)


if __name__ == '__main__':
    main()
