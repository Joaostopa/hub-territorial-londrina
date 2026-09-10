"""Apify: chamadas explícitas, sem repetir POST de execução automaticamente."""
import os
import re
import requests

ACTOR = 'jungle_synthesizer~brazil-vivareal-zap-imoveis-scraper'
API = 'https://api.apify.com/v2'

class ApifyError(RuntimeError):
    pass

def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', str(value)):
        raise ApifyError('Identificador Apify inválido.')
    return str(value)

def londrina_input(business='SALE', max_items=100):
    if business not in ('SALE','RENTAL') or not 1 <= int(max_items) <= 10000:
        raise ApifyError('Use SALE/RENTAL e limite entre 1 e 10000 anúncios.')
    return dict(portal='BOTH', business=business, propertyType='', state='PR', city='Londrina', maxItems=int(max_items))

class Client:
    def __init__(self, token=None):
        self.token = token or os.getenv('APIFY_TOKEN','').strip()
        if not self.token:
            raise ApifyError('Configure APIFY_TOKEN no arquivo .env e reinicie o aplicativo.')
        self.http = requests.Session()
        self.http.headers['Authorization'] = 'Bearer ' + self.token

    def request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, API + path, timeout=(10,60), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise ApifyError('Falha de conexão com Apify. Se estava iniciando uma coleta, confira Runs no Console antes de repetir: ela pode ter iniciado.') from None
        if not 200 <= response.status_code < 300:
            raise ApifyError(f'Apify HTTP {response.status_code}. Confira token, saldo e permissões no Console.')
        try:
            return response.json()
        except ValueError:
            raise ApifyError('Resposta Apify não é JSON válido.') from None

    def start(self, inputs):
        return self.request('POST', f'/acts/{ACTOR}/runs', json=inputs, params={'timeout':3600})['data']

    def run(self, run_id):
        result = self.request('GET', '/actor-runs/' + identifier(run_id))['data']
        actor = self.request('GET', '/acts/' + ACTOR)['data']
        if result.get('actId') != actor['id']:
            raise ApifyError('Execução pertence a outro Actor.')
        return result

    def inputs(self, run):
        return self.request('GET', '/key-value-stores/' + identifier(run['defaultKeyValueStoreId']) + '/records/INPUT')

    def items(self, dataset_id):
        offset = 0
        while True:
            page = self.request('GET', '/datasets/' + identifier(dataset_id) + '/items',
                                params={'format':'json','offset':offset,'limit':1000,'clean':'false'})
            if not isinstance(page,list):
                raise ApifyError('Dataset inesperado: esperado array JSON.')
            if not page:
                break
            yield from page
            offset += len(page)
