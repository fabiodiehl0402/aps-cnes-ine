"""Todos os profissionais com vínculo em estabelecimentos de saúde de cada município (CNES, arquivos PF do DATASUS).
Não depende de equipe: qualquer estabelecimento (UBS, hospital, clínica, consultório), SUS e não SUS, todas as ocupações.
Uso: python scripts/prof_mun.py dados/ [UFs separadas por espaço, vazio = todas]
Gera dados/prof_mun/<UF>.csv.gz (um por UF), dados/prof_mun/_arquivos.txt e dados/cbo.csv (nome e grupo de cada CBO)."""
import csv, datetime, ftplib, gzip, json, os, sys, time, urllib.request
import concurrent.futures as cf
import dbfread, pyreaddbc

OUT = sys.argv[1] if len(sys.argv) > 1 else 'dados'
TODAS = ['RO', 'AC', 'AM', 'RR', 'PA', 'AP', 'TO', 'MA', 'PI', 'CE', 'RN', 'PB', 'PE', 'AL', 'SE', 'BA', 'MG', 'ES', 'RJ', 'SP', 'PR', 'SC', 'RS', 'MS', 'MT', 'GO', 'DF']
UFS = sys.argv[2].split() if len(sys.argv) > 2 and sys.argv[2].strip() else TODAS
H = {'Referer': 'https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp', 'User-Agent': 'Mozilla/5.0 (aps-cnes-ine)'}
TMP = '/tmp/pf'
PASTA = os.path.join(OUT, 'prof_mun')
os.makedirs(TMP, exist_ok=True)
os.makedirs(PASTA, exist_ok=True)
COLS = ['competencia', 'ibge', 'cnes', 'cbo', 'nome', 'cns', 'sus', 'ch', 'vinculo', 'tp_unid']


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
    if c.startswith('32') or c.startswith('324') or c.startswith('3135'): return 'Outros técnicos de saúde'
    if c.startswith('4') or c.startswith('1') or c.startswith('2521') or c.startswith('3513'): return 'Gestão e administrativo'
    if c.startswith('5') or c.startswith('7') or c.startswith('78') or c.startswith('9'): return 'Apoio e serviços gerais'
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


def main():
    ftp = conectar()
    disp = {n.upper(): n for n in ftp.nlst()}
    d = datetime.date.today().replace(day=1)
    comps = []
    for _ in range(4):
        comps.append(d.strftime('%y%m'))
        d = (d - datetime.timedelta(days=1)).replace(day=1)
    amostra, primeira = {}, True
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
        n = 0
        with gzip.open(os.path.join(PASTA, f'{uf}.csv.gz'), 'wt', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=COLS, delimiter=';')
            w.writeheader()
            for r in dbfread.DBF(dbf, encoding='iso-8859-1'):
                if primeira:
                    print('colunas PF:', ', '.join(r.keys()), flush=True)
                    primeira = False
                cbo = g(r, 'CBO')
                ibge, cnes = g(r, 'CODUFMUN'), g(r, 'CNES')
                amostra.setdefault(cbo, (ibge, cnes))
                w.writerow(dict(competencia=g(r, 'COMPETEN') or '20' + nome[4:8], ibge=ibge, cnes=cnes, cbo=cbo,
                                nome=g(r, 'NOMEPROF'), cns=g(r, 'CNS_PROF'),
                                sus='S' if g(r, 'PROF_SUS') == '1' else ('N' if g(r, 'PROFNSUS') == '1' else ''),
                                ch=num(g(r, 'HORA_AMB')) + num(g(r, 'HORAHOSP')) + num(g(r, 'HORAOUTR')),
                                vinculo=g(r, 'VINCULAC'), tp_unid=g(r, 'TP_UNID')))
                n += 1
        os.remove(dbf)
        os.remove(p)
        print(f'{nome}: {n} vínculos', flush=True)
    try:
        ftp.quit()
    except Exception:
        pass
    with open(os.path.join(PASTA, '_arquivos.txt'), 'w') as fh:
        fh.write('\n'.join(sorted(f for f in os.listdir(PASTA) if f.endswith('.csv.gz'))) + '\n')

    # nome de cada CBO: cache; o que faltar vem do próprio CNES, num estabelecimento onde esse CBO aparece
    fc = os.path.join(OUT, 'cbo.csv')
    nomes = {}
    if os.path.exists(fc):
        with open(fc, encoding='utf-8') as fh:
            for r in csv.DictReader(fh, delimiter=';'):
                if r.get('ocupacao'):
                    nomes[r['cbo']] = r['ocupacao']
    falta = {c: v for c, v in amostra.items() if c and c not in nomes}
    print('CBOs sem nome:', len(falta), flush=True)
    vistos = set()

    def busca(item):
        c, (ibge, cnes) = item
        try:
            u = f'https://cnes.datasus.gov.br/services/estabelecimentos-profissionais/{int(ibge):06d}{int(cnes):07d}'
        except Exception:
            return []
        return api(u) or []
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
    print('ok;', len(todos), 'CBOs,', sum(1 for c in todos if nomes.get(c)), 'com nome', flush=True)


if __name__ == '__main__':
    main()
