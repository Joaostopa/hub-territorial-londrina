import json
import pytest
from sqlalchemy import select
from db.models import init_db,make_engine,session,CollectionRun
from db.repository import latest
from scrapers.sources import SOURCES
from scrapers.multisource import parse_listings,links
from scrapers.transport import Page,CollectionFailure,PublicClient
from collect_batch import collect_source


def structured(identifier='1'):
    return '<script type="application/ld+json">'+json.dumps({'@type':'Apartment','sku':identifier,'name':'Apartamento','offers':{'price':450000},'floorSize':{'value':70}})+'</script>'

class FakeClient:
    requests_count=0
    def __init__(self,pages):self.pages=iter(pages)
    def get(self,url):
        self.requests_count+=1
        value=next(self.pages)
        if isinstance(value,Exception):raise value
        return Page(url,value,200)

@pytest.fixture
def engine(tmp_path):return init_db(make_engine('sqlite:///'+str(tmp_path/'test.db')))


def test_pagination_deduplicates_and_persists(engine):
    first=structured()+'<a rel="next" href="?page=2">Próxima</a>'
    result=collect_source(engine,'human',client=FakeClient([first,structured()]))
    assert result['inserted']==1 and result['pages']==2
    assert len(latest(engine,'Londrina'))==1
    assert latest(engine,'Londrina').latitude.isna().all()


def test_failure_preserves_first_page(engine):
    first=structured()+'<a rel="next" href="?page=2">Próxima</a>'
    result=collect_source(engine,'human',client=FakeClient([first,CollectionFailure('network_error','Timeout')]))
    assert result['status']=='partial' and result['inserted']==1
    with session(engine) as s:assert s.scalar(select(CollectionRun)).finished_at


def test_limits_and_unrecognized(engine):
    first=structured()+'<a rel="next" href="?page=2">Próxima</a>'
    assert collect_source(engine,'human',max_pages=1,client=FakeClient([first]))['truncated']
    assert collect_source(engine,'human',client=FakeClient(['<h1>Busca</h1>']))['status']=='parse_unrecognized'
    with pytest.raises(ValueError):collect_source(engine,'human',max_pages=0)


def test_card_separates_sale_rent_and_neighbors():
    html='''<section><article><a href="/imovel/apartamento-55815"><h2>Spazio</h2></a> Londrina Cód. 55815 R$ 2.100 L R$ 300.000 V 46,65 m² A. Útil 2 Dorm</article>
    <article><a href="/imovel/apartamento-55818"><h2>Trancoso</h2></a> Londrina Cód. 55818 R$ 175.000 V 46,97 m² A. Útil 2 Dorm</article></section>'''
    rows=parse_listings(html,SOURCES['santamerica'].start_url,SOURCES['santamerica'])
    assert {r['id_externo']:r['preco'] for r in rows}=={'55815':'300.000','55818':'175.000'}
    assert all('latitude' not in r for r in rows)


def test_external_pagination_ignored():
    assert links('<a rel="next" href="https://evil.example/">Próxima</a>',SOURCES['human'].start_url,SOURCES['human'])==( [],[])


def test_robots_denial_and_timeout(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('scrapers.transport._reserve',lambda *a,**kw:None)
    monkeypatch.setattr('scrapers.transport.requests.get',lambda *a,**kw:SimpleNamespace(status_code=200,content=b'x',text='User-agent: *\nDisallow: /',headers={}))
    client=PublicClient(('humanimoveis.com',))
    with pytest.raises(CollectionFailure,match='robots'):client.get(SOURCES['human'].start_url)
    assert client.requests_count==1
    import requests
    def timeout(*a,**kw):raise requests.Timeout()
    monkeypatch.setattr('scrapers.transport.requests.get',timeout)
    with pytest.raises(CollectionFailure) as error:PublicClient(('humanimoveis.com',)).get(SOURCES['human'].start_url)
    assert error.value.kind=='network_error'
