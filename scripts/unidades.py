"""Endereço e coordenadas (latitude/longitude) de cada unidade de saúde que tem equipe no CNES.
Lê os CNES das equipes em dados/atual/*_equipes.csv.gz e consulta o cadastro do estabelecimento no CNES.
Uso: python scripts/unidades.py dados/   (FULL=1 reconsulta tudo; sem isso, só o que falta no cache)
Gera dados/unidades.csv.gz (separador ;, UTF-8)."""
import csv, gzip, json, os, sys, time, urllib.request
import concurrent.futures as cf

OUT = sys.argv[1] if len(sys.argv) > 1 else 'dados'
H = {'Referer': 'https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp', 'User-Agent': 'Mozilla/5.0 (aps-cnes-ine)'}
THREADS = int(os.environ.get('THREADS', '12'))
BUDGET = int(os.environ.get('BUDGET_MIN', '270')) * 60
COLS = ['cnes', 'ibge', 'estabelecimento', 'tipo_unidade', 'subtipo', 'logradouro', 'numero', 'complemento', 'bairro', 'cep',
        'telefone', 'lat', 'lon', 'dt_atualizacao']


def get(ibge, cnes):
    u = f'https://cnes.datasus.gov.br/services/estabelecimentos/{ibge:06d}{cnes:07d}'
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read()
            if b[:2] == b'\x1f\x8b':
                b = gzip.decompress(b)
            return json.loads(b) if b else None
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def num(s):
    try:
        v = float(str(s).replace(',', '.'))
        return '' if v == 0 else f'{v:.6f}'
    except Exception:
        return ''


def main():
    t0 = time.time()
    alvo = {}   # cnes -> (ibge, nome)
    pa = os.path.join(OUT, 'atual')
    for fn in sorted(os.listdir(pa)):
        if fn.endswith('_equipes.csv.gz'):
            with gzip.open(os.path.join(pa, fn), 'rt', encoding='utf-8') as fh:
                for r in csv.DictReader(fh, delimiter=';'):
                    alvo[int(r['cnes'])] = (int(r['ibge']), r.get('estabelecimento') or '')
    print('unidades com equipe no CNES:', len(alvo), flush=True)
    cache = {}
    fo = os.path.join(OUT, 'unidades.csv.gz')
    if os.path.exists(fo) and os.environ.get('FULL') != '1':
        with gzip.open(fo, 'rt', encoding='utf-8') as fh:
            for r in csv.DictReader(fh, delimiter=';'):
                cache[int(r['cnes'])] = r
    falta = [(ib, c) for c, (ib, _) in alvo.items() if c not in cache or not cache[c].get('lat')]
    print('a consultar no CNES:', len(falta), flush=True)
    ex = cf.ThreadPoolExecutor(THREADS)
    fs = {ex.submit(get, ib, c): (ib, c) for ib, c in falta}
    n = 0
    try:
        for f in cf.as_completed(fs, timeout=max(60, BUDGET - (time.time() - t0))):
            ib, c = fs[f]
            d = f.result()
            n += 1
            if d:
                cache[c] = dict(cnes=c, ibge=ib, estabelecimento=(d.get('noFantasia') or alvo[c][1] or '').strip(),
                                tipo_unidade=(d.get('dsTpUnidade') or '').strip(), subtipo=(d.get('dsStpUnidade') or '').strip(),
                                logradouro=(d.get('noLogradouro') or '').strip(), numero=(d.get('nuEndereco') or '').strip(),
                                complemento=(d.get('noComplemento') or '').strip(), bairro=(d.get('bairro') or '').strip(),
                                cep=(d.get('cep') or '').strip(), telefone=(d.get('nuTelefone') or '').strip(),
                                lat=num(d.get('nuLatitude')), lon=num(d.get('nuLongitude')), dt_atualizacao=(d.get('dtAtualizacao') or '').strip())
            if n % 2000 == 0:
                print(f'{n}/{len(falta)} {int(time.time() - t0)}s', flush=True)
    except cf.TimeoutError:
        print('tempo esgotado: gravando o que já foi consultado', flush=True)
    ex.shutdown(wait=False, cancel_futures=True)
    rows = [cache[c] for c in sorted(cache) if c in alvo]
    with gzip.open(fo, 'wt', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print('ok', len(rows), 'unidades,', sum(1 for r in rows if r.get('lat')), 'com coordenadas', flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == '__main__':
    main()
