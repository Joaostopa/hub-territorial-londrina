"""Enriquece anúncios por evidências explícitas; não estima vendas nem inventa estoque."""
import argparse
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value or '')) if unicodedata.category(c) != 'Mn').lower()


def clean(value):
    text = re.sub(r'<[^>]+>', ' ', html.unescape(str(value or '')))
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[contato omitido]', text)
    text = re.sub(r'(?:\+?55\s*)?\(?\d{2}\)?[\s.-]*\d{4,5}[\s.-]*\d{4}', '[contato omitido]', text)
    return re.sub(r'\s+', ' ', text).strip()


STAGES = {
    'Na planta': r'\bna planta\b|\bpre[- ]lancamento\b',
    'Em construção': r'\bem construcao\b|\bem obras\b|\bobras em andamento\b',
    'Pronto': r'\bpronto para (?:morar|ocupacao)\b|\bobras? concluidas?\b|\bempreendimento entregue\b',
}
DIRECT = {'under_construction': 'Em construção', 'plan_only': 'Na planta', 'built': 'Pronto'}
BUILDERS = {'Plaenge': r'plaenge', 'Vectra': r'vectra', 'A.Yoshii': r'a\.?\s*yoshii'}


def classify_stage(title='', description='', structured=None):
    if structured in DIRECT:
        return dict(estagio=DIRECT[structured], estagio_origem='Campo construction_status do portal',
                    estagio_evidencia=structured, estagio_confianca='Fonte estruturada')
    raw = clean(str(title or '') + '. ' + str(description or ''))
    text = norm(raw)
    hits = []
    for stage, pattern in STAGES.items():
        for match in re.finditer(pattern, text):
            before = text[max(0, match.start()-90):match.start()]
            # Negação, previsão e menção a outro prédio não são estado atual do imóvel.
            if re.search(r'\b(?:nao|sera|ficara|estara|quando|ficar|estar|ficarao|estarao|proximo|proxima|vizinho|vizinha|ao lado|em frente)\b[^.!?;]{0,75}$', before):
                continue
            if re.search(r'\b(?:foi|era|comprado|adquirido)\b[^.!?;]{0,45}$', before):
                continue
            hits.append((stage, raw[max(0, match.start()-35):match.end()+60]))
    stages = {x[0] for x in hits}
    if len(stages) == 1:
        return dict(estagio=hits[0][0], estagio_origem='Inferência textual; requer conferência',
                    estagio_evidencia=hits[0][1], estagio_confianca='Indício textual')
    return dict(estagio='Não informado', estagio_origem='Texto conflitante' if stages else 'Sem evidência suficiente',
                estagio_evidencia=' | '.join(x[1] for x in hits)[:250], estagio_confianca='Revisar' if stages else 'Não identificado')


def enrich(row, source, catalog):
    result = dict(row)
    content = source.get('content') or {}
    title = content.get('title') or source.get('title') or row.get('titulo', '')
    description = content.get('description') or source.get('description') or ''
    attributes = source.get('attributes') or {}
    result.update(classify_stage(title, description, attributes.get('construction_status')))
    text = norm(clean(str(title) + '. ' + str(description)))
    current = result.get('construtora', '')
    for canonical, alias in BUILDERS.items():
        if re.fullmatch(alias, norm(current).strip()):
            result['construtora'] = canonical
    if not current:
        matches = []
        for builder, alias in BUILDERS.items():
            m = re.search(r'\b(?:construtora|incorporadora|construido pela|empreendimento da|assinatura da|assinado pela)\s+(' + alias + r')\b', text)
            if m and not re.search(r'\b(?:proxim[oa]|vizinh[oa]|ao lado|em frente)\b[^.!?;]{0,70}$', text[max(0,m.start()-80):m.start()]):
                matches.append((builder, m.group(0)))
        if len(matches) == 1:
            result['construtora'], result['construtora_evidencia'] = matches[0]
            result['construtora_origem'] = 'Descrição do anúncio; conferir'
    named = norm(result.get('empreendimento', '')).strip()
    candidates = []
    for project in catalog:
        name = norm(project['nome']).strip()
        aliases = [name, *[norm(a) for a in project.get('aliases', [])]]
        exact = named and named in aliases
        in_title = any(len(a) >= 8 and re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', norm(title)) for a in aliases)
        if (exact or in_title) and (not result.get('construtora') or result['construtora'] == project['construtora']):
            candidates.append(project)
    if len(candidates) == 1:
        project = candidates[0]
        result.update(empreendimento=project['nome'], construtora=project['construtora'],
                      empreendimento_catalogo_id=project['id'], construtora_origem='Nome do empreendimento associado ao catálogo oficial',
                      construtora_evidencia=project['url'])
    luxury = re.search(r'\balto padrao\b|\balto luxo\b|\baltissimo padrao\b', text)
    result['alto_padrao_indicio'] = bool(luxury)
    result['alto_padrao_evidencia'] = clean(str(title)+'. '+str(description))[max(0,luxury.start()-20):luxury.end()+40] if luxury else ''
    result['classificador_versao'] = '1.0'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', required=True, type=Path)
    parser.add_argument('--history', type=Path, default=Path('docs/curitiba/historico.json'))
    parser.add_argument('--catalog', type=Path, default=Path('docs/curitiba/empreendimentos.json'))
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text())
    by_id = {str(x.get('record_id') or (x.get('identity') or {}).get('id') or x.get('listing_id')): x for x in raw}
    history = json.loads(args.history.read_text())
    catalog = json.loads(args.catalog.read_text())['projects']
    counts = Counter()
    for batch in history['batches']:
        if batch.get('run_id') != args.run_id:
            continue
        records = []
        for row in batch['records']:
            updated = enrich(row, by_id.get(str(row['id_externo']), {}), catalog)
            counts[updated['estagio']] += 1
            counts['construtora identificada'] += bool(updated.get('construtora'))
            records.append(updated)
        batch['records'] = records
    temp = args.history.with_suffix('.tmp')
    temp.write_text(json.dumps(history, ensure_ascii=False))
    temp.replace(args.history)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    main()
