"""Alertas internos persistentes, executáveis pelo Agendador de Tarefas/cron."""
import argparse
import json
from sqlalchemy import select, delete
from db.models import Alerta, AreaFavorita, EventoAlerta, session, utcnow, init_db, make_engine
from db.repository import latest, filter_listings
from geoutils import within_radius

def enable_alert(engine,owner,area_id,threshold):
    if not 1 <= threshold <= 100:
        raise ValueError('Limite deve estar entre 1% e 100%.')
    with session(engine) as s, s.begin():
        area=s.scalar(select(AreaFavorita).where(AreaFavorita.id==area_id,AreaFavorita.owner==owner))
        if not area:
            raise ValueError('Área não encontrada para este usuário.')
        alert=s.scalar(select(Alerta).where(Alerta.area_id==area_id,Alerta.owner==owner))
        if alert:
            alert.limite_pct=threshold
        else:
            s.add(Alerta(owner=owner,area_id=area_id,limite_pct=threshold))

def disable_alert(engine,owner,area_id):
    with session(engine) as s,s.begin():
        s.execute(delete(Alerta).where(Alerta.area_id==area_id,Alerta.owner==owner))

def check_alerts(engine,owner=None):
    events=[]
    with session(engine) as s,s.begin():
        stmt=select(Alerta)
        if owner:
            stmt=stmt.where(Alerta.owner==owner)
        for alert in s.scalars(stmt).all():
            area=s.scalar(select(AreaFavorita).where(AreaFavorita.id==alert.area_id,AreaFavorita.owner==alert.owner))
            if not area:
                continue
            frame=within_radius(filter_listings(latest(engine,area.cidade),json.loads(area.filtros_json)),area.latitude,area.longitude,area.raio_km)
            median=frame.preco_m2.dropna().median()
            import pandas as pd
            current={'ids':sorted(f'{r.fonte}:{r.id_externo}' for r in frame.itertuples()),
                     'mediana':float(median) if pd.notna(median) else None,'n':len(frame)}
            if alert.ultimo_snapshot:
                previous=json.loads(alert.ultimo_snapshot)
                added=set(current['ids'])-set(previous['ids'])
                messages=[]
                if added:
                    messages.append(f'{len(added)} anúncio(s) entraram na amostra filtrada')
                if current['n'] >= 5 and previous['n'] >= 5 and current['mediana'] is not None and previous['mediana']:
                    change=(current['mediana']/previous['mediana']-1)*100
                    if abs(change)>=alert.limite_pct:
                        messages.append(f'mediana do preço/m² variou {change:+.1f}% (composição da amostra pode ter mudado)')
                if messages:
                    message=area.nome+': '+'; '.join(messages)+'.'
                    s.add(EventoAlerta(owner=alert.owner,area_id=area.id,mensagem=message))
                    events.append(message)
            alert.ultimo_snapshot=json.dumps(current)
            alert.ultima_checagem=utcnow()
    return events

def events_for(engine,owner):
    import pandas as pd
    with engine.connect() as conn:
        return pd.read_sql(select(EventoAlerta).where(EventoAlerta.owner==owner).order_by(EventoAlerta.criado_em.desc()).limit(200),conn)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Atualiza alertas internos; não envia mensagens externas.')
    parser.add_argument('--owner')
    parser.add_argument('--notify',action='store_true',help='Envia pendências aos destinos opt-in cadastrados; exige credenciais.')
    args=parser.parse_args()
    engine=init_db(make_engine())
    for event in check_alerts(engine,args.owner):
        print(event)
    if args.notify:
        from notifications import deliver_pending
        print(deliver_pending(engine,args.owner))
