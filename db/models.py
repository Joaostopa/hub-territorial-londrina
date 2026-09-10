"""Esquema v2; create_all inicializa bancos novos, sem apagar dados existentes."""
from sqlalchemy import (Column, Integer, Float, String, Text, DateTime, Boolean,
                        UniqueConstraint, Index, create_engine, event, inspect, URL)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
from config import DATABASE_URL, DATA_DIR

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Imovel(Base):
    __tablename__ = 'imoveis'
    id = Column(Integer, primary_key=True)
    fonte = Column(String(80), nullable=False)
    id_externo = Column(String(160), nullable=False)
    data_coleta = Column(DateTime, nullable=False, default=utcnow)
    titulo = Column(String(300), nullable=False, default='Imóvel')
    url = Column(Text, nullable=True)
    cidade = Column(String(100), nullable=False)
    bairro = Column(String(160))
    finalidade = Column(String(20), nullable=False, default='venda')
    tipo = Column(String(60), nullable=False, default='outro')
    preco = Column(Float, nullable=False)
    area_m2 = Column(Float)
    preco_m2 = Column(Float)
    quartos = Column(Integer)
    vagas = Column(Integer)
    latitude = Column(Float)
    longitude = Column(Float)
    geo_precisao = Column(String(30), nullable=False, default='nao_informada')
    is_demo = Column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint('fonte', 'id_externo', 'data_coleta', name='uq_snapshot'),
        Index('ix_imoveis_latest', 'fonte', 'id_externo', 'data_coleta'),
        Index('ix_imoveis_city_geo', 'cidade', 'latitude', 'longitude'),
    )

class AreaFavorita(Base):
    __tablename__ = 'areas_favoritas'
    id = Column(Integer, primary_key=True)
    owner = Column(String(250), nullable=False)
    nome = Column(String(120), nullable=False)
    cidade = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    raio_km = Column(Float, nullable=False)
    filtros_json = Column(Text, nullable=False, default='{}')
    criado_em = Column(DateTime, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint('owner', 'nome', name='uq_owner_area'),)

class Concorrente(Base):
    __tablename__ = 'concorrentes'
    id = Column(Integer, primary_key=True)
    nome = Column(String(180), nullable=False)
    incorporadora = Column(String(160), nullable=False)
    cidade = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    status = Column(String(60), nullable=False)
    unidades = Column(Integer)
    preco_m2 = Column(Float)
    criado_em = Column(DateTime, nullable=False, default=utcnow)

class Alerta(Base):
    __tablename__ = 'alertas'
    id = Column(Integer, primary_key=True)
    area_id = Column(Integer, nullable=False, unique=True)
    owner = Column(String(250), nullable=False)
    limite_pct = Column(Float, nullable=False, default=10)
    ultimo_snapshot = Column(Text)
    ultima_checagem = Column(DateTime)

class EventoAlerta(Base):
    __tablename__ = 'eventos_alerta'
    id = Column(Integer, primary_key=True)
    owner = Column(String(250), nullable=False)
    area_id = Column(Integer, nullable=False)
    mensagem = Column(Text, nullable=False)
    criado_em = Column(DateTime, nullable=False, default=utcnow)

class Relatorio(Base):
    __tablename__ = 'relatorios'
    id = Column(Integer, primary_key=True)
    owner = Column(String(250), nullable=False)
    cidade = Column(String(100), nullable=False)
    area_json = Column(Text, nullable=False)
    filtros_json = Column(Text, nullable=False)
    quantidade = Column(Integer, nullable=False)
    criado_em = Column(DateTime, nullable=False, default=utcnow)

class SchemaMismatch(RuntimeError):
    pass

def make_engine(url=None):
    target = url or DATABASE_URL or URL.create('sqlite', database=str(DATA_DIR / 'imoveis.db'))
    engine = create_engine(target, pool_pre_ping=True,
                           connect_args={'check_same_thread': False, 'timeout': 30}
                           if str(target).startswith('sqlite') else {})
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def pragmas(dbapi_connection, _):
            cur = dbapi_connection.cursor()
            cur.execute('PRAGMA journal_mode=WAL')
            cur.execute('PRAGMA foreign_keys=ON')
            cur.close()
    return engine

def init_db(engine):
    # Refuse to silently operate on an incompatible legacy table.
    inspector = inspect(engine)
    if inspector.has_table('imoveis'):
        actual = {c['name'] for c in inspector.get_columns('imoveis')}
        required = {c.name for c in Imovel.__table__.columns}
        if required - actual:
            raise SchemaMismatch('Banco anterior incompatível. Colunas ausentes: '
                                 + ', '.join(sorted(required - actual))
                                 + '. Faça backup e use migrate_legacy.py; não apague o banco.')
    Base.metadata.create_all(engine)
    return engine

def session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)()

class NotificationTarget(Base):
    __tablename__ = 'notification_targets'
    id = Column(Integer,primary_key=True)
    owner = Column(String(250),nullable=False)
    channel = Column(String(20),nullable=False)
    destination = Column(String(250),nullable=False)
    created_at = Column(DateTime,nullable=False,default=utcnow)
    __table_args__ = (UniqueConstraint('owner','channel',name='uq_target_owner_channel'),)

class NotificationDelivery(Base):
    __tablename__ = 'notification_deliveries'
    id = Column(Integer,primary_key=True)
    event_id = Column(Integer,nullable=False)
    target_id = Column(Integer,nullable=False)
    delivered_at = Column(DateTime)
    last_error = Column(String(250))
    __table_args__ = (UniqueConstraint('event_id','target_id',name='uq_delivery'),)

class CollectionRun(Base):
    __tablename__ = 'collection_runs'
    id = Column(Integer,primary_key=True)
    source = Column(String(80),nullable=False)
    city = Column(String(100),nullable=False)
    started_at = Column(DateTime,nullable=False,default=utcnow)
    finished_at = Column(DateTime)
    status = Column(String(40),nullable=False,default='running')
    pages = Column(Integer,nullable=False,default=0)
    requests = Column(Integer,nullable=False,default=0)
    found = Column(Integer,nullable=False,default=0)
    inserted = Column(Integer,nullable=False,default=0)
    rejected = Column(Integer,nullable=False,default=0)
    geolocated = Column(Integer,nullable=False,default=0)
    truncated = Column(Boolean,nullable=False,default=False)
    detail = Column(Text,nullable=False,default='')

class CollectedProject(Base):
    __tablename__ = 'empreendimentos_coletados'
    id = Column(Integer,primary_key=True)
    fonte = Column(String(80),nullable=False)
    url = Column(Text,nullable=False)
    nome = Column(String(200),nullable=False)
    cidade = Column(String(100),nullable=False)
    areas_m2_json = Column(Text,nullable=False,default='[]')
    observado_em = Column(DateTime,nullable=False,default=utcnow)
    __table_args__=(UniqueConstraint('fonte','url',name='uq_collected_project'),)


class ApifyRun(Base):
    __tablename__ = 'apify_runs'
    run_id = Column(String(100), primary_key=True)
    dataset_id = Column(String(100))
    business = Column(String(20), nullable=False)
    input_json = Column(Text, nullable=False)
    started_at = Column(DateTime, nullable=False)
    status = Column(String(40), nullable=False)
    imported_at = Column(DateTime)
    item_count = Column(Integer, default=0)
    accepted = Column(Integer, default=0)
    rejected = Column(Integer, default=0)
    detail = Column(Text, default='')

class ApifyObservation(Base):
    __tablename__ = 'apify_observations'
    id = Column(Integer, primary_key=True)
    run_id = Column(String(100), nullable=False)
    portal = Column(String(20), nullable=False)
    listing_id = Column(String(100), nullable=False)
    business = Column(String(20), nullable=False)
    observed_at = Column(DateTime, nullable=False)
    payload_json = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint('run_id','portal','listing_id','business',name='uq_apify_observation'),)
