import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from classify_properties import classify_stage, enrich
from apify_imovelweb import normalize, import_items
from collect_builders import parse


class MarketPipeline(unittest.TestCase):
    def test_stage_evidence_and_negation(self):
        self.assertEqual(classify_stage(description='Apartamento em construção')['estagio'],'Em construção')
        for text in ['Ainda não está pronto para morar','Será entregue pronto para morar em 2029',
                     'Próximo ao empreendimento em construção','Foi comprado na planta em 2010',
                     'Temos unidades na planta e pronto para morar']:
            with self.subTest(text=text):self.assertEqual(classify_stage(description=text)['estagio'],'Não informado')
        self.assertEqual(classify_stage(description='Lançamento 2026')['estagio'],'Não informado')
        self.assertEqual(classify_stage(structured='plan_only')['estagio'],'Na planta')

    def test_builder_is_not_neighbor_or_advertiser(self):
        row={'titulo':'Apartamento','construtora':''}
        self.assertEqual(enrich(row,{'description':'Empreendimento da Plaenge'},[])['construtora'],'Plaenge')
        self.assertEqual(enrich(row,{'description':'Ao lado da construtora Plaenge'},[])['construtora'],'')
        self.assertEqual(enrich(row,{'advertiser':'Plaenge'},[])['construtora'],'')

    def test_imovelweb_validation_price_and_id(self):
        item={'url':'https://www.imovelweb.com.br/propriedades/apartamento-123.html?tracking=x','city':'Curitiba','state':'PR','currency':'BRL','price':'R$ 1.500.000','area_m2':'123,5','title':'Apartamento em construção','description':'Construtora Plaenge'}
        r=normalize(item,'venda','2026-09-30T19:00:00Z',[])
        self.assertEqual(r['preco'],1500000);self.assertEqual(r['area_m2'],123.5)
        self.assertEqual(r['construtora'],'Plaenge');self.assertEqual(r['estagio'],'Em construção')
        self.assertNotIn('tracking',r['url'])
        self.assertIsNone(normalize({**item,'city':'Londrina'},'venda','2026-09-30T19:00:00Z',[]))
        self.assertIsNone(normalize({**item,'city':None},'venda','2026-09-30T19:00:00Z',[]))

    def test_empty_import_preserves_history(self):
        with tempfile.TemporaryDirectory() as d:
            history=Path(d)/'history.json';catalog=Path(d)/'catalog.json'
            history.write_text('{"batches":[]}');catalog.write_text('{"projects":[]}')
            with self.assertRaises(ValueError):import_items([], 'venda','run','2026-09-30T19:00:00Z',history,catalog)
            self.assertEqual(history.read_text(),'{"batches":[]}')

    def test_catalog_scope(self):
        html='<a href="/londrina"><div class="nome-empreendimento"><h2>Outro</h2><h3>Londrina/PR</h3></div></a><a href="/curitiba"><div class="nome-empreendimento"><h2>Euro Building</h2><h3>Curitiba/PR</h3></div></a>'
        rows=parse('Vectra',html)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['nome'],'Euro Building')
        self.assertIsNone(rows[0]['estoque_unidades'])


if __name__=='__main__':unittest.main()
