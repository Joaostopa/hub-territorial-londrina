import json
from pathlib import Path
from unittest.mock import patch
from connectors.http import ExternalUnavailable
from connectors.ibge_perfil import municipal_profile
from scrapers.multisource import parse_listings
from scrapers.sources import SOURCES
from normalizer import normalize_record
from db.repository import import_records,latest
ROOT=Path(__file__).resolve().parents[1]

def test_verified_snapshot_import_is_idempotent(engine):
    rows=json.loads((ROOT/'dados_verificados/imoveis_2026-09-08.json').read_text())
    assert len(rows)==37
    assert import_records(engine,rows)['inseridos']==37
    assert import_records(engine,rows)['duplicados']==37
    frame=latest(engine,'Londrina')
    assert frame.latitude.notna().sum()==9
    assert not frame.is_demo.any()

def test_human_nested_property_and_invalid_geo():
    payload={'@type':'RealEstateListing','url':'www.humanimoveis.com/imovel/teste/AP6227_HMN',
             'name':'Apartamento','offers':{'price':420000,'businessFunction':'https://schema.org/Sell'},
             'itemOffered':{'@type':'Apartment','numberOfBedrooms':2,'floorSize':{'value':47},
                            'geo':{'latitude':-23.3261727,'longitude':-51.1896176},
                            'address':{'addressLocality':'Londrina'}}}
    html='<script type="application/ld+json">'+json.dumps(payload)+'</script>'
    row=normalize_record(parse_listings(html,SOURCES['human'].start_url,SOURCES['human'])[0])
    assert row['id_externo']=='AP6227_HMN' and row['area_m2']==47
    assert row['url'].startswith('https://') and row['latitude']==-23.3261727
    row.update(latitude=-14.235004,longitude=-51.92528)
    checked=normalize_record(row)
    assert checked['latitude'] is None and checked['geo_precisao']=='fora_cidade_revisar'

def test_ibge_fallback_is_identified_and_reconciled():
    with patch('connectors.ibge_perfil.municipal_population',return_value={'status':'indisponivel','populacao':None,'ano':2022}),patch('connectors.ibge_perfil.fetch',side_effect=ExternalUnavailable('Timeout')):
        result=municipal_profile('4113700')
    assert result['status']=='snapshot'
    assert result['populacao']==555965 and result['renda_media']==2332.51
    assert sum(r['pessoas'] for r in result['faixas_municipais'])==555965
    assert len(result['avisos'])==2 and '08/09/2026' in result['mensagem']

def test_windows_uses_same_environment():
    for name in ['instalar_windows.bat','iniciar_windows.bat','coletar_londrina.bat']:
        s=(ROOT/name).read_text()
        assert '.venv\\Scripts\\python.exe' in s
    assert 'preparar_projeto.py' in (ROOT/'instalar_windows.bat').read_text()
