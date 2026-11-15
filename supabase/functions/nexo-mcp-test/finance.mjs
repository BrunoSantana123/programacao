// Mantém a mesma composição de receitas, despesas e reservas do NEXO existente.
const groups = {income:{uber:'Uber',noventa:'99',particular:'Particulares'},expense:{recharge:'Recarga',fuel:'Combustível',food:'Alimentação',other:'Outras despesas'},reserve:{reserve:'Manutenção'}};
const types = {income:'receita',expense:'despesa',reserve:'reserva',release:'resgate'};
function cents(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw Error('Valor existente inválido; consulta não confirmada.');
  const result = Math.round(numeric * 100);
  if (!Number.isSafeInteger(result)) throw Error('Valor fora do intervalo seguro.');
  return result;
}
function date(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
}
export function queryArguments(raw, movements=false) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw Error('Argumentos inválidos.');
  const keys = movements ? ['data_inicio','data_fim','tipo','categoria','pagina','limite'] : ['data_inicio','data_fim'];
  if (Object.keys(raw).some(k => !keys.includes(k))) throw Error('Argumento não permitido.');
  for (const key of ['data_inicio','data_fim']) if (raw[key] !== undefined && !date(raw[key])) throw Error('Data inválida.');
  if (raw.data_inicio && raw.data_fim && raw.data_inicio > raw.data_fim) throw Error('Período inválido.');
  if (raw.tipo !== undefined && !Object.values(types).includes(raw.tipo)) throw Error('Tipo inválido.');
  if (raw.categoria !== undefined && (typeof raw.categoria !== 'string' || !raw.categoria.trim() || raw.categoria.length > 120)) throw Error('Categoria inválida.');
  for (const [key,max] of [['pagina',100000],['limite',50]]) if (raw[key] !== undefined && (!Number.isInteger(raw[key]) || raw[key] < 1 || raw[key] > max)) throw Error('Paginação inválida.');
  return {...raw, ...(movements ? {pagina:raw.pagina??1,limite:raw.limite??20}: {})};
}
function movements(document, args) {
  if (!document || typeof document !== 'object' || Array.isArray(document)) throw Error('Documento financeiro inválido.');
  if (Object.keys(document).length === 0) return [];
  if (!Array.isArray(document.entries)) throw Error('Histórico financeiro incompatível.');
  const result=[];
  for (const entry of document.entries) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) throw Error('Lançamento existente inválido.');
    if ((args.data_inicio || args.data_fim) && !date(entry.date)) throw Error('Histórico contém data inválida; período não confirmado.');
    if (args.data_inicio && entry.date < args.data_inicio || args.data_fim && entry.date > args.data_fim) continue;
    const add=(type,category,value)=>{
      const amount=cents(value);
      if (!amount || args.tipo && types[type] !== args.tipo || args.categoria && String(category).trim().toLocaleLowerCase('pt-BR') !== args.categoria.trim().toLocaleLowerCase('pt-BR')) return;
      result.push({id:typeof entry.id==='string'?entry.id:null,data:date(entry.date)?entry.date:null,tipo:types[type],categoria:String(category??'Outros').slice(0,120),valor_centavos:amount,descricao:String(entry.description??'').slice(0,200)});
    };
    for (const [type,group] of Object.entries(groups)) for (const [key,category] of Object.entries(group)) if (Object.hasOwn(entry,key)) add(type,category,entry[key]);
    if (Object.hasOwn(types,entry.type) && Object.hasOwn(entry,'amount')) add(entry.type,entry.category??'Outros',entry.amount);
  }
  return result;
}
export function balance(document,args) {
  const totals={receita:0,despesa:0,reserva:0,resgate:0};
  for(const item of movements(document,args)) {
    totals[item.tipo]+=item.valor_centavos;
    if (!Number.isSafeInteger(totals[item.tipo])) throw Error('Saldo fora do intervalo seguro.');
  }
  const saldo=totals.receita-totals.despesa-totals.reserva+totals.resgate;
  if(!Number.isSafeInteger(saldo)) throw Error('Saldo fora do intervalo seguro.');
  return {moeda:'BRL',data_inicio:args.data_inicio??null,data_fim:args.data_fim??null,receitas_centavos:totals.receita,despesas_centavos:totals.despesa,reservas_centavos:totals.reserva,resgates_centavos:totals.resgate,saldo_centavos:saldo,criterio:'Receitas menos despesas e reservas, mais resgates, conforme os lançamentos do NEXO; não é saldo bancário.'};
}
export function listMovements(document,args) {
  const items=movements(document,args).sort((a,b)=>(b.data??'').localeCompare(a.data??''));
  const start=(args.pagina-1)*args.limite;
  return {moeda:'BRL',pagina:args.pagina,limite:args.limite,total:items.length,tem_mais:start+args.limite<items.length,movimentacoes:items.slice(start,start+args.limite)};
}
export function receipt(saved,body) {
  const e=saved?.lancamento;
  if(!e || typeof e.amount!=='number' || typeof saved.repetido!=='boolean' || e.id!==body.p_id || e.type!==(body.p_tipo==='receita'?'income':'expense') || e.date!==body.p_data || e.category!==body.p_categoria || e.description!==body.p_descricao || cents(e.amount)!==body.p_centavos) throw Error('Recibo divergente; gravação não confirmada.');
  return {lancamento:{id:e.id,type:e.type,date:e.date,category:e.category,description:e.description,amount:e.amount},repetido:saved.repetido};
}
