"""Piloto Curitiba: API Apify, histórico imutável, endereço e exportação web.
Usa apenas a biblioteca padrão. Tokens permanecem no .env local.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACTOR = 'jungle_synthesizer~brazil-vivareal-zap-imoveis-scraper'
API = 'https://api.apify.com/v2'
CENTER = (-25.4008, -49.2281)  # centro inicial de visualização, nunca posição de imóvel
IBGE = 'https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/variaveis/93?localidades=N6%5B4106902%5D'

def env():
    p = ROOT / '.env'
    if p.exists():
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if re.fullmatch(r'[A-Z_][A-Z0-9_]*', key.strip()):
                    os.environ.setdefault(key.strip(), value.strip().strip('\"\''))

def now():
    return datetime.now(timezone.utc).isoformat()

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s or '')) if unicodedata.category(c) != 'Mn').lower().strip()

def num(s):
    if s is None or isinstance(s, bool) or s == '':
        return None
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def clean(s, limit=350):
    s = re.sub(r'<[^>]*>', '', str(s or ''))
    s = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[contato omitido]', s)
    s = re.sub(r'(?:\+?55\s*)?\(?\d{2}\)?[\s.-]*\d{4,5}[\s.-]*\d{4}', '[contato omitido]', s)
    return s[:limit]

def valid_geo(lat, lon):
    lat, lon = num(lat), num(lon)
    return lat is not None and lon is not None and -25.7 < lat < -25.15 and -49.6 < lon < -49.0

def timestamp(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if d.tzinfo is None or d.year < 2000 or d.timestamp() > time.time() + 86400:
            raise ValueError()
        return d.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        raise ValueError('data_coleta inválida') from None

def stage(x):
    text = clean(x.get('title', ''), 2000) + '. ' + clean(x.get('description', ''), 2000)
    n = norm(text)
    # Não usa USED ou DEVELOPMENT como prova de entrega; não interpreta data futura.
    found = []
    for label, pattern in [('Na planta', r'\bna planta\b'), ('Em construção', r'\bem construcao\b|\bem obras\b'), ('Pronto', r'\bpronto para morar\b|\bpronto para ocupacao\b|\bobra concluida\b')]:
        match = re.search(pattern, n)
        if match and not re.search(r'(nao|ainda nao)\s+(esta\s+)?$', n[max(0,match.start()-20):match.start()]):
            found.append((label, clean(text[max(0, match.start()-20):match.end()+50], 120)))
    if len(found) == 1:
        return found[0][0], 'Texto do anúncio; requer conferência', found[0][1]
    return 'Não informado', 'Sem evidência ou texto ambíguo', ''

def normalize(x):
    if not isinstance(x, dict):
        raise ValueError('registro não é objeto')
    if norm(x.get('address_city')) != 'curitiba' or str(x.get('address_state_acronym', '')).upper() != 'PR':
        raise ValueError('fora de Curitiba/PR')
    if x.get('property_type') != 'APARTMENT':
        raise ValueError('não é apartamento')
    portal, business = x.get('portal'), x.get('business')
    if portal not in ('VIVAREAL','ZAP') or business not in ('SALE','RENTAL') or not x.get('listing_id'):
        raise ValueError('portal/finalidade/identificador inválido')
    if x.get('price_currency') not in (None, '', 'BRL'):
        raise ValueError('moeda diferente de BRL')
    if business == 'RENTAL' and x.get('rental_period') != 'MONTHLY':
        raise ValueError('aluguel não mensal')
    url = urllib.parse.urlsplit(str(x.get('url', '')))
    domain = 'zapimoveis.com.br' if portal == 'ZAP' else 'vivareal.com.br'
    if url.scheme != 'https' or not url.hostname or not (url.hostname == domain or url.hostname.endswith('.'+domain)):
        raise ValueError('URL inválida')
    lat, lon = num(x.get('latitude')), num(x.get('longitude'))
    precision = 'Portal aproximada'
    if not valid_geo(lat, lon):
        lat = lon = None
        precision = 'Sem coordenadas'
    estate_stage, origin, evidence = stage(x)
    positive = lambda key: num(x.get(key)) if (num(x.get(key)) or 0) > 0 else None
    return dict(id=f'{portal}:{x["listing_id"]}:{business}', grupo_id=f'{x["listing_id"]}:{business}',
        id_externo=str(x['listing_id']), fonte=f'Apify {portal}', cidade='Curitiba', titulo=clean(x.get('title')),
        bairro=clean(x.get('address_neighborhood'),100), finalidade='venda' if business=='SALE' else 'aluguel',
        tipo='apartamento', preco=positive('price'), area_m2=positive('area_useful'), area_total=positive('area_total'),
        quartos=num(x.get('bedrooms')), vagas=num(x.get('parking_spaces')), condominio=num(x.get('condominium_fee')),
        iptu_anual=num(x.get('iptu')), rua=clean(x.get('address_street'),160), numero=clean(x.get('address_number'),20),
        cep=re.sub(r'\D', '', str(x.get('address_zipcode') or ''))[:8],
        latitude=lat, longitude=lon, geo_precisao=precision, url=urllib.parse.urlunsplit(url),
        data_coleta=timestamp(x.get('scraped_at')), estagio=estate_stage, estagio_origem=origin, estagio_evidencia=evidence)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def request(url, method='GET', payload=None, token=None, form=None):
    headers = {'User-Agent': os.getenv('HTTP_USER_AGENT','HubTerritorial/3.0'), 'Accept':'application/json'}
    data = None
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if payload is not None:
        data = json.dumps(payload).encode(); headers['Content-Type'] = 'application/json'
    if form is not None:
        data = urllib.parse.urlencode(form).encode(); headers['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,data=data,headers=headers,method=method), timeout=40) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        raise RuntimeError('Serviço externo indisponível ou resposta inválida; nenhuma resposta foi inventada.') from None

def api(path, method='GET', payload=None):
    token = os.getenv('APIFY_TOKEN','').strip()
    if not token:
        raise RuntimeError('Configure um token NOVO em APIFY_TOKEN no .env local. Não publique o token.')
    return request(API+path,method,payload,token)

def connect(path=None):
    if path is None:
        data = Path(os.getenv('DATA_DIR',str(ROOT/'data'))).expanduser().resolve()
        url = os.getenv('DATABASE_URL','').strip()
        if url and not url.startswith('sqlite:///'):
            raise RuntimeError('Este piloto usa SQLite. Para PostgreSQL, é necessária migração específica; não será criado banco alternativo silenciosamente.')
        path = Path(url[len('sqlite:///'):]) if url else data/'imoveis.db'
        if not path.is_absolute(): path=ROOT/path
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS intel_budget (id INTEGER PRIMARY KEY, reservado INTEGER NOT NULL);
    INSERT OR IGNORE INTO intel_budget VALUES(1,0);
    CREATE TABLE IF NOT EXISTS ctb_jobs (id INTEGER PRIMARY KEY, business TEXT NOT NULL, run_id TEXT UNIQUE,
        state TEXT NOT NULL, created TEXT NOT NULL, input_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ctb_observations (id INTEGER PRIMARY KEY, listing_key TEXT NOT NULL, observed TEXT NOT NULL,
        payload TEXT NOT NULL, digest TEXT NOT NULL, UNIQUE(listing_key,observed,digest));
    CREATE INDEX IF NOT EXISTS ctb_history ON ctb_observations(listing_key,observed);
    CREATE TABLE IF NOT EXISTS ctb_imports (source_id TEXT PRIMARY KEY, imported TEXT NOT NULL, accepted INTEGER, rejected INTEGER, details TEXT);
    CREATE TABLE IF NOT EXISTS ctb_geocache (address_key TEXT PRIMARY KEY, payload TEXT NOT NULL, checked TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ctb_geobudget (id INTEGER PRIMARY KEY, used INTEGER NOT NULL);
    INSERT OR IGNORE INTO ctb_geobudget VALUES(1,0);
    ''');db.commit();return db

def inputs(business):
    if business not in ('SALE','RENTAL'): raise ValueError('Finalidade inválida')
    return dict(portal='BOTH',business=business,propertyType='APARTMENT',state='PR',city='Curitiba',maxItems=1500)

def start_job(db,business):
    if not os.getenv('APIFY_TOKEN'): raise RuntimeError('APIFY_TOKEN ausente no .env local.')
    db.execute('BEGIN IMMEDIATE')
    try:
        old=db.execute('SELECT * FROM ctb_jobs WHERE business=? ORDER BY id DESC LIMIT 1',(business,)).fetchone()
        if old:
            db.rollback();return dict(old) # retoma; nunca inicia novamente por clique/reexecução
        budget=db.execute('UPDATE intel_budget SET reservado=reservado+4 WHERE id=1 AND reservado+4<=10')
        if budget.rowcount!=1: raise RuntimeError('Reserva acumulada insuficiente no teto de US$10. Revise o gasto antes de autorizar outra coleta.')
        cur=db.execute('INSERT INTO ctb_jobs(business,state,created,input_json) VALUES(?,?,?,?)',(business,'START_UNCERTAIN',now(),json.dumps(inputs(business))))
        job_id=cur.lastrowid;db.commit()
    except Exception:
        db.rollback();raise
    run=api('/acts/'+ACTOR+'/runs?'+urllib.parse.urlencode(dict(timeout=3600,maxTotalChargeUsd=4,restartOnError='false')),'POST',inputs(business))['data']
    db.execute('UPDATE ctb_jobs SET run_id=?, state=? WHERE id=?',(run['id'],run['status'],job_id));db.commit()
    return dict(db.execute('SELECT * FROM ctb_jobs WHERE id=?',(job_id,)).fetchone())

def import_records(db,records,source_id):
    if db.execute('SELECT 1 FROM ctb_imports WHERE source_id=?',(source_id,)).fetchone(): return {'already_imported':True}
    accepted=[];errors={}
    for x in records:
        try: accepted.append(normalize(x))
        except (ValueError,TypeError) as e: errors[str(e)]=errors.get(str(e),0)+1
    with db:
        for x in accepted:
            p=json.dumps(x,sort_keys=True,ensure_ascii=False);digest=hashlib.sha256(p.encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO ctb_observations(listing_key,observed,payload,digest) VALUES(?,?,?,?)',(x['id'],x['data_coleta'],p,digest))
        db.execute('INSERT INTO ctb_imports VALUES(?,?,?,?,?)',(source_id,now(),len(accepted),sum(errors.values()),json.dumps(errors)))
    return dict(accepted=len(accepted),rejected=sum(errors.values()),reasons=errors)

def verify_run(run_id,business=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id): raise ValueError('Run ID inválido')
    run=api('/actor-runs/'+run_id)['data'];actor=api('/acts/'+ACTOR)['data']
    if run['actId']!=actor['id']: raise RuntimeError('Actor diferente do integrado.')
    actual=api('/key-value-stores/'+run['defaultKeyValueStoreId']+'/records/INPUT')
    expected=dict(city='Curitiba',state='PR',propertyType='APARTMENT')
    if any(actual.get(k)!=v for k,v in expected.items()) or actual.get('business') not in ('SALE','RENTAL') or (business and actual['business']!=business):
        raise RuntimeError('Execução não corresponde ao piloto Curitiba / apartamentos.')
    return run

def sync_job(db,job):
    if job['state'].startswith('IMPORTED'):
        return {'status':job['state'], 'partial':job['state'] not in ('IMPORTED', 'IMPORTED_SUCCEEDED')}
    if not job['run_id']:raise RuntimeError('Início incerto: confira Runs na Apify e use attach JOB_ID RUN_ID. Não repita a cobrança.')
    run=verify_run(job['run_id'],job['business']);status=run['status']
    if status not in ('SUCCEEDED','FAILED','TIMED-OUT','ABORTED'):
        db.execute('UPDATE ctb_jobs SET state=? WHERE id=?',(status,job['id']));db.commit();return dict(status=status)
    records=[];offset=0
    while True:
        page=api('/datasets/'+run['defaultDatasetId']+'/items?'+urllib.parse.urlencode(dict(format='json',clean='false',offset=offset,limit=1000)))
        if not isinstance(page,list):raise RuntimeError('Dataset inválido.')
        if not page:break
        records.extend(page);offset+=len(page)
        if len(records)>20000:raise RuntimeError('Dataset excede limite de segurança de 20 mil registros; não foi importado parcialmente.')
    result=import_records(db,records,job['run_id'])
    db.execute('UPDATE ctb_jobs SET state=? WHERE id=?',('IMPORTED_'+status,job['id']));db.commit()
    return dict(status=status,partial=status!='SUCCEEDED',**result)

def latest(db):
    return [json.loads(r[0]) for r in db.execute('''SELECT payload FROM (SELECT payload, ROW_NUMBER() OVER(PARTITION BY listing_key ORDER BY observed DESC,id DESC) AS rn FROM ctb_observations) WHERE rn=1''')]

def address_key(x):
    # Não usa apenas bairro/cidade: esses centroides não são imóveis.
    if not x.get('rua') and not x.get('cep'):return None
    parts=[x.get('rua'),x.get('numero'),x.get('cep'),x.get('bairro'),'Curitiba','PR','Brasil']
    return norm(', '.join(str(p) for p in parts if p))

def geocode_result(x,payload):
    for item in payload.get('results',[]):
        if norm(item.get('city'))!='curitiba' or item.get('country_code')!='br':continue
        if not valid_geo(item.get('lat'),item.get('lon')):continue
        rank=item.get('rank',{});typ=item.get('result_type')
        if (num(rank.get('confidence')) or 0)<0.8:continue
        if typ in ('building','amenity'):
            if not x.get('rua') or norm(item.get('street'))!=norm(x['rua']):continue
            if not x.get('numero') or norm(item.get('housenumber'))!=norm(x['numero']):continue
            precision='Endereço e número aproximados'
        elif typ=='street':
            if not x.get('rua') or norm(item.get('street'))!=norm(x['rua']):continue
            precision='Rua aproximada (sem posição do imóvel)'
        elif typ=='postcode':
            if not x.get('cep') or re.sub(r'\D','',str(item.get('postcode','')))!=x['cep']:continue
            precision='CEP aproximado (sem posição do imóvel)'
        else:continue
        return dict(latitude=item['lat'],longitude=item['lon'],geo_precisao=precision,geo_fonte='Geoapify / OpenStreetMap',geo_verificado_em=now())
    return None

def geocode(db,limit=100):
    key=os.getenv('GEOAPIFY_API_KEY','').strip()
    if not key:raise RuntimeError('Geocodificação opcional: configure GEOAPIFY_API_KEY no .env. Sem chave, anúncios continuam na lista.')
    used=0;found=0
    for x in latest(db):
        if valid_geo(x.get('latitude'),x.get('longitude')):continue
        address=address_key(x)
        if not address or db.execute('SELECT 1 FROM ctb_geocache WHERE address_key=?',(address,)).fetchone():continue
        if used>=limit:break
        with db:
            changed=db.execute('UPDATE ctb_geobudget SET used=used+1 WHERE id=1 AND used<1000')
            if not changed.rowcount:raise RuntimeError('Teto local de 1000 consultas Geoapify atingido. Verifique o plano e a franquia antes de ampliar.')
        query=urllib.parse.urlencode(dict(text=address,format='json',limit=3,filter='countrycode:br',apiKey=key))
        payload=request('https://api.geoapify.com/v1/geocode/search?'+query)
        result=geocode_result(x,payload)
        with db:db.execute('INSERT OR REPLACE INTO ctb_geocache VALUES(?,?,?)',(address,json.dumps(result),now()))
        used+=1;found+=bool(result);time.sleep(0.5)
    return dict(consultas=used,localizados=found)

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)

def export(db,folder):
    folder=Path(folder);rows=latest(db)
    for x in rows:
        x['endereco']=', '.join(str(x.get(k) or '') for k in ['rua','numero','cep']).strip(', ')
        if not valid_geo(x.get('latitude'),x.get('longitude')):
            hit=db.execute('SELECT payload FROM ctb_geocache WHERE address_key=?',(address_key(x),)).fetchone()
            if hit and json.loads(hit[0]):x.update(json.loads(hit[0]))
    # Agrupa identidade compartilhada Grupo ZAP, mantendo snapshots por portal no banco.
    groups={}
    for x in rows:groups.setdefault(x['grupo_id'],[]).append(x)
    consolidated=[]
    for group in groups.values():
        x=max(group,key=lambda x:(x['data_coleta'],valid_geo(x['latitude'],x['longitude']))).copy()
        x['fontes']=[dict(fonte=y['fonte'],url=y['url']) for y in group]
        consolidated.append(x)
    atomic_json(folder/'imoveis.json',consolidated)
    summary=dict(city='Curitiba',focus='Bacacheri',generated_at=now(),target=3000,records=len(consolidated),
        portal_records=len(rows),bacacheri=sum(norm(x['bairro'])=='bacacheri' for x in consolidated),
        geolocated=sum(valid_geo(x['latitude'],x['longitude']) for x in consolidated),
        target_reached=len(consolidated)>=3000,observations=db.execute('SELECT count(*) FROM ctb_observations').fetchone()[0],
        reserved_usd=db.execute('SELECT reservado FROM intel_budget WHERE id=1').fetchone()[0])
    atomic_json(folder/'status.json',summary);return summary

def enrich_public(folder):
    folder=Path(folder);status={}
    try:
        raw=request(IBGE);series=raw[0]['resultados'][0]['series'][0]
        if series['localidade']['id']!='4106902':raise ValueError('Município incorreto')
        population=int(series['serie']['2022'])
        if not 1000000<population<3000000:raise ValueError('População inválida')
        atomic_json(folder/'ibge.json',dict(city='Curitiba',population=population,year=2022,checked=now(),source=IBGE,ages=[],scope='Município inteiro',available=True))
        status['ibge']='Atualizado'
    except (RuntimeError,ValueError,KeyError,IndexError,TypeError):status['ibge']='Indisponível; snapshot anterior preservado'
    try:
        query=f'''[out:json][timeout:25];(nwr["amenity"~"^(restaurant|school|pharmacy|hospital)$"](around:3000,{CENTER[0]},{CENTER[1]});nwr["shop"~"^(supermarket|convenience)$"](around:3000,{CENTER[0]},{CENTER[1]});nwr["leisure"="fitness_centre"](around:3000,{CENTER[0]},{CENTER[1]}););out center tags;'''
        raw=request('https://overpass-api.de/api/interpreter','POST',form={'data':query})
        if raw.get('remark') or 'elements' not in raw:raise ValueError('Resposta incompleta')
        rows=[];categories={'restaurant':'Restaurantes','school':'Escolas','pharmacy':'Farmácias','hospital':'Hospitais','supermarket':'Mercados','convenience':'Mercados','fitness_centre':'Academias'}
        for x in raw['elements']:
            t=x.get('tags',{});c=x.get('center',x);cat=next((categories[t[k]] for k in ('amenity','shop','leisure') if t.get(k) in categories),None)
            if cat and valid_geo(c.get('lat'),c.get('lon')):rows.append(dict(id=f'{x["type"]}/{x["id"]}',nome=clean(t.get('name') or cat),categoria=cat,latitude=c['lat'],longitude=c['lon'],url=f'https://www.openstreetmap.org/{x["type"]}/{x["id"]}'))
        atomic_json(folder/'pois.json',dict(data=now(),centro=list(CENTER),raio_km=3,items=rows,available=True));status['osm']=f'{len(rows)} locais obtidos'
    except (RuntimeError,ValueError,KeyError,TypeError):status['osm']='Indisponível; snapshot anterior preservado'
    return status

def backup(db):
    path=Path(os.getenv('DATA_DIR',str(ROOT/'data')))/'backups'/('curitiba-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.db')
    path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as other:db.backup(other)
    return str(path)

def main():
    env();p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('collect');sub.add_parser('sync');sub.add_parser('status');sub.add_parser('public');sub.add_parser('export')
    a=sub.add_parser('import');a.add_argument('file')
    a=sub.add_parser('geocode');a.add_argument('--limit',type=int,default=100)
    a=sub.add_parser('attach');a.add_argument('job',type=int);a.add_argument('run')
    args=p.parse_args();folder=ROOT/'docs/curitiba';db=connect()
    try:
        if args.cmd=='collect':
            backup(db)
            for business in ('SALE','RENTAL'):
                job=start_job(db,business);print(json.dumps(job,ensure_ascii=False))
            print('Coletas iniciadas/retomadas. Execute sync para importar quando terminarem. Não repetir POST automaticamente.')
        elif args.cmd=='sync':
            backup(db)
            for job in db.execute('SELECT * FROM ctb_jobs').fetchall():print(json.dumps(sync_job(db,dict(job)),ensure_ascii=False))
            print(json.dumps(export(db,folder),ensure_ascii=False))
        elif args.cmd=='import':
            raw=Path(args.file).read_bytes()
            if len(raw)>50*1024*1024:raise ValueError('Máximo 50 MB')
            rows=json.loads(raw)
            if not isinstance(rows,list) or len(rows)>20000:raise ValueError('Use lista JSON de até 20 mil anúncios.')
            backup(db);print(import_records(db,rows,'file:'+hashlib.sha256(raw).hexdigest()));print(export(db,folder))
        elif args.cmd=='geocode':
            if not 1<=args.limit<=1000:raise ValueError('Use limite entre 1 e 1000')
            print(geocode(db,args.limit));print(export(db,folder))
        elif args.cmd=='attach':
            job=db.execute('SELECT * FROM ctb_jobs WHERE id=?',(args.job,)).fetchone()
            if not job or job['run_id']:raise ValueError('Apenas job de início incerto, sem run_id, pode ser vinculado.')
            run=verify_run(args.run,job['business'])
            with db:db.execute('UPDATE ctb_jobs SET run_id=?,state=? WHERE id=?',(args.run,run['status'],args.job))
        elif args.cmd=='public':print(enrich_public(folder))
        elif args.cmd=='export':print(export(db,folder))
        elif args.cmd=='status':
            print(json.dumps([dict(x) for x in db.execute('SELECT * FROM ctb_jobs')],ensure_ascii=False,indent=2));print(export(db,folder))
    finally:db.close()

if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,sqlite3.Error,OSError) as e:
        print('Não concluído:',str(e));raise SystemExit(1)
