"""Coleta catálogos públicos por construtora, sem contatos nem disponibilidade inventada."""
import argparse
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from classify_properties import clean, classify_stage, norm

SOURCES = {
    'Plaenge': 'https://www.plaenge.com.br/imoveis-curitiba',
    'Vectra': 'https://www.vectraconstrutora.com.br/default/imoveis-a-venda/empreendimento-busca',
    'A.Yoshii': 'https://www.ayoshii.com.br/empreendimentos/cidade/curitiba',
}


def make_project(builder, name, url, text, stage_text='', neighborhood=''):
    stage = classify_stage(description=stage_text)
    commercial = 'Pré-lançamento' if 'pre' in norm(stage_text) and 'lancamento' in norm(stage_text) else ('Lançamento' if 'lancamento' in norm(stage_text) else '')
    return dict(id=hashlib.sha256((builder+'|Curitiba|'+norm(name)).encode()).hexdigest()[:20],
                nome=clean(name), construtora=builder, cidade='Curitiba', bairro=clean(neighborhood),
                url=url, fonte='Site oficial '+builder, detalhes=clean(text)[:400],
                estagio=stage['estagio'], estagio_evidencia=clean(stage_text)[:150],
                estagio_origem='Catálogo oficial da construtora', fase_comercial=commercial,
                data_coleta=datetime.now(timezone.utc).isoformat(), tipologias=[], estoque_unidades=None,
                alto_padrao_indicio=builder=='Plaenge',
                alto_padrao_evidencia='Título do catálogo oficial: Apartamentos de Alto Padrão em Curitiba' if builder=='Plaenge' else '')


def parse(builder, markup):
    soup=BeautifulSoup(markup, 'html.parser')
    projects=[]
    if builder == 'Plaenge':
        for item in soup.select('#imoveis .image-box.item'):
            name=item.select_one('h3.title'); detail=item.select_one('.detail p'); link=item.select_one('a[href]'); status=item.select_one('.header-thumb .text')
            if not all([name,detail,link]): continue
            text=detail.get_text(' ',strip=True)
            if 'curitiba' not in norm(text): continue
            neighborhood=re.search(r'Curitiba\s*\|\s*(.*?)\s*Área',text)
            projects.append(make_project(builder,name.get_text(),urljoin(SOURCES[builder],link['href']),text,status.get_text(' ',strip=True) if status else '',neighborhood.group(1) if neighborhood else ''))
    elif builder == 'Vectra':
        for item in soup.select('a[href]'):
            name=item.select_one('.nome-empreendimento h2'); city=item.select_one('.nome-empreendimento h3')
            if name and city and 'curitiba' in norm(city.get_text()):
                projects.append(make_project(builder,name.get_text(),urljoin(SOURCES[builder],item['href']),city.get_text()))
    else:
        # Apenas cartões com cidade explícita; menus e notícias não são empreendimentos.
        for item in soup.select('a[href]'):
            text=clean(item.get_text(' ',strip=True));href=item['href']
            if not re.search(r'/empreendimentos/[^/]+/?$',href) or not re.search(r'Curitiba\s*[,/]\s*PR',text,re.I):continue
            m=re.match(r'(Pré[- ]?\s*Lançamento|lançamento|Pronto para Morar)\s+(.+?)\s+Curitiba\s*[,/]\s*PR',text,re.I)
            if m:projects.append(make_project(builder,m[2],urljoin(SOURCES[builder],href),text,m[1]))
    return list({p['id']:p for p in projects}.values())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('docs/curitiba/empreendimentos.json'))
    p.add_argument('--html-dir',type=Path,help='HTMLs já obtidos: plaenge.html, vectra.html, ayoshii.html')
    args=p.parse_args()
    existing=json.loads(args.output.read_text()) if args.output.exists() else {'version':1,'projects':[]}
    audit=[]
    for builder,url in SOURCES.items():
        try:
            if args.html_dir:
                filename={'Plaenge':'plaenge.html','Vectra':'vectra.html','A.Yoshii':'ayoshii.html'}[builder]
                markup=(args.html_dir/filename).read_text()
            else:
                with urllib.request.urlopen(url,timeout=30) as response:markup=response.read().decode('utf-8')
            fresh=parse(builder,markup)
            if not fresh:raise ValueError('Nenhum cartão compatível; catálogo anterior preservado')
            # Ausência não exclui catálogo: paginação ou falha não significa encerramento.
            merged={x['id']:x for x in existing['projects']}
            merged.update({x['id']:x for x in fresh});existing['projects']=list(merged.values())
            audit.append({'construtora':builder,'status':'coletado','registros':len(fresh),'url':url})
        except Exception as exc:
            audit.append({'construtora':builder,'status':'não atualizado','erro':str(exc),'url':url})
    existing.update(updated_at=datetime.now(timezone.utc).isoformat(),coverage='Catálogo parcial de Curitiba; não comprova disponibilidade nem estoque',sources=audit)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(existing,ensure_ascii=False,indent=2))
    print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':main()
