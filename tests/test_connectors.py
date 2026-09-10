import json
import pandas as pd
import pytest
from shapely.geometry import box,mapping
from connectors.ibge_malha import save_mesh,intersect_neighborhoods,validate_geojson
from connectors.ibge_bairros import save_indicators,area_demographics
from connectors.ibge_censo import municipal_population
from connectors.http import ExternalUnavailable
from scrapers.olx_scraper import parse
from scrapers.vivareal_zap_scraper import parse_payload
from scrapers.base import validate_portal_url,ScraperUnavailable


def mesh():
    return {'type':'FeatureCollection','features':[
        {'type':'Feature','properties':{'codigo':'1','nome':'Oeste'},'geometry':mapping(box(-.05,-.05,0,.05))},
        {'type':'Feature','properties':{'codigo':'2','nome':'Leste'},'geometry':mapping(box(0,-.05,.05,.05))}]}

def test_circle_intersects_both_neighborhoods():
    save_mesh('test',mesh(),'Fixture de teste, não IBGE')
    neighborhoods,geo,note=intersect_neighborhoods('test',0,0,1)
    assert len(neighborhoods)==2
    assert neighborhoods.attrs['cobertura_circulo']==pytest.approx(1)
    assert neighborhoods.fracao_area.between(0,1).all()
    save_indicators('test',pd.DataFrame([{'codigo':str(i),'ano':2022,'fonte':'Teste','populacao':1000,'renda_media':2000} for i in (1,2)]))
    d,_=area_demographics('test',neighborhoods)
    assert d['status']=='estimativa'
    assert d['populacao_estimada']==pytest.approx((neighborhoods.fracao_area*1000).sum())
    assert d['renda_media']==pytest.approx(2000)

def test_missing_partial_mesh_never_fabricates_population():
    n,_,_=intersect_neighborhoods('missing',0,0,1)
    assert n.empty and area_demographics('missing',n)[0]['populacao_estimada'] is None
    partial=mesh();partial['features']=partial['features'][:1]
    save_mesh('partial',partial,'Teste')
    n,_,_=intersect_neighborhoods('partial',0,0,1)
    save_indicators('partial',pd.DataFrame([{'codigo':'1','ano':2022,'fonte':'Teste','populacao':1000}]))
    assert area_demographics('partial',n)[0]['populacao_estimada'] is None

def test_overlapping_mesh_suppresses_total():
    payload=mesh();payload['features'][1]['geometry']=payload['features'][0]['geometry']
    save_mesh('overlap',payload,'Teste')
    n,_,_=intersect_neighborhoods('overlap',0,0,1)
    assert n.attrs['sobreposicao']

def test_ibge_success_and_failure(monkeypatch):
    monkeypatch.setattr('connectors.ibge_censo.fetch',lambda *a,**k:[{'resultados':[{'series':[{'serie':{'2022':'555965'}}]}]}])
    assert municipal_population('4113700')['populacao']==555965
    def fail(*a,**k):raise ExternalUnavailable('offline')
    monkeypatch.setattr('connectors.ibge_censo.fetch',fail)
    assert municipal_population('4113700')['populacao'] is None

def test_olx_fixture_parser_no_contacts():
    payload={'props':{'pageProps':{'ads':[{'listId':123,'price':'520.000','subject':'Apartamento','properties':[{'name':'size','value':'100'}],
                                         'location':{'latitude':-23.3,'longitude':-51.1},'phone':'43999999999'}]}}}
    rows=parse('<script id="__NEXT_DATA__">'+json.dumps(payload)+'</script>','Londrina')
    assert len(rows)==1 and rows[0]['id_externo']=='123' and 'phone' not in rows[0]
    with pytest.raises(ScraperUnavailable):parse('<html>CAPTCHA</html>','Londrina')

def test_vivareal_json_fixture():
    payload={'listings':[{'id':'1','pricingInfos':[{'businessType':'SALE','price':'500000'}],
                         'address':{'point':{'lat':-23,'lon':-51}},'usableAreas':[100]}]}
    assert parse_payload(payload,'Londrina')[0]['preco']=='500000'
    with pytest.raises(ScraperUnavailable):parse_payload(payload,'Londrina','aluguel')

@pytest.mark.parametrize('url',['http://www.olx.com.br/a','https://evil.com/a','https://olx.com.br.evil.com','https://x:secret@olx.com.br'])
def test_portal_domains_restricted(url):
    with pytest.raises(ValueError):validate_portal_url(url,['olx.com.br'])
