"""Coleta limitada e auditável de páginas públicas. python collect_batch.py --help"""
import argparse
import hashlib
import json
from sqlalchemy import select
from db.models import init_db, make_engine, session, CollectionRun, CollectedProject, utcnow
from db.repository import import_records
from scrapers.sources import SOURCES
from scrapers.transport import PublicClient, CollectionFailure
from scrapers.multisource import links, parse_listings, parse_project


def collect_source(engine, key, *, max_pages=3, max_records=100, client=None):
    if not 1 <= max_pages <= 20 or not 1 <= max_records <= 1000:
        raise ValueError('Limites: 1–20 páginas e 1–1000 anúncios.')
    source = SOURCES[key]
    client = client or PublicClient(source.domains)
    with session(engine) as s:
        run = CollectionRun(source=source.name, city='Londrina')
        s.add(run); s.commit()
        run_id, observed = run.id, run.started_at
    stats = dict(status='running', pages=0, requests=0, found=0, inserted=0,
                 rejected=0, geolocated=0, truncated=False, detail='')
    queue, visited, fingerprints, identities = [source.start_url], set(), set(), set()
    try:
        while queue and stats['pages'] < max_pages and stats['found'] < max_records:
            url = queue.pop(0)
            if url in visited: continue
            visited.add(url)
            page = client.get(url)
            stats['pages'] += 1
            digest = hashlib.sha256(page.text.encode()).hexdigest()
            if digest in fingerprints: continue
            fingerprints.add(digest)
            details, following = links(page.text, page.url, source)
            if source.kind == 'empreendimentos':
                project = parse_project(page.text, page.url, source)
                if project:
                    with session(engine) as s:
                        existing = s.scalar(select(CollectedProject).where(CollectedProject.fonte==source.name, CollectedProject.url==page.url))
                        if existing:
                            existing.nome=project['nome'];existing.observado_em=observed
                        else: s.add(CollectedProject(**project, observado_em=observed));stats['inserted']+=1
                        s.commit()
                    stats['found'] += 1
                queue.extend(x for x in details + following if x not in visited and x not in queue)
            else:
                rows = parse_listings(page.text, page.url, source)
                fresh = [r for r in rows if str(r['id_externo']) not in identities]
                remaining = max_records - stats['found']
                if len(fresh) > remaining: stats['truncated'] = True
                fresh = fresh[:remaining]
                for row in fresh:
                    identities.add(str(row['id_externo']));row['data_coleta']=observed.isoformat()
                result = import_records(engine, fresh)
                stats['found'] += len(fresh)
                stats['inserted'] += result['inseridos']
                stats['rejected'] += result['rejeitados']
                from normalizer import normalize_record
                for row in fresh:
                    try:
                        valid = normalize_record(row)
                        stats['geolocated'] += int(valid.get('latitude') is not None and valid.get('longitude') is not None)
                    except (ValueError, TypeError, OverflowError): pass
                # Follow details only if the search page lacked structured listing data.
                candidates = following + (details if not rows else [])
                queue.extend(x for x in candidates if x not in visited and x not in queue)
        stats['truncated'] = stats['truncated'] or bool(queue)
        stats['status'] = 'success' if stats['found'] and not stats['rejected'] else ('partial' if stats['found'] else 'parse_unrecognized')
        stats['detail'] = 'Limite atingido; cobertura incompleta.' if stats['truncated'] else 'Somente páginas visitadas; não representa todo o mercado.'
        if not stats['found']: stats['detail'] = 'Nenhum registro reconhecido; não significa ausência de imóveis. Revise o adaptador com HTML autorizado.'
    except CollectionFailure as exc:
        stats['status'] = 'partial' if stats['inserted'] else exc.kind
        stats['detail'] = f'{exc.kind}: {exc}'
    except Exception as exc:
        stats['status'] = 'partial' if stats['inserted'] else 'error'
        stats['detail'] = f'Erro {type(exc).__name__}; revise o adaptador. Registros já gravados foram preservados.'
    finally:
        stats['requests'] = client.requests_count
        with session(engine) as s:
            run = s.get(CollectionRun, run_id)
            for field, value in stats.items(): setattr(run, field, value)
            run.finished_at = utcnow();s.commit()
    return dict(id=run_id, fonte=source.name, **stats)


def main():
    parser=argparse.ArgumentParser(description='Piloto: venda de apartamentos em Londrina e empreendimentos Yticon.')
    parser.add_argument('--sources', nargs='+', choices=list(SOURCES), default=['santamerica','human','monaco'])
    parser.add_argument('--max-pages',type=int,default=3)
    parser.add_argument('--max-records',type=int,default=100)
    parser.add_argument('--output',default='diagnostico_coleta.json')
    args=parser.parse_args()
    engine=init_db(make_engine())
    results=[]
    for key in args.sources:
        print(f'Consultando {SOURCES[key].name}...',flush=True)
        results.append(collect_source(engine,key,max_pages=args.max_pages,max_records=args.max_records))
        print(json.dumps(results[-1],ensure_ascii=False),flush=True)
    from pathlib import Path
    Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(r['status']=='success' for r in results) else 2

if __name__=='__main__': raise SystemExit(main())
