"""Casos sintéticos exclusivamente de teste; não integram a base publicada."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('curitiba',Path(__file__).resolve().parents[1]/'curitiba_pipeline.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

def ad(**kw):
    r=dict(listing_id='test-id',portal='VIVAREAL',business='SALE',property_type='APARTMENT',address_city='Curitiba',address_state_acronym='PR',address_neighborhood='Bacacheri',address_street='Rua Teste',address_number='10',address_zipcode='82510000',url='https://www.vivareal.com.br/imovel/teste',price=500000,price_currency='BRL',area_useful=60,latitude=None,longitude=None,title='Apartamento',scraped_at='2026-09-01T12:00:00Z')
    r.update(kw);return r

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.db=c.connect(self.path/'db.sqlite')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_city_purpose_and_type(self):
        for kw in [dict(address_city='Londrina'),dict(property_type='HOME'),dict(business='RENTAL',rental_period='DAILY'),dict(price_currency='USD'),dict(url='https://evil.example/x'),dict(scraped_at='ontem')]:
            with self.assertRaises(ValueError):c.normalize(ad(**kw))
        self.assertEqual(c.normalize(ad(business='RENTAL',rental_period='MONTHLY'))['finalidade'],'aluguel')
    def test_no_contacts_or_false_coordinates(self):
        r=c.normalize(ad(publisher_email='secret@example.test',publisher_phone='41999999999',latitude=-23.3,longitude=-51.1,title='Contate secret@example.test'))
        self.assertNotIn('secret',json.dumps(r));self.assertIsNone(r['latitude'])
    def test_stages_require_unambiguous_evidence(self):
        self.assertEqual(c.stage(ad(title='Apartamento na planta'))[0],'Na planta')
        self.assertEqual(c.stage(ad(title='Apartamento em construção'))[0],'Em construção')
        self.assertEqual(c.stage(ad(title='Pronto para morar'))[0],'Pronto')
        self.assertEqual(c.stage(ad(title='Não pronto para morar'))[0],'Não informado')
        self.assertEqual(c.stage(ad(listing_type='USED'))[0],'Não informado')
        self.assertEqual(c.stage(ad(title='Na planta ou pronto para morar'))[0],'Não informado')
    def test_history_and_idempotency(self):
        c.import_records(self.db,[ad()],'one');c.import_records(self.db,[ad()],'one')
        c.import_records(self.db,[ad(price=520000,scraped_at='2026-09-02T12:00:00Z')],'two')
        self.assertEqual(self.db.execute('select count(*) from ctb_observations').fetchone()[0],2)
        self.assertEqual(c.latest(self.db)[0]['preco'],520000)
    def test_duplicate_portals_not_double_inventory(self):
        c.import_records(self.db,[ad(),ad(portal='ZAP',url='https://www.zapimoveis.com.br/imovel/teste')],'one')
        result=c.export(self.db,self.path/'export');self.assertEqual(result['records'],1);self.assertEqual(result['portal_records'],2)
    def test_3000_records_are_handled(self):
        rows=[ad(listing_id=str(i)) for i in range(3000)]
        self.assertEqual(c.import_records(self.db,rows,'synthetic-load-test')['accepted'],3000)
        summary=c.export(self.db,self.path/'out');self.assertEqual(summary['records'],3000);self.assertTrue(summary['target_reached'])
    def test_budget_and_no_repeat_post(self):
        with patch.dict(os.environ,{'APIFY_TOKEN':'TEST_ONLY'}),patch.object(c,'api',return_value={'data':{'id':'run-sale','status':'RUNNING'}}) as call:
            a=c.start_job(self.db,'SALE');b=c.start_job(self.db,'SALE');self.assertEqual(a['id'],b['id']);self.assertEqual(call.call_count,1)
            self.assertIn('maxTotalChargeUsd=4',call.call_args.args[0])
        self.db.execute('update intel_budget set reservado=8');self.db.commit()
        with patch.dict(os.environ,{'APIFY_TOKEN':'TEST_ONLY'}),patch.object(c,'api') as call:
            with self.assertRaises(RuntimeError):c.start_job(self.db,'RENTAL')
            call.assert_not_called()
    def test_uncertain_post_is_not_retried(self):
        with patch.dict(os.environ,{'APIFY_TOKEN':'TEST_ONLY'}),patch.object(c,'api',side_effect=RuntimeError('offline')) as call:
            with self.assertRaises(RuntimeError):c.start_job(self.db,'SALE')
            job=c.start_job(self.db,'SALE');self.assertIsNone(job['run_id']);self.assertEqual(call.call_count,1)
        self.assertEqual(self.db.execute('select reservado from intel_budget').fetchone()[0],4)
    def test_geocode_rejects_city_centroids_and_mismatches(self):
        x=c.normalize(ad());result=dict(city='Curitiba',country_code='br',lat=-25.4,lon=-49.23,result_type='city',rank={'confidence':1})
        self.assertIsNone(c.geocode_result(x,{'results':[result]}))
        result.update(result_type='building',street='Rua Teste',housenumber='10')
        self.assertIsNotNone(c.geocode_result(x,{'results':[result]}))
        result['housenumber']='20';self.assertIsNone(c.geocode_result(x,{'results':[result]}))
        result.update(result_type='street',street='Rua Teste');self.assertIn('Rua aproximada',c.geocode_result(x,{'results':[result]})['geo_precisao'])
    def test_geocoder_cache_and_call_budget(self):
        c.import_records(self.db,[ad(),ad(listing_id='second')],'one')
        with patch.dict(os.environ,{'GEOAPIFY_API_KEY':'TEST_ONLY'}),patch.object(c,'request',return_value={'results':[]}) as call,patch.object(c.time,'sleep'):
            c.geocode(self.db,100);c.geocode(self.db,100);self.assertEqual(call.call_count,1)
    def test_backup(self):
        c.import_records(self.db,[ad()],'one')
        with patch.dict(os.environ,{'DATA_DIR':str(self.path)}):path=c.backup(self.db)
        copy=c.sqlite3.connect(path);self.assertEqual(copy.execute('select count(*) from ctb_observations').fetchone()[0],1);copy.close()

if __name__=='__main__':unittest.main()
