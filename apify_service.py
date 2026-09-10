"""Snapshots imutáveis por execução; importação transacional e sem contatos."""
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit
import pandas as pd
from sqlalchemy import select
from db.models import ApifyRun, ApifyObservation, Imovel, session, utcnow
from normalizer import normalize_record, clean_text
from connectors.apify import Client, ApifyError, londrina_input, identifier

TYPES = {'APARTMENT':'apartamento','HOME':'casa','ALLOTMENT_LAND':'terreno',
         'COMMERCIAL_BUILDING':'comercial','COMMERCIAL_PROPERTY':'comercial','FARM':'rural','OFFICE':'comercial'}
SAFE = ('listing_type','rental_period','condominium_fee','iptu','area_total','area_useful',
        'suites','bathrooms','amenities','listed_at','updated_at','scraped_at')

def timestamp(value):
    stamp = pd.to_datetime(value, utc=True, errors='raise')
    if pd.isna(stamp):
        raise ValueError('Data da coleta ausente.')
    return stamp.to_pydatetime().replace(tzinfo=None)

def validate_inputs(inputs):
    if inputs.get('city','').strip().casefold() != 'londrina' or inputs.get('state') != 'PR':
        raise ApifyError('Somente execuções de Londrina/PR podem ser importadas.')
    if inputs.get('business') not in ('SALE','RENTAL') or inputs.get('portal') not in ('BOTH','VIVAREAL','ZAP'):
        raise ApifyError('Finalidade ou portal da execução inválido.')
    # Preserve configuration only; never copy arbitrary input secrets.
    return {k:inputs.get(k) for k in ('portal','business','propertyType','state','city','maxItems')}

def map_item(item, inputs, observed):
    if not isinstance(item,dict):
        raise ValueError('Registro não é um objeto.')
    if str(item.get('address_city','')).strip().casefold() != 'londrina' or item.get('address_state_acronym') != 'PR':
        raise ValueError('Registro fora de Londrina/PR ou sem município/UF.')
    portal = item.get('portal')
    if portal not in ('ZAP','VIVAREAL') or (inputs['portal'] != 'BOTH' and inputs['portal'] != portal):
        raise ValueError('Portal divergente.')
    business = item.get('business')
    if business != inputs['business']:
        raise ValueError('Finalidade divergente.')
    if item.get('price_currency') != 'BRL':
        raise ValueError('Moeda ausente ou diferente de BRL.')
    if business == 'RENTAL' and item.get('rental_period') != 'MONTHLY':
        raise ValueError('Aluguel não mensal: excluído para não misturar diárias e mensalidades.')
    listing_id = identifier(item.get('listing_id',''))
    url = str(item.get('url') or '')
    host = urlsplit(url).hostname or ''
    expected = 'zapimoveis.com.br' if portal == 'ZAP' else 'vivareal.com.br'
    if host not in (expected,'www.'+expected) or urlsplit(url).scheme != 'https':
        raise ValueError('URL do anúncio não corresponde ao portal.')
    lat, lon = item.get('latitude'), item.get('longitude')
    if lat is None or lon is None:
        lat = lon = None
    row = normalize_record(dict(fonte='Apify '+portal, id_externo=listing_id+':'+business,
          data_coleta=observed.isoformat(), titulo=item.get('title'),url=url,cidade='Londrina',
          bairro=item.get('address_neighborhood'),finalidade='venda' if business=='SALE' else 'aluguel',
          tipo=TYPES.get(item.get('property_type'),'outro'),preco=item.get('price'),
          area_m2=item.get('area_useful'),quartos=item.get('bedrooms'),vagas=item.get('parking_spaces'),
          latitude=lat,longitude=lon,geo_precisao='aproximada_portal' if lat is not None else 'nao_informada'))
    # Area útil não é substituída pela total: preço/m² permanece comparável.
    payload = {**row,'data_coleta':observed.isoformat(),'listing_id':listing_id,'portal':portal,'business':business}
    for key in SAFE:
        value = item.get(key)
        if key == 'amenities':
            value = [clean_text(v,80) for v in value if isinstance(v,str)][:100] if isinstance(value,list) else []
        elif isinstance(value,str):
            value = clean_text(value,100)
        elif value is not None and not isinstance(value,(int,float)):
            value = None
        payload[key] = value
    return row, payload

def start(engine, business='SALE', max_items=100, client=None):
    client = client or Client()
    inputs = londrina_input(business,max_items)
    run = client.start(inputs)
    remember(engine,run,inputs)
    return run['id']

def remember(engine,run,inputs):
    with session(engine) as s, s.begin():
        row = s.get(ApifyRun,run['id'])
        if row is None:
            s.add(ApifyRun(run_id=run['id'],dataset_id=run.get('defaultDatasetId'),
                  business=inputs['business'],input_json=json.dumps(inputs),
                  started_at=timestamp(run['startedAt']),status=run['status']))
        elif row.imported_at is None:
            row.status=run['status']
            row.dataset_id=run.get('defaultDatasetId')

def sync(engine, run_id, client=None):
    client = client or Client()
    run = client.run(identifier(run_id))
    inputs = validate_inputs(client.inputs(run))
    remember(engine,run,inputs)
    if run['status'] != 'SUCCEEDED':
        return {'status':run['status'],'mensagem':'Ainda não importado. Somente execuções concluídas com sucesso são aceitas.'}
    with session(engine) as s:
        old = s.get(ApifyRun,run_id)
        if old.imported_at:
            return {'status':'JA_IMPORTADO','aceitos':old.accepted,'rejeitados':old.rejected}
    # Fetch all pages before committing: interrupted pagination cannot create a partial snapshot.
    items = list(client.items(run['defaultDatasetId']))
    return import_items(engine,run_id,inputs,items)

def import_items(engine,run_id,inputs,items):
    errors=[]; seen=set(); accepted=0
    with session(engine) as s, s.begin():
        run = s.get(ApifyRun,run_id)
        if run.imported_at:
            return {'status':'JA_IMPORTADO','aceitos':run.accepted,'rejeitados':run.rejected}
        for index,item in enumerate(items,1):
            try:
                observed = timestamp(item.get('scraped_at') or run.started_at) if isinstance(item,dict) else run.started_at
                if observed < run.started_at.replace(microsecond=0) or observed > utcnow()+__import__('datetime').timedelta(minutes=10):
                    raise ValueError('Data de observação incompatível com a execução.')
                row,payload = map_item(item,inputs,observed)
            except (ValueError,TypeError,OverflowError,ApifyError):
                errors.append({'linha':index,'erro':'Registro inválido: confira cidade, finalidade, moeda, data, URL e valores no dataset.'})
                continue
            key=(payload['portal'],payload['listing_id'],payload['business'])
            if key in seen:
                continue
            seen.add(key)
            s.add(ApifyObservation(run_id=run_id,portal=key[0],listing_id=key[1],business=key[2],observed_at=observed,
                                  payload_json=json.dumps(payload,ensure_ascii=False,allow_nan=False)))
            exists=s.scalar(select(Imovel.id).where(Imovel.fonte==row['fonte'],Imovel.id_externo==row['id_externo'],Imovel.data_coleta==row['data_coleta']))
            if not exists:
                s.add(Imovel(**row))
            accepted+=1
        run.imported_at=utcnow();run.item_count=len(items);run.accepted=accepted;run.rejected=len(errors)
        run.status='IMPORTADO_COM_REJEICOES' if errors else ('IMPORTADO' if items else 'VAZIO')
        run.detail=json.dumps({'erros':errors,'limite_solicitado':inputs.get('maxItems'),
            'aviso':'Cobertura não comprovada; ausência não significa venda. Portais podem repetir o mesmo imóvel.'},ensure_ascii=False)
    return {'status':'IMPORTADO','aceitos':accepted,'rejeitados':len(errors),'duplicados_no_dataset':len(items)-accepted-len(errors)}

def history(engine):
    with engine.connect() as conn:
        return pd.read_sql(select(ApifyObservation).order_by(ApifyObservation.observed_at),conn)
