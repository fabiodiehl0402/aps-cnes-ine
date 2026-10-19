// Gera as planilhas "download-pagamento" do e-Gestor (Relatórios Públicos da APS -> Financiamento APS)
// exatamente como o botão "Baixar Excel" do site, a partir da API pública relatorioaps-prd.saude.gov.br.
// Uso: node gerar_pagamento.js <pasta_saida> [qtde_parcelas=12]
const fs = require('fs'), path = require('path'), crypto = require('crypto'), XLSX = require('xlsx');
const API = 'https://relatorioaps-prd.saude.gov.br';
const SITE = 'https://relatorioaps.saude.gov.br/';
const out = process.argv[2] || 'saida';
const N = parseInt(process.argv[3] || '12');

async function get(url, tipo = 'json', tentativas = 5) {   // tipo 'raw' devolve o texto da resposta
  for (let i = 1; i <= tentativas; i++) {
    try {
      const r = await fetch(url, { headers: { 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (aps-cnes-ine)' }, signal: AbortSignal.timeout(300000) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return tipo === 'json' ? await r.json() : await r.text();  // json ou texto
    } catch (e) {
      console.log(`  tentativa ${i} falhou (${e.message}) ${url}`);
      if (i === tentativas) throw e;
      await new Promise(s => setTimeout(s, 5000 * i));
    }
  }
}

// --- geradores de abas: copiados do próprio site (assim as colunas acompanham mudanças do e-Gestor) ---
async function codigoGeradores() {
  try {
    const html = await get(SITE, 'text');
    const main = html.match(/src="(main\.[a-z0-9]+\.js)"/)[1];
    const js = await get(SITE + main, 'text');
    const a = js.indexOf('class Ei{'), b = js.indexOf('RTe=(()=>{');
    if (a < 0 || b < 0 || b < a) throw new Error('marcadores não encontrados');
    console.log('geradores lidos do site (' + main + ')');
    return js.slice(a, b).replace(/,\s*$/, '');
  } catch (e) {
    console.log('usando cópia local dos geradores: ' + e.message);
    return fs.readFileSync(path.join(__dirname, 'geradores_pagamento.js'), 'utf8');
  }
}

const MESES = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];
const kn = { converteParaValorFormatado: v => MESES[parseInt(String(v).slice(4, 6)) - 1] + '/' + String(v).slice(0, 4) };
const di = { formataNuParcela: v => parseInt(String(v).substring(4, 6)) + '/12' };
class Ze { aplicaACelula(ws, c) { if (ws[c]) ws[c].z = '"R$ "#,##0.00_);"-R$ "#,##0.00'; } }
class Dx { constructor(n) { this.nome = n; this.colunas = []; } addColuna(nome, celulas, fmt) { this.colunas.push({ nome, celulas, formatacoes: fmt || [] }); } }
const ae = () => null;

function geradores(codigo) {
  const nomes = [...codigo.matchAll(/(?:let |,)(\w+)=\(\(\)=>\{class t extends Ei/g)].map(m => m[1]);
  const f = new Function('Dx', 'Ze', 'kn', 'di', 'ae', codigo.replace(/^class Ei/, 'class Ei') + `;return {Ei, lista:[${nomes.join(',')}]};`);
  return f(Dx, Ze, kn, di, ae).lista.map(C => new C());
}

function resumo(e) {
  const r = new Dx('Resumo');
  r.addColuna('Comp. CNES', e.map(a => kn.converteParaValorFormatado(a.nuCompCnes)));
  r.addColuna('Parcela', e.map(a => di.formataNuParcela(a.nuParcela)));
  r.addColuna('Plano Orcamentário', e.map(a => a.dsPlanoOrcamentario));
  r.addColuna('Gestão', e.map(a => a.dsEsferaAdministrativa));
  for (const [n, k] of [['Valor Integral', 'vlIntegral'], ['Ajuste', 'vlAjuste'], ['Desconto', 'vlDesconto'], ['Valor efetivo de repasse', 'vlEfetivoRepasse'],
    ['Valor da Implantação', 'vlImplantacao'], ['Ajuste da Implantação', 'vlAjusteImplantacao'], ['Desconto da Implantação', 'vlDescontoImplantacao'], ['Valor total da implantação', 'vlTotalImplantacao']])
    r.addColuna(n, e.map(a => a[k]), [new Ze()]);
  return r;
}

function planilha(sheet) {  // mesmo layout do site: cabeçalho na linha 1, dados a partir da linha 2
  const ws = XLSX.utils.json_to_sheet([]);
  sheet.colunas.forEach((col, c) => {
    XLSX.utils.sheet_add_aoa(ws, [[col.nome]], { origin: XLSX.utils.encode_cell({ c, r: 0 }) });
    XLSX.utils.sheet_add_aoa(ws, col.celulas.map(v => [v]), { origin: XLSX.utils.encode_cell({ c, r: 1 }) });
    col.formatacoes.forEach(f => col.celulas.forEach((_, i) => f.aplicaACelula(ws, XLSX.utils.encode_cell({ c, r: i + 1 }))));
  });
  return ws;
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const gens = geradores(await codigoGeradores());
  console.log('abas:', ['Resumo', ...gens.map(g => g.getNome())].join(', '));
  const anos = await get(API + '/data/anos');
  let parcelas = [];
  for (const a of anos) parcelas = parcelas.concat(await get(API + '/data/parcelas?ano=' + a));
  parcelas = [...new Set(parcelas)].sort().reverse().slice(0, N).sort();
  console.log('parcelas:', parcelas.join(' '));
  // só regrava a planilha de uma parcela quando os dados dela mudaram (evita encher o repositório)
  const fHash = path.join(out, '_hash.json');
  const hashes = fs.existsSync(fHash) ? JSON.parse(fs.readFileSync(fHash, 'utf8')) : {};
  const feitos = [];
  let novos = 0;
  for (const p of parcelas) {
    const t0 = Date.now();
    const nome = `download-pagamento-01-${p.slice(4, 6)}-${p.slice(0, 4)}.xlsx`;   // dia 01 + mês/ano da parcela (o Power BI lê mês e ano do nome)
    const txt = await get(`${API}/financiamento/pagamento?unidadeGeografica=MUNICIPIO&nuParcelaInicio=${p}&nuParcelaFim=${p}&tipoRelatorio=COMPLETO`, 'text');
    const d = JSON.parse(txt);
    if (!d.pagamentos || d.pagamentos.length < 5000) { console.log(`parcela ${p}: só ${d.pagamentos?.length || 0} municípios — ignorada`); continue; }
    const h = crypto.createHash('sha256').update(JSON.stringify({ r: d.resumosPlanosOrcamentarios, p: d.pagamentos })).digest('hex');
    if (hashes[p] === h && fs.existsSync(path.join(out, nome))) { feitos.push(nome); console.log(`parcela ${p}: sem mudança`); continue; }
    hashes[p] = h; novos++;
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, planilha(resumo(d.resumosPlanosOrcamentarios)), 'Resumo');
    for (const g of gens) XLSX.utils.book_append_sheet(wb, planilha(g.geraSheet(d.pagamentos)), g.getNome());
    XLSX.writeFile(wb, path.join(out, nome), { compression: true });
    feitos.push(nome);
    console.log(`parcela ${p}: ${d.pagamentos.length} municípios -> ${nome} (${Math.round((Date.now() - t0) / 1000)}s)`);
  }
  if (!feitos.length) { console.log('ERRO: nenhuma parcela gerada'); process.exit(1); }
  for (const f of fs.readdirSync(out)) if (f.startsWith('download-pagamento-') && !feitos.includes(f)) fs.unlinkSync(path.join(out, f));
  fs.writeFileSync(fHash, JSON.stringify(hashes, null, 1));
  fs.writeFileSync(path.join(out, '_arquivos.txt'), feitos.join('\n') + '\n');
  console.log(`${feitos.length} parcelas publicadas, ${novos} novas ou alteradas`);
  fs.writeFileSync(path.join(out, 'ultima_atualizacao.txt'), new Date().toISOString().slice(0, 16) + 'Z\n');
})().catch(e => { console.error(e); process.exit(1); });
