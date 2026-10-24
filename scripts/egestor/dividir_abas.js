// Divide cada planilha "download-pagamento" (24 abas, ~18 MB) em uma planilha pequena por aba:
//   <saida>/<Aba>/download-pagamento-01-MM-AAAA.xlsx   (ex.: eSF/, ACS/, Academia_da_Saude/)
// Assim cada tabela do Power BI baixa só a aba que usa (~1 MB em vez de 18 MB por mês).
// Uso: node dividir_abas.js <pasta_com_planilhas_completas> <saida>
const fs = require('fs'), path = require('path'), crypto = require('crypto'), XLSX = require('xlsx');
const [ent, out] = [process.argv[2], process.argv[3]];
const slug = n => n.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
fs.mkdirSync(out, { recursive: true });
const arqs = fs.readFileSync(path.join(ent, '_arquivos.txt'), 'utf8').split('\n').map(s => s.trim()).filter(s => s.endsWith('.xlsx'));
const fHash = path.join(out, '_hash.json');
const hashes = fs.existsSync(fHash) ? JSON.parse(fs.readFileSync(fHash, 'utf8')) : {};
let novos = 0;
for (const nome of arqs) {
  const buf = fs.readFileSync(path.join(ent, nome));
  const h = crypto.createHash('sha256').update(buf).digest('hex');
  if (hashes[nome] === h && fs.existsSync(path.join(out, 'Resumo', nome))) { console.log(nome, 'sem mudança'); continue; }
  const wb = XLSX.read(buf, { cellStyles: false });
  for (const aba of wb.SheetNames) {
    const nw = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(nw, wb.Sheets[aba], aba);
    fs.mkdirSync(path.join(out, slug(aba)), { recursive: true });
    XLSX.writeFile(nw, path.join(out, slug(aba), nome), { compression: true });
  }
  hashes[nome] = h; novos++;
  console.log(nome, '->', wb.SheetNames.length, 'abas');
}
for (const dir of fs.readdirSync(out)) {   // remove parcelas que saíram da janela
  const pd = path.join(out, dir);
  if (fs.statSync(pd).isDirectory()) for (const f of fs.readdirSync(pd)) if (!arqs.includes(f)) fs.unlinkSync(path.join(pd, f));
}
for (const k of Object.keys(hashes)) if (!arqs.includes(k)) delete hashes[k];
fs.writeFileSync(fHash, JSON.stringify(hashes, null, 1));
fs.writeFileSync(path.join(out, '_arquivos.txt'), arqs.join('\n') + '\n');
console.log(`${arqs.length} parcelas, ${novos} divididas agora`);
