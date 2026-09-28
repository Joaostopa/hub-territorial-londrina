/* Historical replay: complete observations alone may establish absence. */
(function(root){
'use strict';
const key=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toLowerCase();
const unit=r=>r.empreendimento&&r.torre&&r.unidade?JSON.stringify([key(r.cidade),key(r.empreendimento),key(r.torre),key(r.unidade),r.finalidade]):r.id;
function replay(batches){const active=new Map(),seen=new Map(),exits=[],timeline=[];
 for(const b of [...batches].sort((a,b)=>a.observed.localeCompare(b.observed)||a.id.localeCompare(b.id))){
 const scope=JSON.stringify([b.source,b.city,b.purpose,b.coverage]),previous=seen.get(scope)||new Map();seen.set(scope,previous);const present=new Set();
 for(const raw of b.records){const r={...raw,data_coleta:b.observed};present.add(r.id);active.set(r.id,r);previous.set(r.id,r);for(const e of exits)if(!e.reversed&&e.unit===unit(r))e.reversed=b.observed;}
 const removed=[];if(b.complete){for(const [id,r] of previous)if(!present.has(id)){previous.delete(id);const latest=active.get(id);if(latest&&latest.data_coleta<=r.data_coleta){removed.push(latest);active.delete(id)}}const live=new Set([...active.values()].map(unit));for(const r of removed)if(!live.has(unit(r))&&!exits.some(e=>!e.reversed&&e.unit===unit(r)))exits.push({...r,unit:unit(r),detected:b.observed,lastSeen:r.data_coleta,reversed:null,batchId:b.id});}
 timeline.push({date:b.observed,rows:[...active.values()]});}
 return {current:[...active.values()],exits,timeline};}
function period(date,weekly){if(!weekly)return date.slice(0,7);const d=new Date(date),day=d.getUTCDay()||7;d.setUTCDate(d.getUTCDate()-day+1);return d.toISOString().slice(0,10)}
root.MarketEngine={replay,period,unit};if(typeof module!=='undefined')module.exports=root.MarketEngine;
})(typeof window==='undefined'?globalThis:window);
