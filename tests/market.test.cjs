const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const engine=require('../docs/curitiba/market-engine.js');
const row={id:'a',cidade:'Curitiba',finalidade:'venda',preco:100000,area_m2:50};
const b=(m,records,complete=true,purpose='venda')=>({id:m+purpose,source:'VivaReal',city:'Curitiba',purpose,coverage:'bairro',observed:`2026-${m}-01T00:00:00Z`,complete,records});
test('partial coverage preserves stock; complete disappearance and reappearance revise estimates',()=>{const out=engine.replay([b('01',[row]),b('02',[],false),b('03',[]),b('04',[row])]);assert.deepEqual(out.timeline.map(t=>t.rows.length),[1,1,0,1]);assert.equal(out.exits.length,1);assert.equal(out.exits[0].reversed,'2026-04-01T00:00:00Z')});
test('rent and sale never remove one another',()=>{const out=engine.replay([b('01',[row]),b('02',[{...row,id:'rent',finalidade:'aluguel'}],true,'aluguel'),b('03',[])]);assert.equal(out.current[0].id,'rent');assert.equal(out.exits[0].finalidade,'venda')});
test('published Curitiba data retains all 414 sales and the recovered rental',()=>{const x=JSON.parse(fs.readFileSync('docs/curitiba/imoveis.json'));assert.equal(x.filter(r=>r.finalidade==='venda').length,414);assert.equal(x.filter(r=>r.finalidade==='aluguel').length,1);assert.equal(new Set(x.map(r=>r.id)).size,415)});
test('dashboard and project startup use the published data and shared filters',async()=>{
 const elements=new Map(),handlers={};function el(id){if(!elements.has(id))elements.set(id,{value:'',checked:false,innerHTML:'',textContent:'',addEventListener(){},get options(){return [...this.innerHTML.matchAll(/<option[^>]*value="([^"]*)"/g)].map(m=>({value:m[1]}))}});return elements.get(id)}
 for(const [id,value] of Object.entries({purpose:'venda',scope:'neighborhood',neighborhood:'bacacheri','history-group':'month',radius:'2.5'}))el(id).value=value;
 const document={body:{dataset:{city:'Curitiba'}},getElementById:el,querySelectorAll:()=>[],addEventListener:(n,f)=>handlers[n]=f,dispatchEvent:e=>{handlers[e.type]?.()},createElement:()=>({click(){}})};
 const ctx=vm.createContext({console,document,window:{},Intl,URL,Blob,Event,setTimeout,clearTimeout,structuredClone,fetch:async path=>({ok:true,json:async()=>path==='imoveis.json'?JSON.parse(fs.readFileSync('docs/curitiba/imoveis.json')):path.startsWith('historico')?{batches:[]}:path==='bairros.geojson'?JSON.parse(fs.readFileSync('docs/curitiba/bairros.geojson')):path==='pois.json'?{items:[]}:JSON.parse(fs.readFileSync('docs/curitiba/ibge.json'))})});ctx.window=ctx;
 for(const f of ['market-engine.js','app.js','market.js'])vm.runInContext(fs.readFileSync('docs/curitiba/'+f,'utf8'),ctx,{filename:f});
 await new Promise(r=>setTimeout(r,50));assert.equal(vm.runInContext('selected.length',ctx),376);assert.match(el('history-metrics').innerHTML,/Vendas estimadas/);assert.match(el('project-rows').innerHTML,/Empreendimento/);
 el('scope').value='city';vm.runInContext('render()',ctx);assert.equal(vm.runInContext('selected.length',ctx),414);
 el('purpose').value='aluguel';vm.runInContext('render()',ctx);assert.equal(vm.runInContext('selected.length',ctx),1);
 });
