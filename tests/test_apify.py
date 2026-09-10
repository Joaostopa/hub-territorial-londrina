"""Fixtures sintéticas exclusivas de testes; nunca importadas no banco do usuário."""
import json
from datetime import datetime
import pytest
from sqlalchemy import select,func
from db.models import init_db,make_engine,ApifyRun,ApifyObservation,Imovel,session
from apify_service import remember,import_items,sync,map_item
from connectors.apify import Client,ApifyError,londrina_input
from apify_cli import backup

@pytest.fixture
def engine(tmp_path):
    return init_db(make_engine('sqlite:///'+str(tmp_path/'test.db')))

def item(**changes):
    row=dict(listing_id='12345',portal='ZAP',business='SALE',price_currency='BRL',price=500000,
         address_city='Londrina',address_state_acronym='PR',url='https://www.zapimoveis.com.br/imovel/12345/',
         area_useful=80,area_total=100,property_type='APARTMENT',latitude=-23.31,longitude=-51.17,
         condominium_fee=450,iptu=1800,title='Apartamento teste',publisher_phone='43999999999',publisher_email='secret@example.com',
         scraped_at='2026-09-01T10:01:00Z')
    return dict(row,**changes)

def setup_run(engine,id='run1',business='SALE',day=1):
    inputs=londrina_input(business)
    remember(engine,dict(id=id,startedAt=f'2026-09-{day:02d}T10:00:00Z',status='SUCCEEDED',defaultDatasetId='ds'),inputs)
    return inputs

def count(engine,cls):
    with session(engine) as s:return s.scalar(select(func.count()).select_from(cls))

def test_history_idempotence_and_privacy(engine):
    inputs=setup_run(engine)
    assert import_items(engine,'run1',inputs,[item(),item()])['aceitos']==1
    assert import_items(engine,'run1',inputs,[item()])['status']=='JA_IMPORTADO'
    setup_run(engine,'run2',day=8)
    import_items(engine,'run2',inputs,[item(price=480000,scraped_at='2026-09-08T10:01:00Z')])
    assert count(engine,Imovel)==2
    assert count(engine,ApifyObservation)==2
    with session(engine) as s:
        payloads=s.scalars(select(ApifyObservation.payload_json)).all()
    assert 'secret@example' not in ''.join(payloads)
    assert 'publisher_phone' not in ''.join(payloads)
    assert json.loads(payloads[0])['condominium_fee']==450
    assert json.loads(payloads[0])['iptu']==1800

def test_city_currency_and_rental_rejections(engine):
    inputs=setup_run(engine)
    out=import_items(engine,'run1',inputs,[item(address_city='Curitiba'),item(price_currency='USD'),item(business='RENTAL')])
    assert out['rejeitados']==3
    assert count(engine,Imovel)==0

def test_sale_and_rental_are_separate(engine):
    from db.repository import latest
    inputs=setup_run(engine)
    import_items(engine,'run1',inputs,[item()])
    inputs=setup_run(engine,'rent','RENTAL')
    import_items(engine,'rent',inputs,[item(business='RENTAL',rental_period='MONTHLY',price=2300)])
    result=latest(engine)
    assert set(result.finalidade)=={'venda','aluguel'}
    assert len(result)==2

def test_missing_coords_and_useful_area(engine):
    inputs=setup_run(engine)
    import_items(engine,'run1',inputs,[item(latitude=None,area_useful=None)])
    with session(engine) as s:
        row=s.scalar(select(Imovel))
        assert row.latitude is None and row.longitude is None
        assert row.area_m2 is None and row.preco_m2 is None

class FakeClient:
    def run(self,id): return dict(id=id,startedAt='2026-09-01T10:00:00Z',status='SUCCEEDED',defaultDatasetId='ds')
    def inputs(self,run):return londrina_input()
    def items(self,id):
        yield item()
        raise ApifyError('pagination failed')

def test_failed_pagination_commits_no_observations(engine):
    with pytest.raises(ApifyError):sync(engine,'run1',FakeClient())
    assert count(engine,Imovel)==0
    assert count(engine,ApifyObservation)==0
    with session(engine) as s: assert s.get(ApifyRun,'run1').imported_at is None

def test_dataset_pagination():
    client=Client('test-token')
    offsets=[]
    def request(method,path,**kwargs):
        offset=kwargs['params']['offset'];offsets.append(offset)
        return [{'id':i} for i in range(offset,min(offset+1000,2001))]
    client.request=request
    assert len(list(client.items('dataset')))==2001
    assert offsets==[0,1000,2000,2001]

def test_backup_restores_history(engine,tmp_path,monkeypatch):
    import apify_cli
    monkeypatch.setattr(apify_cli,'DATA_DIR',tmp_path)
    inputs=setup_run(engine)
    import_items(engine,'run1',inputs,[item()])
    path=backup(engine)
    restored=make_engine('sqlite:///'+str(path))
    assert count(restored,ApifyObservation)==1
    assert count(restored,Imovel)==1

def test_weekly_uncertain_start_does_not_repeat_charge(engine,tmp_path,monkeypatch):
    import apify_cli
    monkeypatch.setattr(apify_cli,'DATA_DIR',tmp_path)
    calls=[]
    def failed(*args):
        calls.append(True)
        raise ApifyError('network timeout after POST')
    monkeypatch.setattr(apify_cli,'start',failed)
    with pytest.raises(ApifyError):apify_cli.weekly(engine,'SALE',100)
    with pytest.raises(ApifyError):apify_cli.weekly(engine,'SALE',100)
    assert len(calls)==1

def test_weekly_resume_no_new_run(engine,tmp_path,monkeypatch):
    import apify_cli
    monkeypatch.setattr(apify_cli,'DATA_DIR',tmp_path)
    (tmp_path/'apify-weekly-SALE.json').write_text(json.dumps({'week':'2026-W37','run_id':'existing','done':False,'uncertain':False}))
    def forbidden(*args):raise AssertionError('must not start again')
    monkeypatch.setattr(apify_cli,'start',forbidden)
    monkeypatch.setattr(apify_cli,'sync',lambda *a:{'status':'IMPORTADO'})
    assert apify_cli.weekly(engine,'SALE',100)['status']=='IMPORTADO'

def test_ui_import_and_history(tmp_path):
    from pathlib import Path
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest
    script=tmp_path/'ui.py'
    script.write_text('''from db.models import init_db,make_engine
from apify_ui import render
render(init_db(make_engine()),lambda:None)
''')
    with patch('apify_ui.start',return_value='uiRun'):
        app=AppTest.from_file(str(script),default_timeout=30).run()
        assert not app.exception
        next(b for b in app.button if 'Iniciar coleta' in b.label).click().run()
        assert not app.exception
        assert app.text_input(key='apify_run_id').value=='uiRun'
    def fake_sync(engine,run_id):
        inputs=setup_run(engine,run_id)
        return import_items(engine,run_id,inputs,[item()])
    with patch('apify_ui.sync',side_effect=fake_sync):
        next(b for b in app.button if 'Consultar execução' in b.label).click().run()
        assert not app.exception,[e.message for e in app.exception]
        assert any('observações preservadas' in x.value for x in app.markdown)
