// Importa exportação da execução para um lote parcial sem publicar dados de contato.
const fs=require('fs'),vm=require('vm');
const [input,observed,runId]=process.argv.slice(2);
if(!input||!Number.isFinite(Date.parse(observed))||!runId)throw Error('Uso: node scripts/import-apify-snapshot.cjs arquivo.json dataISO runID');
const els=new Map(),el=id=>{if(!els.has(id))els.set(id,{value:'',addEventListener(){}});return els.get(id)};
const ctx=vm.createContext({document:{body:{dataset:{city:'Curitiba'}},getElementById:el,querySelectorAll:()=>[]},window:{},Intl,URL,console});
vm.runInContext(fs.readFileSync('docs/curitiba/app.js','utf8').replace(/start\(\);\s*$/,''),ctx);
const raw=JSON.parse(fs.readFileSync(input));ctx.raw=raw;
const parsed=vm.runInContext('raw.map(normalizeApify)',ctx),unique=new Map();
for(let i=0;i<parsed.length;i++){const r=parsed[i];if(!r||!(r.preco>0))continue;r.data_coleta=observed;delete r.tipologias;r.data_referencia_origem='Execução Apify '+runId+'; coleta parcial';if(!(r.area_m2>0))r.area_m2=null;unique.set(r.id,r)}
const records=[...unique.values()],groups=new Map();for(const r of records){if(!groups.has(r.finalidade))groups.set(r.finalidade,[]);groups.get(r.finalidade).push(r)}
const file='docs/curitiba/historico.json',history=JSON.parse(fs.readFileSync(file));history.batches=history.batches.filter(b=>b.run_id!==runId);
for(const [purpose,rows]of groups)history.batches.push({run_id:runId,source:'Apify VIVAREAL',purpose,coverage:'Curitiba/apartamentos',observed_at:observed,complete:false,note:'Curitiba inteira. Coleta limitada por tempo/orçamento; ausências não comprovam vendas.',records:rows});
fs.writeFileSync(file,JSON.stringify(history));
const baseline=JSON.parse(fs.readFileSync('docs/curitiba/imoveis.json')),ids=new Set(baseline.map(r=>r.id));console.log(JSON.stringify({exported:raw.length,accepted:records.length,rejected:raw.length-parsed.filter(Boolean).length,newIds:records.filter(r=>!ids.has(r.id)).length,combined:new Set([...ids,...records.map(r=>r.id)]).size,neighborhoods:new Set(records.map(r=>r.bairro)).size,purpose:[...groups].map(([k,v])=>[k,v.length])}));
