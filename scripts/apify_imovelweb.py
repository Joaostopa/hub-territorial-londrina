"""Integração Apify/Imovelweb para Curitiba. Token apenas no ambiente, nunca no site."""
import argparse
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from classify_properties import clean, enrich, norm

ACTOR = 'anyxsolutions~imovelweb-scraper'
SEARCH = {'venda':'https://www.imovelweb.com.br/apartamentos-venda-curitiba-pr.html',
          'aluguel':'https://www.imovelweb.com.br/apartamentos-aluguel-curitiba-pr.html'}


def number(value):
    if value is None or isinstance(value,bool):return None
    if isinstance(value,(int,float)):return value if math.isfinite(value) else None
    m=re.search(r'\d[\d.,]*',str(value))
    if not m:return None
    s=m[0]
    if ',' in s:s=s.replace('.','').replace(',','.')
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+',s):s=s.replace('.','')
    try:return float(s)
    except ValueError:return None


def normalize(item, purpose, observed, catalog):
    url=str(item.get('url') or '')
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ['www.imovelweb.com.br','imovelweb.com.br']:return None
    if norm(item.get('city'))!='curitiba' or norm(item.get('state')) not in ['pr','parana']:return None
    # Cards de busca sem cidade explícita não viram anúncios válidos por suposição.
    price=number(item.get('price'));area=number(item.get('area_m2') or item.get('area'))
    if not price or price<=0 or item.get('currency','BRL')!='BRL':return None
    text=norm(str(item.get('title',''))+' '+str(item.get('description','')))
    if purpose=='venda' and re.search(r'\b(?:para alugar|para locacao|aluguel mensal)\b',text):return None
    if purpose=='aluguel' and re.search(r'\b(?:a venda|para venda)\b',text):return None
    canonical=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
    external=hashlib.sha256(canonical.encode()).hexdigest()[:24]
    row=dict(id=f'IMOVELWEB:{external}:{purpose}',id_externo=external,fonte='Apify IMOVELWEB',
             cidade='Curitiba',finalidade=purpose,tipo='apartamento',titulo=clean(item.get('title')),
             bairro=clean(item.get('neighborhood')),endereco=clean(item.get('street')),url=canonical,
             preco=price,area_m2=area if area and area>0 else None,quartos=number(item.get('bedrooms')),
             latitude=None,longitude=None,geo_precisao='Sem coordenadas',data_coleta=observed,
             empreendimento='',construtora='',data_referencia_origem='Coleta parcial Imovelweb')
    return enrich(row,item,catalog)


def api(path, token, payload=None):
    request=urllib.request.Request('https://api.apify.com/v2/'+path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)
    except urllib.error.HTTPError as exc:
        # Não imprimir corpo/URL que possa conter credenciais.
        raise RuntimeError(f'Apify respondeu HTTP {exc.code}. Confira saldo, acesso e configuração do Actor.') from None


def run_actor(token, payload, budget):
    query=urllib.parse.urlencode({'maxTotalChargeUsd':budget,'timeout':1800})
    run=api(f'acts/{ACTOR}/runs?{query}',token,payload)['data']
    print(json.dumps({'run_id':run['id'],'status':run['status']}),flush=True)
    while run['status'] in ['READY','RUNNING','TIMING-OUT','ABORTING']:
        time.sleep(10)
        run=api('actor-runs/'+run['id'],token)['data']
    items=[];offset=0
    while True:
        page=api(f"datasets/{run['defaultDatasetId']}/items?format=json&clean=true&offset={offset}&limit=1000",token)
        items.extend(page)
        if len(page)<1000:break
        offset+=len(page)
    return items,run


def collect(token, purpose, limit, budget):
    payload={'startUrls':[{'url':SEARCH[purpose]}],'maxItems':limit,
             'proxyConfiguration':{'useApifyProxy':True,'apifyProxyGroups':['RESIDENTIAL'],'apifyProxyCountry':'BR'}}
    items,run=run_actor(token,payload,budget)
    # Busca retorna cartões; detalhe é necessário para confirmar cidade/UF e ler descrição.
    details=[x for x in items if x.get('itemType')=='property']
    urls=[]
    for x in items:
        u=str(x.get('url') or '');parsed=urllib.parse.urlsplit(u)
        if x.get('itemType')=='search' and parsed.scheme=='https' and parsed.hostname in ['www.imovelweb.com.br','imovelweb.com.br'] and '/propriedades/' in parsed.path and u not in urls:
            urls.append(u)
    if urls:
        charged=run.get('usageTotalUsd')
        if charged is None:raise RuntimeError('Custo da busca indisponível; etapa de detalhes não iniciada para respeitar orçamento.')
        remaining=round(budget-float(charged),6)
        if remaining<=0:raise RuntimeError('Orçamento consumido na busca; detalhes não iniciados. Execução preservada na Apify.')
        payload.update(startUrls=[{'url':u} for u in urls[:limit]],maxItems=1)
        extra,last=run_actor(token,payload,remaining)
        details.extend(extra)
        last['searchRunId']=run['id'];last['usageTotalUsd']=float(charged)+float(last.get('usageTotalUsd') or 0)
        return details,last
    return items,run


def import_items(items, purpose, run_id, observed, history_path, catalog_path):
    catalog=json.loads(catalog_path.read_text())['projects']
    parsed=[normalize(x,purpose,observed,catalog) for x in items]
    records=list({x['id']:x for x in parsed if x}.values())
    if not records:raise ValueError('Nenhum detalhe válido para Curitiba. Histórico preservado; obtenha páginas de detalhes com cidade/UF explícitas.')
    history=json.loads(history_path.read_text())
    history['batches']=[b for b in history['batches'] if b.get('run_id')!=run_id]
    history['batches'].append(dict(run_id=run_id,source='Apify IMOVELWEB',purpose=purpose,
        coverage='Curitiba/apartamentos/Imovelweb',observed_at=observed,complete=False,
        note='Coleta parcial; não infere vendas por desaparecimento. Pode haver imóveis repetidos entre portais.',records=records))
    temp=history_path.with_suffix('.tmp');temp.write_text(json.dumps(history,ensure_ascii=False));temp.replace(history_path)
    return {'lidos':len(items),'aceitos':len(records),'rejeitados':sum(x is None for x in parsed),'duplicados':sum(x is not None for x in parsed)-len(records)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--purpose',choices=SEARCH,default='venda')
    p.add_argument('--input',type=Path,help='Importar exportação local sem iniciar execução paga')
    p.add_argument('--run-id');p.add_argument('--observed-at')
    p.add_argument('--collect',action='store_true')
    p.add_argument('--limit',type=int,default=200)
    p.add_argument('--max-total-charge-usd',type=float)
    p.add_argument('--history',type=Path,default=Path('docs/curitiba/historico.json'))
    p.add_argument('--catalog',type=Path,default=Path('docs/curitiba/empreendimentos.json'))
    args=p.parse_args()
    if args.collect:
        if args.input or not args.max_total_charge_usd or not 0<args.max_total_charge_usd<=100 or not 1<=args.limit<=20000:p.error('Informe limite de resultados e teto de custo explícitos; não combine --collect e --input.')
        token=os.environ.get('APIFY_TOKEN')
        if not token:p.error('APIFY_TOKEN ausente no ambiente de execução.')
        items,run=collect(token,args.purpose,args.limit,args.max_total_charge_usd)
        run_id=run['id'];observed=run.get('finishedAt') or datetime.now(timezone.utc).isoformat()
        print(json.dumps({'run_id':run_id,'status':run['status'],'custo_usd':run.get('usageTotalUsd')}))
    else:
        if not args.input or not args.run_id or not args.observed_at:p.error('Use --input, --run-id e --observed-at, ou --collect.')
        items=json.loads(args.input.read_text());run_id=args.run_id;observed=args.observed_at
    date=datetime.fromisoformat(observed.replace('Z','+00:00'))
    if date.tzinfo is None or date>datetime.now(timezone.utc):raise ValueError('Data de coleta deve ter fuso e não estar no futuro.')
    print(json.dumps(import_items(items,args.purpose,run_id,observed,args.history,args.catalog),ensure_ascii=False))


if __name__=='__main__':main()
