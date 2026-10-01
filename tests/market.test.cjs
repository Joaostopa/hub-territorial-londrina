const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const engine=require('../docs/curitiba/market-engine.js');
const row={id:'a',cidade:'Curitiba',finalidade:'venda',preco:100000,area_m2:50};
const b=(m,records,complete=true,purpose='venda')=>({id:m+purpose,source:'VivaReal',city:'Curitiba',purpose,coverage:'bairro',observed:`2026-${m}-01T00:00:00Z`,complete,records});
test('partial coverage preserves stock; complete disappearance and reappearance revise estimates',()=>{const out=engine.replay([b('01',[row]),b('02',[],false),b('03',[]),b('04',[row])]);assert.deepEqual(out.timeline.map(t=>t.rows.length),[1,1,0,1]);assert.equal(out.exits.length,1);assert.equal(out.exits[0].reversed,'2026-04-01T00:00:00Z')});
test('rent and sale never remove one another',()=>{const out=engine.replay([b('01',[row]),b('02',[{...row,id:'rent',finalidade:'aluguel'}],true,'aluguel'),b('03',[])]);assert.equal(out.current[0].id,'rent');assert.equal(out.exits[0].finalidade,'venda')});
test('published Curitiba data retains all 414 sales and the recovered rental',()=>{const x=JSON.parse(fs.readFileSync('docs/curitiba/imoveis.json'));assert.equal(x.filter(r=>r.finalidade==='venda').length,414);assert.equal(x.filter(r=>r.finalidade==='aluguel').length,1);assert.equal(new Set(x.map(r=>r.id)).size,415)});
test('dashboard and project startup use the published data and shared filters',async()=>{
 const elements=new Map(),handlers={};function el(id){if(!elements.has(id))elements.set(id,{value:'',checked:false,innerHTML:'',textContent:'',listeners:{},addEventListener(n,f){this.listeners[n]=f},get options(){return [...this.innerHTML.matchAll(/<option[^>]*value="([^"]*)"/g)].map(m=>({value:m[1]}))}});return elements.get(id)}
 for(const [id,value] of Object.entries({purpose:'venda',scope:'neighborhood',neighborhood:'bacacheri','history-group':'month',radius:'2.5'}))el(id).value=value;
 const document={body:{dataset:{city:'Curitiba'}},getElementById:el,querySelectorAll:()=>[],addEventListener:(n,f)=>handlers[n]=f,dispatchEvent:e=>{handlers[e.type]?.()},createElement:()=>({click(){}})};
 const storage=new Map();const ctx=vm.createContext({crypto:require("node:crypto").webcrypto,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},console,document,window:{},Intl,URL,Blob,Event,setTimeout,clearTimeout,structuredClone,fetch:async path=>({ok:true,json:async()=>path==='imoveis.json'?JSON.parse(fs.readFileSync('docs/curitiba/imoveis.json')):path.startsWith('historico')?{batches:[]}:path.startsWith('empreendimentos')?JSON.parse(fs.readFileSync('docs/curitiba/empreendimentos.json')):path==='bairros.geojson'?JSON.parse(fs.readFileSync('docs/curitiba/bairros.geojson')):path==='pois.json'?{items:[]}:JSON.parse(fs.readFileSync('docs/curitiba/ibge.json'))})});ctx.window=ctx;
 for(const f of ['market-engine.js','app.js','market.js','registry.js'])vm.runInContext(fs.readFileSync('docs/curitiba/'+f,'utf8'),ctx,{filename:f});
 await new Promise(r=>setTimeout(r,50));assert.equal(vm.runInContext('selected.length',ctx),376);assert.match(el('history-metrics').innerHTML,/Vendas estimadas/);assert.match(el('project-rows').innerHTML,/Empreendimento/);
 el('scope').value='city';vm.runInContext('render()',ctx);assert.equal(vm.runInContext('selected.length',ctx),414);
 el('project-builder').value='Vectra';el('project-builder').listeners.change();assert.match(el('project-select').innerHTML,/Euro Building/);assert.doesNotMatch(el('project-select').innerHTML,/Casa Constant/);assert.match(el('official-projects').innerHTML,/Vectra/);
 el('project-builder').value='Plaenge';el('project-builder').listeners.change();assert.match(el('project-select').innerHTML,/Casa Constant/);assert.doesNotMatch(el('project-select').innerHTML,/Euro Building/);
 el('project-builder').value='';el('project-builder').listeners.change();
 el('registry-name').value='Teste <edifício>';el('registry-builder').value='Construtora Exemplo';
 el('registry-form').onsubmit({preventDefault(){}});assert.match(el('registry-status').textContent,/tipologia/);
 el('registry-types').listeners.input({target:{dataset:{typeIndex:'0',typeKey:'nome'},value:'2 quartos'}});
 el('registry-form').onsubmit({preventDefault(){}});
 assert.equal(JSON.parse(storage.get('hub-projects-v1:Curitiba'))[0].tipologias[0].nome,'2 quartos');
 assert.match(el('registry-list').innerHTML,/&lt;edifício&gt;/);
 el('registry-search').value='construtora exemplo';el('registry-search').oninput();assert.match(el('registry-list').innerHTML,/Teste/);
 vm.runInContext(fs.readFileSync('docs/curitiba/registry.js','utf8'),ctx);assert.match(el('registry-list').innerHTML,/Teste/);
 el('purpose').value='aluguel';vm.runInContext('render()',ctx);assert.equal(vm.runInContext('selected.length',ctx),1);
 });

test('new city snapshot preserves the baseline and never infers exits from partial collection',()=>{
 const baseline=JSON.parse(fs.readFileSync('docs/curitiba/imoveis.json')),h=JSON.parse(fs.readFileSync('docs/curitiba/historico.json'));
 const batches=[b('09',baseline,false),...h.batches.map((x,i)=>({...x,id:'run-'+i,city:'Curitiba',observed:x.observed_at}))];
 const result=engine.replay(batches),ids=new Set(result.current.map(r=>r.id));
 assert.ok(baseline.every(r=>ids.has(r.id)));assert.equal(result.exits.length,0);
 for(const batch of h.batches){assert.equal(batch.complete,false);assert.ok(batch.records.every(r=>r.finalidade===batch.purpose&&r.cidade==='Curitiba'&&r.preco>0));assert.equal(new Set(batch.records.map(r=>r.id)).size,batch.records.length);assert.ok(batch.records.every(r=>!r.contact_details&&!r.source_context&&!r.attributes));}
});
