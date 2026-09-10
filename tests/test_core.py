import json
import math
import sqlite3
from datetime import datetime
import pandas as pd
import pytest
from sqlalchemy import inspect,select,URL
from db.models import Imovel,SchemaMismatch,make_engine,init_db,session
from db.repository import latest,import_records,filter_listings,save_favorite,favorites,delete_favorite
from normalizer import normalize_record
from geoutils import haversine,within_radius,extract_circle
from analytics import monthly_history,opportunity_scores
from io_utils import csv_bytes,excel_bytes
from alerts import enable_alert,check_alerts,events_for
from migrate_legacy import migrate

def test_empty_database_ready(engine):
    assert 'imoveis' in inspect(engine).get_table_names()
    assert latest(engine,'Londrina').empty
    assert within_radius(latest(engine,'Londrina'),-23.3,-51.1,2).empty

def test_normalize_brazil_money_and_privacy(record):
    out=normalize_record({**record,'telefone':'43999999999','email':'x@y.com','titulo':'Contato x@y.com 43 99999-9999','url':'https://example.com/anuncio/1?email=x#tracking'})
    assert out['preco']==520000
    assert out['preco_m2']==5200
    assert 'telefone' not in out and 'email' not in out
    assert 'x@y.com' not in out['titulo'] and '99999' not in out['titulo']
    assert out['url']=='https://example.com/anuncio/1'

@pytest.mark.parametrize('change',[{'preco':-10},{'area_m2':0},{'latitude':999},{'quartos':1.5},
                                   {'latitude':float('inf')},{'longitude':None},{'finalidade':'troca'}])
def test_invalid_records_rejected(record,change):
    with pytest.raises(ValueError):normalize_record({**record,**change})

def test_latest_snapshot_and_duplicate_import(engine,record):
    assert import_records(engine,[record])['inseridos']==1
    assert import_records(engine,[record])['duplicados']==1
    import_records(engine,[{**record,'preco':600000,'data_coleta':'2026-08-02'},
                           {**record,'fonte':'Outra','preco':450000}])
    df=latest(engine,'Londrina')
    assert len(df)==2
    assert df.loc[df.fonte=='Teste','preco'].iloc[0]==600000
    assert len(latest(engine,'Londrina',datetime(2026,8,1,23,59)))==2

def test_latest_missing_geolocation_not_resurrected(engine,record):
    import_records(engine,[record,{**record,'latitude':None,'longitude':None,'data_coleta':'2026-08-02'}])
    assert filter_listings(latest(engine),{}).empty

def test_purpose_filters_never_mix(engine,record):
    import_records(engine,[record,{**record,'id_externo':'2','finalidade':'aluguel','preco':3000}])
    assert filter_listings(latest(engine),{'finalidade':'venda'}).preco.tolist()==[520000]

def test_haversine_and_boundary():
    assert float(haversine(0,0,0,1))==pytest.approx(111.19508,abs=.001)
    distance=float(haversine(0,0,0,.01))
    df=pd.DataFrame({'latitude':[0,0],'longitude':[.01,.02]})
    assert len(within_radius(df,0,0,distance))==1

def test_map_units_and_clear():
    feature={'geometry':{'type':'Point','coordinates':[-51,-23]},'properties':{'radius':1834.2}}
    assert extract_circle({'last_active_drawing':feature})==(-23.,-51.,1.8342)
    feature['properties']={}
    assert extract_circle({'last_active_drawing':feature,'last_circle_radius':1.8342})==(-23.,-51.,1.8342)
    assert extract_circle({'all_drawings':[]}) is None
    assert extract_circle(None) is None

def test_monthly_history_one_per_ad_per_month(engine,record):
    import_records(engine,[record,{**record,'preco':600000,'data_coleta':'2026-08-02'},
                          {**record,'preco':500000,'data_coleta':'2026-07-02'}])
    h=monthly_history(engine,'Londrina',{'finalidade':'venda'},(-23.3045,-51.1696,2))
    assert h.anuncios.tolist()==[1,1]
    assert h.mediana_m2.tolist()==[5000,6000]

def test_favorites_are_owner_scoped(engine):
    save_favorite(engine,'alice','Área','Londrina',(-23,-51,1),{'finalidade':'venda'})
    save_favorite(engine,'bob','Área','Londrina',(-23,-51,1),{'finalidade':'venda'})
    alice=favorites(engine,'alice')[0]
    delete_favorite(engine,'bob',alice['id'])
    assert len(favorites(engine,'alice'))==1
    with pytest.raises(ValueError):save_favorite(engine,'alice','Área','Londrina',(-23,-51,1),{})

def test_alert_baseline_and_new_ad_once(engine,record):
    save_favorite(engine,'alice','Área','Londrina',(-23.3045,-51.1696,1),{'finalidade':'venda'})
    aid=favorites(engine,'alice')[0]['id'];enable_alert(engine,'alice',aid,10)
    import_records(engine,[record]);assert check_alerts(engine,'alice')==[]
    import_records(engine,[{**record,'id_externo':'2'}]);assert len(check_alerts(engine,'alice'))==1
    assert check_alerts(engine,'alice')==[]
    assert events_for(engine,'bob').empty

def test_score_missing_and_relative():
    rows=[{'area':str(i),'anuncios':10,'com_preco_m2':10,'mediana_m2':5000+i*1000,
           'crescimento_pct':10-i,'renda_media':5000-i*1000,'densidade':1+i} for i in range(3)]
    result=opportunity_scores(rows)
    assert result.score.tolist()==[100,50,0]
    rows[0]['renda_media']=None
    assert opportunity_scores(rows).score.isna().all()

def test_exports_neutralize_formulas():
    frame=pd.DataFrame({'titulo':['=WEBSERVICE("https://example.com")','Normal'],'preco':[100,200]})
    assert "'=WEBSERVICE" in csv_bytes(frame).decode('utf-8-sig')
    from openpyxl import load_workbook
    from io import BytesIO
    wb=load_workbook(BytesIO(excel_bytes({'Imoveis':frame})))
    assert wb.active['A2'].data_type=='s'
    assert wb.active['A2'].value.startswith("'=")

def test_legacy_detection_and_non_destructive_migration(tmp_path,record):
    source=tmp_path/'old.db'
    with sqlite3.connect(source) as conn:pd.DataFrame([record]).to_sql('imoveis',conn,index=False)
    before=source.read_bytes()
    e=make_engine(URL.create('sqlite',database=str(source)))
    with pytest.raises(SchemaMismatch):init_db(e)
    e.dispose()
    # PRAGMA journal_mode may update metadata; snapshot after opening to check migration immutability.
    before=source.read_bytes()
    result=migrate(source,tmp_path/'new.db')
    assert result['inseridos']==1
    assert source.read_bytes()==before
    with pytest.raises(ValueError):migrate(source,source)
