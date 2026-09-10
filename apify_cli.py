"""CLI: execução explícita e rotina semanal retomável; token vem do .env."""
import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from config import DATA_DIR
from db.models import init_db, make_engine, session, ApifyRun
from connectors.apify import ApifyError
from apify_service import start, sync

@contextmanager
def exclusive():
    path=DATA_DIR/'apify-weekly.lock'
    with path.open('a+b') as handle:
        handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
        try:
            if __import__('os').name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise ApifyError('Outra rotina semanal já está em execução.') from None
        try:
            yield
        finally:
            if __import__('os').name=='nt':
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def backup(engine):
    if engine.dialect.name!='sqlite':
        raise ApifyError('Backup automático desta rotina exige SQLite. Configure backup PostgreSQL antes de usar outro banco.')
    target=DATA_DIR/'backups';target.mkdir(exist_ok=True)
    path=target/('imoveis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.db')
    raw=engine.raw_connection()
    try:
        with sqlite3.connect(path) as dest:
            raw.driver_connection.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ApifyError('Backup não passou na verificação de integridade.')
    finally: raw.close()
    return path

def weekly(engine,business,limit):
    # A persistent checkpoint avoids duplicate paid starts after timeouts / restarts.
    with exclusive():
        checkpoint=DATA_DIR/('apify-weekly-'+business+'.json')
        state=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        now=datetime.now(timezone.utc)
        week=now.strftime('%G-W%V')
        if state.get('week')==week and state.get('done'):
            return {'status':'SEMANA_JA_CONCLUIDA'}
        if state.get('uncertain'):
            raise ApifyError('Início anterior sem confirmação. Confira o Console Apify e siga APIFY_LONDRINA.md antes de iniciar outra cobrança.')
        run_id=state.get('run_id') if not state.get('done') else None
        if not run_id:
            backup(engine)
            state={'week':week,'uncertain':True,'done':False}
            checkpoint.write_text(json.dumps(state),encoding='utf-8')
            run_id=start(engine,business,limit)
            state.update(run_id=run_id,uncertain=False)
            checkpoint.write_text(json.dumps(state),encoding='utf-8')
        for _ in range(180):
            result=sync(engine,run_id)
            print(json.dumps({'run_id':run_id,**result},ensure_ascii=False),flush=True)
            if result['status'] in ('IMPORTADO','JA_IMPORTADO'):
                state['done']=True
                checkpoint.write_text(json.dumps(state),encoding='utf-8')
                backup(engine)
                return result
            if result['status'] in ('FAILED','ABORTED','TIMED-OUT'):
                raise ApifyError('Execução terminou com falha. Nenhuma nova cobrança será iniciada automaticamente; confira o Console e o checkpoint.')
            time.sleep(15)
        raise ApifyError('Tempo de espera local encerrado. Execute novamente para retomar o mesmo run_id.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','sync','weekly','backup'])
    parser.add_argument('--business',choices=['SALE','RENTAL'],default='SALE')
    parser.add_argument('--max-items',type=int,default=100)
    parser.add_argument('--run-id')
    args=parser.parse_args()
    engine=init_db(make_engine())
    try:
        if args.action=='start': result={'run_id':start(engine,args.business,args.max_items)}
        elif args.action=='sync': result=sync(engine,args.run_id or '')
        elif args.action=='weekly': result=weekly(engine,args.business,args.max_items)
        else: result={'backup':str(backup(engine))}
        print(json.dumps(result,ensure_ascii=False))
    except (ApifyError,ValueError,SQLAlchemyError) as exc:
        # Never print DB parameters or remote response bodies, which may contain secrets.
        print(str(exc) if isinstance(exc,ApifyError) else 'Erro local de validação ou banco; nenhuma importação parcial foi confirmada.')
        raise SystemExit(1)

if __name__=='__main__': main()
