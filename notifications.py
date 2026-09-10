"""Entrega opcional. Nada é enviado pelo app; execução exige alerts.py --notify."""
import os,re,ssl,smtplib
from email.message import EmailMessage
import requests
from sqlalchemy import select,delete
from db.models import NotificationTarget,NotificationDelivery,EventoAlerta,session,utcnow

class NotificationError(RuntimeError):
    pass

def save_target(engine,owner,channel,destination):
    destination=destination.strip()
    if channel=='email':
        if len(destination)>250 or not re.fullmatch(r'[^\s@\r\n]+@[^\s@\r\n]+\.[^\s@\r\n]+',destination):
            raise ValueError('Informe um e-mail válido.')
    elif channel=='whatsapp':
        destination=re.sub(r'[\s()+-]','',destination)
        if not re.fullmatch(r'[1-9]\d{7,14}',destination):
            raise ValueError('Informe o número com país e DDD, por exemplo 55 + DDD + número.')
    else:
        raise ValueError('Canal inválido.')
    with session(engine) as s,s.begin():
        target=s.scalar(select(NotificationTarget).where(NotificationTarget.owner==owner,NotificationTarget.channel==channel))
        if target:
            if target.destination != destination:
                target.destination=destination;target.created_at=utcnow()
        else:s.add(NotificationTarget(owner=owner,channel=channel,destination=destination))

def remove_target(engine,owner,channel):
    with session(engine) as s,s.begin():
        ids=list(s.scalars(select(NotificationTarget.id).where(NotificationTarget.owner==owner,NotificationTarget.channel==channel)))
        if ids:s.execute(delete(NotificationDelivery).where(NotificationDelivery.target_id.in_(ids)))
        s.execute(delete(NotificationTarget).where(NotificationTarget.owner==owner,NotificationTarget.channel==channel))

def targets(engine,owner):
    with session(engine) as s:
        return [{'canal':r.channel,'destino':r.destination} for r in s.scalars(select(NotificationTarget).where(NotificationTarget.owner==owner))]

def send_email(destination,message):
    host=os.getenv('SMTP_HOST','');sender=os.getenv('SMTP_FROM','')
    if not host or not sender:raise NotificationError('Configure SMTP_HOST e SMTP_FROM.')
    mail=EmailMessage();mail['From']=sender;mail['To']=destination
    mail['Subject']='Hub Territorial | alerta de área acompanhada'
    mail.set_content(message+'\n\nConsulte a área e os filtros no Hub Territorial.\n')
    try:
        with smtplib.SMTP(host,int(os.getenv('SMTP_PORT','587')),timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'):
                smtp.login(os.environ['SMTP_USER'],os.getenv('SMTP_PASSWORD',''))
            smtp.send_message(mail)
    except (smtplib.SMTPException,OSError,ValueError) as exc:
        raise NotificationError('Falha no envio SMTP: '+type(exc).__name__) from exc

def send_whatsapp(destination,message):
    # Business-initiated sends require an approved template; free-form messages are not used.
    version=os.getenv('WHATSAPP_API_VERSION','')
    phone_id=os.getenv('WHATSAPP_PHONE_NUMBER_ID','')
    token=os.getenv('WHATSAPP_TOKEN','')
    template=os.getenv('WHATSAPP_TEMPLATE','')
    if not (re.fullmatch(r'v\d+\.\d+',version) and phone_id.isdigit() and token and template):
        raise NotificationError('Configure versão, phone number ID, token e template aprovado do WhatsApp Business.')
    payload={'messaging_product':'whatsapp','to':destination,'type':'template',
             'template':{'name':template,'language':{'code':os.getenv('WHATSAPP_LANGUAGE','pt_BR')},
                         'components':[{'type':'body','parameters':[{'type':'text','text':message[:1000]}]}]}}
    try:
        response=requests.post(f'https://graph.facebook.com/{version}/{phone_id}/messages',
                               headers={'Authorization':'Bearer '+token},json=payload,timeout=(8,20))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NotificationError('Falha no WhatsApp Business: '+type(exc).__name__) from exc

def deliver_pending(engine,owner=None):
    """Um processo agendador por banco. Falhas ficam pendentes para a próxima execução."""
    stats={'entregues':0,'falhas':0}
    with session(engine) as s:
        query=select(NotificationTarget)
        if owner:query=query.where(NotificationTarget.owner==owner)
        target_rows=s.scalars(query).all()
        for target in target_rows:
            events=s.scalars(select(EventoAlerta).where(EventoAlerta.owner==target.owner,
                            EventoAlerta.criado_em>=target.created_at).order_by(EventoAlerta.id)).all()
            for event in events:
                delivery=s.scalar(select(NotificationDelivery).where(NotificationDelivery.event_id==event.id,
                                   NotificationDelivery.target_id==target.id))
                if delivery and delivery.delivered_at:continue
                if delivery is None:
                    delivery=NotificationDelivery(event_id=event.id,target_id=target.id);s.add(delivery)
                try:
                    (send_email if target.channel=='email' else send_whatsapp)(target.destination,event.mensagem)
                    delivery.delivered_at=utcnow();delivery.last_error=None;stats['entregues']+=1
                except NotificationError as exc:
                    delivery.last_error=str(exc)[:250];stats['falhas']+=1
                s.commit()
    return stats
