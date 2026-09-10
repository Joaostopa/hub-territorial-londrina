"""Inicialização idempotente com a coleta real de referência, sem dados fictícios."""
import json
from pathlib import Path
from db.models import init_db,make_engine
from db.repository import import_records

def prepare():
    engine=init_db(make_engine())
    rows=json.loads((Path(__file__).resolve().parent/'dados_verificados/imoveis_2026-09-08.json').read_text(encoding='utf-8'))
    result=import_records(engine,rows)
    if result['rejeitados']:raise RuntimeError(str(result['erros']))
    print(f"Base real de 08/09/2026: {result['inseridos']} inseridos, {result['duplicados']} já existentes.")
    print('Disponibilidade atual dos anúncios depende de nova consulta. Use iniciar_windows.bat ou F5 no VS Code.')
    return result
if __name__=='__main__':prepare()
