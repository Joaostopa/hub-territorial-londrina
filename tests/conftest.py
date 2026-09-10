import os,tempfile
from pathlib import Path
# Test data never touch the user's data directory.
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='hub-tests-')
os.environ['AUTH_REQUIRED']='false'
os.environ.pop('DATABASE_URL',None)
import pytest
from db.models import make_engine,init_db
from sqlalchemy import URL

@pytest.fixture
def engine(tmp_path):
    eng=init_db(make_engine(URL.create('sqlite',database=str(tmp_path/'test.db'))))
    yield eng
    eng.dispose()

@pytest.fixture
def record():
    return {'fonte':'Teste','id_externo':'001','cidade':'Londrina','preco':'520.000,00',
            'area_m2':'100','latitude':-23.3045,'longitude':-51.1696,'finalidade':'venda',
            'data_coleta':'2026-08-01T12:00:00Z','bairro':'Bairro de teste','tipo':'apartamento'}
