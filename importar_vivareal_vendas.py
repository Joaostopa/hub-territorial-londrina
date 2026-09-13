"""Importa exportação fatihtahta/vivareal-scraper: somente apartamentos à venda.
Não inicia coletas, não usa token e não armazena contatos do anunciante.
"""
import argparse
import hashlib
import json
from pathlib import Path
import curitiba_pipeline as core


def convert(row, reference):
    if not isinstance(row,dict):raise ValueError('registro inválido')
    attr=row.get('attributes') or {};loc=row.get('location') or {};pricing=row.get('pricing') or {}
    if attr.get('business')!='sale':raise ValueError('fora do escopo: somente venda')
    if attr.get('unit_types')!=['apartment']:raise ValueError('tipo diferente ou misto')
    offers=[o for o in pricing.get('offers',[]) if o.get('business_type')=='sale']
    if not offers:raise ValueError('sem oferta de venda')
    prices=[core.num(o.get('amount')) for o in offers]
    prices=[p for p in prices if p is not None and p>0]
    if not prices:raise ValueError('sem preço de venda válido')
    if any(o.get('currency',pricing.get('currency'))!='BRL' for o in offers):raise ValueError('moeda não BRL')
    area=attr.get('area') or {};rooms=attr.get('rooms') or {};content=row.get('content') or {}
    coord=loc.get('coordinates') or {};geocoding=loc.get('geocoding') or {};identity=row.get('identity') or {}
    # Não combina preço mínimo de uma tipologia com área de outra.
    varied=len(set(prices))>1 or len(attr.get('variants') or [])>1
    flat=dict(listing_id=identity.get('id'),portal='VIVAREAL',business='SALE',property_type='APARTMENT',
        address_city=loc.get('city'),address_state_acronym=loc.get('state_code'),address_neighborhood=loc.get('neighborhood'),
        address_street=loc.get('street'),address_number=loc.get('street_number'),address_zipcode=loc.get('postal_code'),
        latitude=coord.get('latitude'),longitude=coord.get('longitude'),
        title=content.get('title') or f'Apartamento à venda · {loc.get("neighborhood") or "Curitiba"} · anúncio {identity.get("id")}',
        description=content.get('description'),price=min(prices),price_currency='BRL',
        area_useful=None if varied else area.get('usable_area'),area_total=None if varied else area.get('total_area'),
        bedrooms=rooms.get('bedrooms'),parking_spaces=rooms.get('parking_spaces'),
        condominium_fee=offers[0].get('monthly_condo_fee') if len(offers)==1 else None,
        iptu=offers[0].get('yearly_iptu') if len(offers)==1 else None,
        url=(row.get('source_context') or {}).get('url'),scraped_at=reference)
    x=core.normalize(flat)
    x.update(coletor='fatihtahta/vivareal-scraper',data_referencia_origem='Importação/exportação; data de coleta não fornecida pelo dataset',
        preco_tipo='A partir de' if varied else 'Preço anunciado',preco_max=max(prices),
        pagina_origem=(row.get('source_context') or {}).get('page_index'),
        endereco=', '.join(str(v) for v in [x.get('rua'),x.get('numero'),x.get('cep')] if v),
        fonte_tipo='Dataset fornecido pelo usuário; anúncio não reconfirmado individualmente')
    if core.valid_geo(x['latitude'],x['longitude']):
        precision=geocoding.get('precision')
        x['geo_precisao']={'rooftop':'Portal: endereço aproximado','range_interpolated':'Portal: endereço interpolado','geometric_center':'Rua aproximada (centro geométrico do portal)'}.get(precision,'Portal aproximada')
    status=attr.get('construction_status')
    if status=='under_construction':
        x.update(estagio='Em construção',estagio_origem='Campo construction_status do portal',estagio_evidencia='under_construction')
    x['construction_status_original']=core.clean(status,60)
    # Conserva datas da fonte com nomes distintos; não as confunde com coleta.
    for k in ('published_at','created_at','updated_at'):
        value=(row.get('timestamps') or {}).get(k)
        if value:
            try:x[k]=core.timestamp(value)
            except ValueError:pass
    return x


def import_file(db,file,reference=None):
    raw=Path(file).read_bytes()
    if len(raw)>50*1024*1024:raise ValueError('Máximo de 50 MB')
    source_id='fatihtahta-file:'+hashlib.sha256(raw).hexdigest()
    prior=db.execute('SELECT accepted,rejected,details FROM ctb_imports WHERE source_id=?',(source_id,)).fetchone()
    if prior:return dict(already_imported=True,accepted=prior['accepted'],rejected=prior['rejected'],reasons=json.loads(prior['details']))
    records=json.loads(raw)
    if not isinstance(records,list) or len(records)>20000:raise ValueError('Esperada lista de até 20 mil registros')
    reference=core.timestamp(reference or core.now());accepted=[];errors={}
    for row in records:
        try:accepted.append(convert(row,reference))
        except (ValueError,TypeError,KeyError) as e:errors[str(e)]=errors.get(str(e),0)+1
    if not accepted:raise ValueError('Nenhum anúncio válido de venda em Curitiba. Motivos: '+json.dumps(errors,ensure_ascii=False))
    with db:
        for x in accepted:
            p=json.dumps(x,ensure_ascii=False,sort_keys=True)
            db.execute('INSERT OR IGNORE INTO ctb_observations(listing_key,observed,payload,digest) VALUES(?,?,?,?)',
                (x['id'],x['data_coleta'],p,hashlib.sha256(p.encode()).hexdigest()))
        db.execute('INSERT INTO ctb_imports VALUES(?,?,?,?,?)',(source_id,core.now(),len(accepted),sum(errors.values()),json.dumps(errors)))
    return dict(accepted=len(accepted),rejected=sum(errors.values()),reasons=errors)


def main():
    core.env();p=argparse.ArgumentParser(description=__doc__);p.add_argument('arquivo');args=p.parse_args()
    db=core.connect()
    try:
        core.backup(db);print(json.dumps(import_file(db,args.arquivo),ensure_ascii=False,indent=2))
        print(json.dumps(core.export(db,core.ROOT/'docs/curitiba'),ensure_ascii=False,indent=2))
        print('Importação concluída. Abra iniciar_curitiba.bat e recarregue a página local.')
    finally:db.close()

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as e:print('Não concluído:',e);raise SystemExit(1)
