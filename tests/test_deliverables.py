from io import BytesIO
from unittest.mock import Mock
from sqlalchemy import select
import pandas as pd
import pytest
from db.models import session,EventoAlerta,NotificationDelivery
from db.repository import import_records,latest,filter_listings
from notifications import save_target,deliver_pending,NotificationError,send_whatsapp
from geoutils import within_radius
from pdf_report import build_pdf
from analytics import monthly_history

def test_notification_retry_and_delivered_not_resent(engine,monkeypatch):
    save_target(engine,'alice','email','alice@example.com')
    with session(engine) as s,s.begin():s.add(EventoAlerta(owner='alice',area_id=1,mensagem='Mensagem de teste'))
    fail=Mock(side_effect=NotificationError('offline'))
    monkeypatch.setattr('notifications.send_email',fail)
    assert deliver_pending(engine)=={'entregues':0,'falhas':1}
    good=Mock();monkeypatch.setattr('notifications.send_email',good)
    assert deliver_pending(engine)=={'entregues':1,'falhas':0}
    assert deliver_pending(engine)=={'entregues':0,'falhas':0}
    assert good.call_count==1

def test_whatsapp_template_payload_without_sending(monkeypatch):
    for k,v in {'WHATSAPP_API_VERSION':'v99.0','WHATSAPP_PHONE_NUMBER_ID':'123','WHATSAPP_TOKEN':'TEST_TOKEN',
                'WHATSAPP_TEMPLATE':'hub_alerta'}.items():monkeypatch.setenv(k,v)
    post=Mock(return_value=Mock());monkeypatch.setattr('notifications.requests.post',post)
    send_whatsapp('5543999999999','Área de teste')
    assert post.call_args.kwargs['json']['type']=='template'
    assert post.call_args.kwargs['json']['template']['components'][0]['parameters'][0]['text']=='Área de teste'

def test_pdf_empty_and_populated(engine,record):
    ar=(-23.3045,-51.1696,2)
    for populated in (False,True):
        if populated:import_records(engine,[record])
        df=within_radius(filter_listings(latest(engine),{}),*ar)
        content=build_pdf('Londrina',ar,df,{'finalidade':'venda'},pd.DataFrame(),
                         {'mensagem':'Sem dados','fontes':[]},{'populacao':None},pd.DataFrame(),
                         'Offline',monthly_history(engine,'Londrina',{}),pd.DataFrame(),demo=True)
        assert content.startswith(b'%PDF-') and len(content)>4000

def test_localized_thousands_but_decimal_coordinates(record):
    from normalizer import normalize_record
    row=normalize_record({**record,'preco':'520.000','latitude':'-23.304','longitude':'-51.169'})
    assert row['preco']==520000 and row['latitude']==-23.304

def test_raw_portal_html_not_cached(monkeypatch):
    from connectors.http import fetch
    from config import DATA_DIR
    monkeypatch.setattr('connectors.http._reserve',lambda *a,**k:None)
    response=Mock(content=b'<html>contact@example.com</html>',text='<html>contact@example.com</html>')
    monkeypatch.setattr('connectors.http.requests.request',Mock(return_value=response))
    before=set((DATA_DIR/'cache').glob('*.json'))
    fetch('https://example.com/private-fixture',as_json=False,cache=False)
    assert set((DATA_DIR/'cache').glob('*.json'))==before

def test_numeric_listing_id_is_not_redacted_as_phone(record):
    from normalizer import normalize_record
    assert normalize_record({**record,'id_externo':'12345678901'})['id_externo']=='12345678901'
    assert normalize_record({**record,'cidade':'londrina'})['cidade']=='Londrina'
