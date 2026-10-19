"""Extrai do CNES (cnes.datasus.gov.br) as equipes por INE e seus profissionais de uma UF inteira.
Uso: python scripts/extrair.py RO saida/ [parte total]   ex.: SP saida/ 2 6
Gera saida/RO_equipes.csv.gz e saida/RO_profissionais.csv.gz (separador ;, UTF-8)."""
import json, sys, time, csv, gzip, os, datetime, collections, urllib.request
import concurrent.futures as cf

H = {'Referer': 'https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp', 'User-Agent': 'Mozilla/5.0 (aps-cnes-ine)'}
B = 'https://cnes.datasus.gov.br/services/'
THREADS = int(os.environ.get('THREADS', '8'))
BUDGET = int(os.environ.get('BUDGET_MIN', '280')) * 60   # tempo máximo da parte; depois grava o que tiver
MUN_MAX = 900   # segundos máximos por município (respostas travadas do CNES são descartadas)

def get(url, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30)
            b = r.read()
            if b[:2] == b'\x1f\x8b': b = gzip.decompress(b)
            return json.loads(b) if b else []
        except Exception:
            time.sleep(2 * (i + 1))
    return None

UFC = {'RO': 11, 'AC': 12, 'AM': 13, 'RR': 14, 'PA': 15, 'AP': 16, 'TO': 17, 'MA': 21, 'PI': 22, 'CE': 23, 'RN': 24, 'PB': 25, 'PE': 26, 'AL': 27,
       'SE': 28, 'BA': 29, 'MG': 31, 'ES': 32, 'RJ': 33, 'SP': 35, 'PR': 41, 'SC': 42, 'RS': 43, 'MS': 50, 'MT': 51, 'GO': 52, 'DF': 53}

def municipios(uf):
    # 1º: lista do próprio CNES; 2º: API do IBGE (às vezes não responde para o GitHub)
    for _ in range(3):
        d = get(B + f'municipios?estado={UFC[uf]}')
        if d:
            if uf == 'DF': return ['530010']   # o CNES lista as regiões administrativas; o município IBGE é só Brasília
            return sorted(k for k in map(str, d) if k[:2] == str(UFC[uf]) and k[2:] != '0000')
    d = get(f'https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios', tries=8) or []
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

def _pmap(fn, items, deadline):
    # executa em paralelo e descarta o que não terminar até o prazo (evita travar a parte inteira)
    ex = cf.ThreadPoolExecutor(THREADS)
    fs = [ex.submit(fn, x) for x in items]
    done, pend = cf.wait(fs, timeout=max(1, deadline - time.time()))
    ex.shutdown(wait=False, cancel_futures=True)
    return [f.result() for f in fs if f in done and f.exception() is None], len(pend)

def um_municipio(mun):
    dl = time.time() + MUN_MAX
    est = get(B + f'estabelecimentos?municipio={mun}') or []
    est = [e for e in est if e.get('atendeSus') == 'S']
    res, p1 = _pmap(lambda e: (e, get(B + 'estabelecimentos-equipes/' + e['id']) or []), est, dl)
    jobs = [(e, t) for e, ts in res for t in ts]
    def pf(j):
        e, t = j
        return j, get(B + f"estabelecimentos-equipes/profissionais/{e['id']}?coMun={t['coMunicipio']}&coArea={t['coArea']}&coEquipe={t['seqEquipe']}") or []
    out, p2 = _pmap(pf, jobs, dl)
    return out, p1 + p2

def main(uf, out, parte=1, total=1):
    os.makedirs(out, exist_ok=True)
    ref = datetime.date.today().isoformat()
    E, P = [], []
    t0 = time.time()
    muns = municipios(uf)[parte - 1::total]
    falhas = []
    if True:
        for i, mun in enumerate(muns):
            if time.time() - t0 > BUDGET:
                falhas += muns[i:]
                print(f'tempo esgotado: {len(muns) - i} municípios ficaram de fora', flush=True)
                break
            seen = set()
            res, pend = um_municipio(mun)
            if pend: falhas.append(mun)
            for (e, t), ps in res:
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
            print(f'{uf} {i+1}/{len(muns)} {mun} equipes={len(E)} prof={len(P)} {int(time.time()-t0)}s' + (f' ({pend} consultas sem resposta)' if pend else ''), flush=True)
    for name, rows, cols in (('equipes', E, None), ('profissionais', P, None)):
        if not rows: continue
        with gzip.open(os.path.join(out, f'{uf}-{parte}_{name}.csv.gz'), 'wt', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=';'); w.writeheader(); w.writerows(rows)
    if falhas: print('municípios incompletos:', ' '.join(falhas))
    print('OK', uf, len(E), len(P), flush=True)
    sys.stdout.flush()
    os._exit(0 if E else 1)   # _exit: não espera conexões travadas do CNES

if __name__ == '__main__':
    a = sys.argv
    main(a[1].upper(), a[2], int(a[3]) if len(a) > 3 else 1, int(a[4]) if len(a) > 4 else 1)
