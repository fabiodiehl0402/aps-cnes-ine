"""Mapa INE -> unidade de saúde (CNES) com histórico, a partir dos arquivos EP do DATASUS (CNES - Equipes).
Serve para localizar equipes que já saíram do CNES atual (desativadas, excluídas ou trocadas de INE)
mas ainda aparecem em listas do Ministério (ex.: ESAEI / suspensão por não envio ao SISAB).
Uso: python scripts/mapa_ine.py dados/  [meses=18]
Gera dados/ine_unidade.csv.gz (separador ;, UTF-8) e mantém dados/cnes_nomes.csv.gz (cache de nomes)."""
import csv, datetime, gzip, io, json, os, sys, time, urllib.request
import concurrent.futures as cf
import dbfread, pyreaddbc

OUT = sys.argv[1] if len(sys.argv) > 1 else 'dados'
MESES = int(sys.argv[2]) if len(sys.argv) > 2 else 18
UFS = ['RO', 'AC', 'AM', 'RR', 'PA', 'AP', 'TO', 'MA', 'PI', 'CE', 'RN', 'PB', 'PE', 'AL', 'SE', 'BA', 'MG', 'ES', 'RJ', 'SP', 'PR', 'SC', 'RS', 'MS', 'MT', 'GO', 'DF']
FTP = 'ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/EP/EP{uf}{aamm}.dbc'
H = {'Referer': 'https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp', 'User-Agent': 'Mozilla/5.0 (aps-cnes-ine)'}
TMP = '/tmp/ep'
os.makedirs(TMP, exist_ok=True)


def competencias(n):
    d = datetime.date.today().replace(day=1)
    out = []
    for _ in range(n + 1):           # mês atual quase nunca está publicado; vai para trás
        out.append(d.strftime('%y%m'))
        d = (d - datetime.timedelta(days=1)).replace(day=1)
    return out


def baixar(uf, aamm):
    dst = f'{TMP}/EP{uf}{aamm}.dbc'
    for i in range(3):
        try:
            with urllib.request.urlopen(FTP.format(uf=uf, aamm=aamm), timeout=180) as r, open(dst, 'wb') as f:
                f.write(r.read())
            return dst
        except Exception as e:
            if '550' in str(e) or 'No such file' in str(e):
                return None          # competência ainda não publicada
            time.sleep(5 * (i + 1))
    return None


def ler(path):
    dbf = path[:-4] + '.dbf'
    pyreaddbc.dbc2dbf(path, dbf)
    for r in dbfread.DBF(dbf, encoding='iso-8859-1'):
        yield r
    os.remove(dbf)
    os.remove(path)


def main():
    comps = competencias(MESES)
    mapa = {}   # ine -> registro mais recente
    jobs = [(uf, c) for uf in UFS for c in comps]
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(baixar, uf, c): (uf, c) for uf, c in jobs}
        for f in cf.as_completed(futs):
            uf, c = futs[f]
            p = f.result()
            if not p:
                continue
            n = 0
            for r in ler(p):
                ide = (r.get('IDEQUIPE') or '').strip()
                if len(ide) < 8:
                    continue
                ine = int(ide[-8:])
                comp = int(r.get('COMPETEN') or ('20' + c))
                old = mapa.get(ine)
                if old and old['ult_competencia'] >= comp:
                    continue
                dtd = (r.get('DT_DESAT') or '').strip()
                mapa[ine] = dict(ine=ine, cnes=int(r['CNES']), ibge=int(r['CODUFMUN']), tipo_eqp=(r.get('TIPO_EQP') or '').strip(),
                                 nome_equipe=(r.get('NOME_EQP') or '').strip(), dt_ativacao=(r.get('DT_ATIVA') or '').strip(),
                                 dt_desativacao='' if dtd in ('', '900001') else dtd, ult_competencia=comp)
                n += 1
            print(f'EP{uf}{c}: {n} equipes', flush=True)
    print('INEs no histórico:', len(mapa), flush=True)

    # nomes das unidades: cache + CNES atual (extração mensal) + API do CNES para o que faltar
    nomes = {}
    fc = os.path.join(OUT, 'cnes_nomes.csv.gz')
    if os.path.exists(fc):
        with gzip.open(fc, 'rt', encoding='utf-8') as fh:
            for r in csv.DictReader(fh, delimiter=';'):
                nomes[int(r['cnes'])] = r['estabelecimento']
    pa = os.path.join(OUT, 'atual')
    if os.path.isdir(pa):
        for fn in os.listdir(pa):
            if fn.endswith('_equipes.csv.gz'):
                with gzip.open(os.path.join(pa, fn), 'rt', encoding='utf-8') as fh:
                    for r in csv.DictReader(fh, delimiter=';'):
                        if r.get('estabelecimento'):
                            nomes[int(r['cnes'])] = r['estabelecimento']
    falta = sorted({(m['ibge'], m['cnes']) for m in mapa.values() if m['cnes'] not in nomes})
    print('unidades sem nome, consultando CNES:', len(falta), flush=True)

    def nome(par):
        ibge, cnes = par
        for i in range(3):
            try:
                u = f'https://cnes.datasus.gov.br/services/estabelecimentos/{ibge:06d}{cnes:07d}'
                b = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read()
                if b[:2] == b'\x1f\x8b':
                    b = gzip.decompress(b)
                d = json.loads(b) if b else {}
                return cnes, (d.get('noFantasia') or d.get('noEmpresarial') or '').strip()
            except Exception:
                time.sleep(2 * (i + 1))
        return cnes, ''
    with cf.ThreadPoolExecutor(12) as ex:
        for cnes, nm in ex.map(nome, falta):
            if nm:
                nomes[cnes] = nm

    with gzip.open(fc, 'wt', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['cnes', 'estabelecimento'])
        for k in sorted(nomes):
            w.writerow([k, nomes[k]])
    cols = ['ine', 'cnes', 'estabelecimento', 'ibge', 'tipo_eqp', 'nome_equipe', 'dt_ativacao', 'dt_desativacao', 'ult_competencia']
    with gzip.open(os.path.join(OUT, 'ine_unidade.csv.gz'), 'wt', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=';')
        w.writeheader()
        for ine in sorted(mapa):
            m = mapa[ine]
            m['estabelecimento'] = nomes.get(m['cnes'], '')
            w.writerow(m)
    print('ok', len(mapa), 'INEs,', sum(1 for m in mapa.values() if m['estabelecimento']), 'com nome da unidade')


if __name__ == '__main__':
    main()
