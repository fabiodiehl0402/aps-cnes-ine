"""Extrai do CNES (cnes.datasus.gov.br) as equipes por INE e seus profissionais de uma UF inteira.
Uso: python scripts/extrair.py RO saida/ [parte total]   ex.: SP saida/ 2 6
Gera saida/RO_equipes.csv.gz e saida/RO_profissionais.csv.gz (separador ;, UTF-8)."""
import json, sys, time, csv, gzip, os, datetime, collections, urllib.request
import concurrent.futures as cf

H = {'Referer': 'https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp', 'User-Agent': 'Mozilla/5.0 (aps-cnes-ine)'}
B = 'https://cnes.datasus.gov.br/services/'
THREADS = int(os.environ.get('THREADS', '8'))

def get(url, tries=5):
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60)
            b = r.read()
            if b[:2] == b'\x1f\x8b': b = gzip.decompress(b)
            return json.loads(b) if b else []
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def municipios(uf):
    d = get(f'https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios') or []
    return [str(m['id'])[:6] for m in d]

def cat(c):
    c = str(c)
    if c.startswith('225') or c.startswith('2231'): return 'Médico'
    if c.startswith('2235'): return 'Enfermeiro'
    if c.startswith('3222'): return 'Téc./aux. enfermagem'
    if c in ('515105', '322255'): return 'ACS'
    if c.startswith('2232'): return 'Cirurgião-dentista'
    if c.startswith('3224'): return 'ASB/TSB'
    return 'Outro'

TP = {'70': 'eSF', '01': 'eSF', '76': 'eAP', '71': 'eSB', '72': 'eMulti', '73': 'eCR', '74': 'eAPP'}
REQ = {'eSF': ['Médico', 'Enfermeiro', 'Téc./aux. enfermagem'], 'eAP': ['Médico', 'Enfermeiro'], 'eSB': ['Cirurgião-dentista', 'ASB/TSB']}

def dt(s):
    try: return datetime.datetime.strptime(s, '%d/%m/%Y').date()
    except Exception: return None

def um_municipio(mun, ex):
    est = get(B + f'estabelecimentos?municipio={mun}') or []
    est = [e for e in est if e.get('atendeSus') == 'S']
    res = list(ex.map(lambda e: (e, get(B + 'estabelecimentos-equipes/' + e['id']) or []), est))
    jobs = [(e, t) for e, ts in res for t in ts]
    def pf(j):
        e, t = j
        return j, get(B + f"estabelecimentos-equipes/profissionais/{e['id']}?coMun={t['coMunicipio']}&coArea={t['coArea']}&coEquipe={t['seqEquipe']}") or []
    return list(ex.map(pf, jobs))

def main(uf, out, parte=1, total=1):
    os.makedirs(out, exist_ok=True)
    ref = datetime.date.today().isoformat()
    E, P = [], []
    t0 = time.time()
    with cf.ThreadPoolExecutor(THREADS) as ex:
        muns = municipios(uf)
        muns = muns[parte - 1::total]
        for i, mun in enumerate(muns):
            seen = set()
            for (e, t), ps in um_municipio(mun, ex):
                if t['coEquipe'] in seen: continue
                seen.add(t['coEquipe'])
                tipo = TP.get(t['tpEquipe'], 'Outra')
                c = collections.Counter(cat(p['cbo']) for p in ps)
                req = REQ.get(tipo)
                falt = [k for k in req if c[k] == 0] if req else []
                ativa = not t['dtDesativacao']
                sit = 'Desativada' if not ativa else ('Completa' if req and not falt else ('Incompleta' if req else 'Sem regra'))
                ents = [dt(p['dtEntrada']) for p in ps if dt(p['dtEntrada'] or '')]
                E.append(dict(data_ref=ref, ibge=int(mun), cnes=int(e['cnes']), estabelecimento=e['noFantasia'] or '', ine=int(t['coEquipe']), tipo=tipo,
                              tipo_cnes=t['dsEquipe'], nome_equipe=t['nomeEquipe'] or '', area=t['coArea'], dt_ativacao=t['dtAtivacao'] or '',
                              dt_desativacao=t['dtDesativacao'] or '', n_medico=c['Médico'], n_enfermeiro=c['Enfermeiro'], n_tec_enf=c['Téc./aux. enfermagem'],
                              n_acs=c['ACS'], n_dentista=c['Cirurgião-dentista'], n_asb_tsb=c['ASB/TSB'], n_outros=c['Outro'], n_total=len(ps),
                              faltando='; '.join(falt), situacao=sit, ult_entrada=max(ents).isoformat() if ents else '',
                              entradas_120d=sum(1 for x in ents if (datetime.date.today() - x).days <= 120)))
                for p in ps:
                    d = dt(p['dtEntrada'] or '')
                    P.append(dict(data_ref=ref, ibge=int(mun), ine=int(t['coEquipe']), cbo=p['cbo'], ocupacao=p['dsCbo'], categoria=cat(p['cbo']),
                                  nome=p['noProfissional'], ch_semanal=(p['chAmb'] or 0) + (p['chOutros'] or 0) + (p['chHosp'] or 0),
                                  entrada=d.isoformat() if d else ''))
            print(f'{uf} {i+1} {mun} equipes={len(E)} prof={len(P)} {int(time.time()-t0)}s', flush=True)
    for name, rows, cols in (('equipes', E, None), ('profissionais', P, None)):
        if not rows: continue
        with gzip.open(os.path.join(out, f'{uf}-{parte}_{name}.csv.gz'), 'wt', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=';'); w.writeheader(); w.writerows(rows)
    print('OK', uf, len(E), len(P))

if __name__ == '__main__':
    a = sys.argv
    main(a[1].upper(), a[2], int(a[3]) if len(a) > 3 else 1, int(a[4]) if len(a) > 4 else 1)
