import json
from datetime import timedelta
import pandas as pd
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from db.models import (Imovel, AreaFavorita, Concorrente, Alerta, EventoAlerta, Relatorio,
                       session, utcnow)
from normalizer import normalize_record
from geoutils import validate_area

PUBLIC_COLUMNS = [c.name for c in Imovel.__table__.columns]

def latest(engine, city=None, as_of=None):
    # Rank before geolocation filtering: a newer record without coordinates must not
    # accidentally resurrect an older geolocated snapshot.
    query = select(*Imovel.__table__.columns,
                   func.row_number().over(partition_by=(Imovel.fonte, Imovel.id_externo),
                     order_by=(Imovel.data_coleta.desc(), Imovel.id.desc())).label('_rank'))
    if as_of is not None:
        query = query.where(Imovel.data_coleta <= as_of)
    ranked = query.subquery()
    statement = select(*[ranked.c[c] for c in PUBLIC_COLUMNS]).where(ranked.c._rank == 1)
    if city:
        statement = statement.where(ranked.c.cidade == city)
    with engine.connect() as conn:
        return pd.read_sql(statement, conn, parse_dates=['data_coleta'])

def filter_listings(df, filters):
    out = df.copy()
    if filters.get('finalidade'):
        out = out[out.finalidade == filters['finalidade']]
    if filters.get('tipos'):
        out = out[out.tipo.isin(filters['tipos'])]
    if filters.get('fontes'):
        out = out[out.fonte.isin(filters['fontes'])]
    if filters.get('preco_min'):
        out = out[out.preco >= filters['preco_min']]
    if filters.get('preco_max'):
        out = out[out.preco <= filters['preco_max']]
    if filters.get('area_min'):
        out = out[out.area_m2 >= filters['area_min']]
    if filters.get('quartos_min'):
        out = out[out.quartos >= filters['quartos_min']]
    if filters.get('max_age_days'):
        out = out[out.data_coleta >= utcnow() - timedelta(days=filters['max_age_days'])]
    return out.dropna(subset=['latitude','longitude'])

def import_records(engine, records, *, demo=False):
    valid, errors = [], []
    for line, record in enumerate(records, start=2):
        try:
            valid.append(normalize_record(record, demo=demo))
        except (ValueError, TypeError, OverflowError) as exc:
            errors.append({'linha': line, 'erro': str(exc)})
    added = duplicates = 0
    with session(engine) as s:
        with s.begin():
            for row in valid:
                exists = s.scalar(select(Imovel.id).where(Imovel.fonte == row['fonte'],
                                  Imovel.id_externo == row['id_externo'],
                                  Imovel.data_coleta == row['data_coleta']))
                if exists:
                    duplicates += 1
                    continue
                # Savepoint makes concurrent duplicate imports harmless.
                try:
                    with s.begin_nested():
                        s.add(Imovel(**row))
                        s.flush()
                    added += 1
                except IntegrityError:
                    duplicates += 1
    return {'inseridos': added, 'duplicados': duplicates, 'rejeitados': len(errors), 'erros': errors}

def favorites(engine, owner):
    with session(engine) as s:
        rows = s.scalars(select(AreaFavorita).where(AreaFavorita.owner == owner).order_by(AreaFavorita.nome)).all()
        return [{c.name: getattr(r,c.name) for c in AreaFavorita.__table__.columns} for r in rows]

def save_favorite(engine, owner, name, city, area, filters):
    name = name.strip()
    if not name or len(name) > 120:
        raise ValueError('Informe um nome de 1 a 120 caracteres.')
    lat, lon, radius = validate_area(*area)
    with session(engine) as s, s.begin():
        row = s.scalar(select(AreaFavorita).where(AreaFavorita.owner == owner, AreaFavorita.nome == name))
        if row:
            raise ValueError('Já existe uma área com esse nome. Escolha outro nome.')
        s.add(AreaFavorita(owner=owner, nome=name, cidade=city, latitude=lat,
                          longitude=lon, raio_km=radius, filtros_json=json.dumps(filters)))

def delete_favorite(engine, owner, area_id):
    with session(engine) as s, s.begin():
        s.execute(delete(Alerta).where(Alerta.area_id == area_id, Alerta.owner == owner))
        s.execute(delete(EventoAlerta).where(EventoAlerta.area_id == area_id, EventoAlerta.owner == owner))
        s.execute(delete(AreaFavorita).where(AreaFavorita.id == area_id, AreaFavorita.owner == owner))

def competitors(engine, city):
    with engine.connect() as conn:
        return pd.read_sql(select(Concorrente).where(Concorrente.cidade == city), conn)

def save_competitor(engine, data):
    validate_area(data['latitude'],data['longitude'],1)
    for key in ['nome', 'incorporadora', 'cidade', 'status']:
        data[key] = str(data[key]).strip()
        if not data[key]:
            raise ValueError(f'Preencha {key}.')
    with session(engine) as s, s.begin():
        s.add(Concorrente(**data))

def delete_competitor(engine, record_id):
    with session(engine) as s, s.begin():
        s.execute(delete(Concorrente).where(Concorrente.id == record_id))

def record_report(engine, owner, city, area, filters, count):
    with session(engine) as s, s.begin():
        s.add(Relatorio(owner=owner, cidade=city, area_json=json.dumps(area),
                        filtros_json=json.dumps(filters), quantidade=count))

def report_history(engine, owner):
    with engine.connect() as conn:
        return pd.read_sql(select(Relatorio).where(Relatorio.owner == owner).order_by(Relatorio.criado_em.desc()).limit(100),conn)
