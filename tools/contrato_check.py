"""Protótipo REVISADO do contrato v1.x (rev4) — somente teste, não é a rotina.
Rev4: forma do snapshot, demanda/oth/cands/removed/universo/negativos (ContratoError). Rev3: validação de estrutura e tipos das horas (ContratoError). Rev2 (em relação à rev1): oth consultado no snapshot legado em qualquer posição; docstring sobre Removed. Mudanças da rev1 em relação a contrato_check.py: ver diff. Limitações registradas no fim do arquivo."""
import collections, math

class ContratoError(ValueError):
    """Snapshot incompatível ou inválido: o processamento deve ser interrompido."""

CONTRATOS_SUPORTADOS = frozenset({1})

def _int_estrito(x):
    # bool é subclasse de int: type(x) is int exclui True/False; também exclui 1.0, "1", numpy etc.
    return type(x) is int

def versao(snap):
    """'legado' se o campo 'contrato' não existe; inteiro estrito suportado; caso contrário interrompe.
    Campo presente com valor null/qualquer tipo não inteiro também interrompe (não é 'sem campo')."""
    if not isinstance(snap, dict):
        raise ContratoError(f'snapshot deve ser um objeto, recebido {type(snap).__name__}.')
    if 'contrato' not in snap:
        return 'legado'
    c = snap['contrato']
    if not _int_estrito(c) or c not in CONTRATOS_SUPORTADOS:
        raise ContratoError(f'Contrato {c!r} ({type(c).__name__}) desconhecido: processamento interrompido (incompatibilidade).')
    return c

def _forma(snap, v):
    """P1/P2/P5: chaves obrigatórias e tipos de lista; oth, quando presente, é lista de objetos com 'id'."""
    obrig = ('rows',) if v == 'legado' else ('rows', 'inconc', 'orf')
    for k in obrig:
        if k not in snap: raise ContratoError(f"chave obrigatória '{k}' ausente (contrato {v}).")
        if not isinstance(snap[k], list): raise ContratoError(f"'{k}' deve ser lista, recebido {type(snap[k]).__name__}.")
    if 'oth' in snap:
        if not isinstance(snap['oth'], list): raise ContratoError(f"'oth' deve ser lista, recebido {type(snap['oth']).__name__}.")
        for n, o in enumerate(snap['oth']):
            if not isinstance(o, dict) or 'id' not in o: raise ContratoError(f'oth[{n}]: item malformado (esperado objeto com campo id): {o!r}')

def _cand_id(cat, i, x):
    """Candidata = int estrito (forma simples) ou objeto {'id': int estrito, 't': texto opcional} (forma gravada pelo gerador)."""
    cid = x.get('id') if isinstance(x, dict) else x
    if not _int_estrito(cid):
        raise ContratoError(f'{cat} id={i} campo=cands: ID de candidata não inteiro: {cid!r} ({type(cid).__name__}).')
    if isinstance(x, dict) and 't' in x and not isinstance(x['t'], str):
        raise ContratoError(f"{cat} id={i} campo=cands: título da candidata {cid} deve ser texto.")
    return cid

def _checar_cands(cat, i, d):
    """P8: cands (quando presente) = lista não vazia de candidatas válidas, sem repetição; tier (quando presente) = texto."""
    if 'cands' in d:
        c = d['cands']
        if not isinstance(c, list) or not c: raise ContratoError(f'{cat} id={i} campo=cands: esperado lista não vazia, recebido {c!r}.')
        ids = [_cand_id(cat, i, x) for x in c]
        if len(set(ids)) != len(ids): raise ContratoError(f'{cat} id={i} campo=cands: candidatas repetidas: {ids!r}.')
    if 'tier' in d and not isinstance(d['tier'], str):
        raise ContratoError(f"{cat} id={i} campo=tier: esperado texto, recebido {d['tier']!r} ({type(d['tier']).__name__}).")

def _ids_snapshot(snap, versao_):
    """Lista (categoria, id, demanda) validando forma, IDs inteiros estritos e demanda inteira estrita. Não deduplica."""
    _forma(snap, versao_)
    out = []
    for n, r in enumerate(snap['rows']):
        if not isinstance(r, (list, tuple)) or len(r) < 2:
            raise ContratoError(f'rows[{n}]: registro malformado (esperado lista com ao menos id e demanda): {r!r}')
        out.append(('rows', r[0], r[1]))
    if versao_ != 'legado':
        for cat in ('inconc', 'orf'):
            for n, d in enumerate(snap[cat]):
                if not isinstance(d, dict) or 'id' not in d:
                    raise ContratoError(f'{cat}[{n}]: registro malformado (esperado objeto com campo id): {d!r}')
                out.append((cat, d['id'], None))
    for cat, i, dm in out:
        if not _int_estrito(i):
            raise ContratoError(f'ID não inteiro em {cat}: {i!r} ({type(i).__name__}); leitura interrompida.')
        if cat == 'rows' and not _int_estrito(dm):
            raise ContratoError(f'rows id={i} campo=demanda: valor {dm!r} ({type(dm).__name__}) inválido; esperado int estrito.')
    if versao_ != 'legado':
        for cat in ('inconc', 'orf'):
            for d in snap[cat]: _checar_cands(cat, d['id'], d)
    return out

def cat_map(snap):
    """id -> (categoria, demanda). Interrompe se algum ID aparecer mais de uma vez (mesma categoria ou entre categorias).
    Em snapshot legado só 'rows' é conhecido: o resto é DESCONHECIDO, não 'inexistente'."""
    v = versao(snap)
    m = {}
    for cat, i, d in _ids_snapshot(snap, v):
        if i in m:
            raise ContratoError(f'ID {i} duplicado ({m[i][0]} e {cat}); leitura interrompida.')
        m[i] = (cat, d)
    return m, v

NOTA_OTH_ANT='evidência complementar: ID presente em oth do legado anterior (classificação inalterada)'
NOTA_OTH_ATU='evidência complementar: ID presente em oth do legado atual (classificação inalterada)'

def _oth_ids(snap):
    return {o['id'] for o in snap.get('oth', []) if _int_estrito(o.get('id'))}

def _transicao_c1(a, b):
    """Regras aprovadas (ambos contrato 1). a,b = (cat,dem) ou None (ausente/Removed)."""
    if a is None and b is None: return None
    if a is None: return 'entrada de escopo'
    if b is None: return 'saída de escopo'
    (ca, da), (cb, db) = a, b
    if ca == 'rows' and cb == 'rows': return None if da == db else 'reassociação entre demandas'
    if ca == 'rows': return 'perda de associação'
    if cb == 'rows': return 'associação recuperada'
    return None if ca == cb else 'mudança de classificação da qualidade'

def _removed_validado(removed):
    """P6: None = conjunto vazio; aceita set/frozenset/list/tuple de int estritos."""
    if removed is None: return frozenset()
    if not isinstance(removed, (set, frozenset, list, tuple)):
        raise ContratoError(f'removed deve ser set/frozenset/list/tuple de IDs inteiros, recebido {type(removed).__name__}.')
    for r in removed:
        if not _int_estrito(r): raise ContratoError(f'ID Removed não inteiro: {r!r} ({type(r).__name__})')
    return frozenset(removed)

def comparar(sa, sb, removed=frozenset()):
    """Compara anterior (sa) e atual (sb) por ID.
    Retorna {'modo','versoes','eventos','notas'}.
    modo: 'contrato1' | 'legado-legado' | 'metodologia' (um dos lados legado, o outro contrato 1).
    Em 'metodologia' nenhuma mudança de associação é resultado definitivo (rótulos 'indicativa').
    'removed': IDs Removed no ADO no momento do snapshot atual (tratados como ausentes no atual).
    O comparador NÃO reconstrói o histórico de Removed: não sabe se uma Task ausente no anterior estava Removed.
    Task ausente no anterior e presente no atual é sempre entrada de escopo (ou não verificável, se o anterior é legado).
    oth (legado) é só evidência complementar: gera nota, nunca altera a classificação do evento."""
    removed = _removed_validado(removed)
    ma, va = cat_map(sa); mb, vb = cat_map(sb)
    ev = collections.defaultdict(list); notas = collections.defaultdict(list)
    la, lb = va == 'legado', vb == 'legado'
    modo = 'legado-legado' if (la and lb) else 'metodologia' if (la or lb) else 'contrato1'
    oth_a = _oth_ids(sa) if la else set()
    oth_b = _oth_ids(sb) if lb else set()   # oth do legado, esteja ele na posição anterior ou atual
    for t in set(ma) | set(mb):
        a = ma.get(t); b = None if t in removed else mb.get(t)
        if a is None and b is None: continue
        # ---- presença / escopo
        if a is None:   # só no atual
            if la:
                ev['entrada não verificável (legado)'].append(t)
                if t in oth_a: notas[NOTA_OTH_ANT].append(t)
            else: ev['entrada de escopo'].append(t)
            continue
        if b is None:   # só no anterior (ou Removed no atual)
            if lb and t not in removed:
                ev['saída não verificável (legado)'].append(t)
                if t in oth_b: notas[NOTA_OTH_ATU].append(t)
            else: ev['saída de escopo'].append(t)
            continue
        # ---- presente nos dois: nunca entrada/saída
        k = _transicao_c1(a, b)
        if k is None: continue
        if modo == 'metodologia':
            k = {'perda de associação': 'possível perda de associação (mudança de metodologia)',
                 'associação recuperada': 'possível associação recuperada (mudança de metodologia)',
                 'reassociação entre demandas': 'reassociação indicativa (mudança de metodologia)',
                 'mudança de classificação da qualidade': 'mudança de classificação (mudança de metodologia)'}[k]
        ev[k].append(t)
    f = lambda d: {k: sorted(v) for k, v in d.items()}
    return {'modo': modo, 'versoes': (va, vb), 'eventos': f(ev), 'notas': f(notas)}

CAMPOS_HORAS = ('est', 'rem', 'cons', 'cw')
ROWS_POS_HORAS = 4          # rows = [id, demanda, estado, responsável, est, rem, cons, cw, iteração]
ROWS_MIN_LEN = ROWS_POS_HORAS + len(CAMPOS_HORAS)   # 8

def _hora_valida(v):
    """int ou float finitos; exclui bool (subclasse de int), str, None, NaN e ±infinito."""
    return type(v) in (int, float) and math.isfinite(v)

def _checar_horas(onde, i, valores):
    for nome, v in zip(CAMPOS_HORAS, valores):
        if not _hora_valida(v):
            raise ContratoError(f'{onde} id={i} campo={nome}: valor {v!r} ({type(v).__name__}) inválido; esperado int/float finito (sem bool/NaN/infinito).')
        if v < 0:
            raise ContratoError(f'{onde} id={i} campo={nome}: valor negativo {v!r} não permitido.')

def _horas_do_snapshot(snap):
    """id -> (est,rem,cons,cw) após validar estrutura e tipos; interrompe no primeiro erro, antes de qualquer soma."""
    by = {}
    for n, r in enumerate(snap['rows']):
        if not isinstance(r, (list, tuple)) or len(r) < 2: raise ContratoError(f'rows[{n}]: registro malformado: {r!r}')
        i = r[0]
        if not _int_estrito(i): raise ContratoError(f'ID não inteiro em rows: {i!r} ({type(i).__name__}); leitura interrompida.')
        if len(r) < ROWS_MIN_LEN:
            raise ContratoError(f'rows id={i}: registro com {len(r)} posições; esperado ao menos {ROWS_MIN_LEN} (campos de horas nas posições {ROWS_POS_HORAS}-{ROWS_MIN_LEN-1}).')
        _checar_horas('rows', i, r[ROWS_POS_HORAS:ROWS_MIN_LEN]); by[i] = tuple(r[ROWS_POS_HORAS:ROWS_MIN_LEN])
    for cat in ('inconc', 'orf'):
        for n, d in enumerate(snap.get(cat, [])):
            if not isinstance(d, dict) or 'id' not in d: raise ContratoError(f'{cat}[{n}]: registro malformado: {d!r}')
            i = d['id']
            if not _int_estrito(i): raise ContratoError(f'ID não inteiro em {cat}: {i!r} ({type(i).__name__}); leitura interrompida.')
            for nome in CAMPOS_HORAS:
                if nome not in d: raise ContratoError(f'{cat} id={i} campo={nome}: campo ausente.')
            _checar_horas(cat, i, [d[nome] for nome in CAMPOS_HORAS]); by[i] = tuple(d[nome] for nome in CAMPOS_HORAS)
    return by

def _universo_validado(universo_horas):
    for t, vals in universo_horas.items():
        if not _int_estrito(t): raise ContratoError(f'ID não inteiro no universo: {t!r} ({type(t).__name__})')
        if not isinstance(vals, (list, tuple)) or len(vals) != len(CAMPOS_HORAS):
            raise ContratoError(f'universo id={t}: esperado exatamente {len(CAMPOS_HORAS)} valores {CAMPOS_HORAS}, recebido {vals!r}.')
        _checar_horas('universo', t, vals)

def validar_horas(snap, universo_horas, tol=0.005):
    """universo_horas: {id:(est,rem,cons,cw)} capturado ANTES da classificação.
    Compara os 4 totais e cada Task. Prova PRESERVAÇÃO dos valores, não a correção independente da regra
    que zera rem/cons de Tasks concluídas (validar no PASSO 2). Interrompe com ContratoError se houver ID duplicado/não inteiro,
    registro malformado, campo de horas ausente ou não numérico finito (str, bool, None, NaN, ±inf) em qualquer categoria ou no universo."""
    if versao(snap) == 'legado': raise ContratoError('validar_horas exige contrato 1 (partição completa).')
    _forma(snap, 1)                        # chaves e tipos de lista (P1/P2/P5)
    by = _horas_do_snapshot(snap)          # estrutura e tipos ANTES de somas e comparações
    _universo_validado(universo_horas)
    cat_map(snap)                          # IDs duplicados interrompem
    faltando = sorted(set(universo_horas) - set(by)); extras = sorted(set(by) - set(universo_horas))
    nomes = CAMPOS_HORAS
    totais = {}
    for i, n in enumerate(nomes):
        cap = sum(x[i] for x in by.values()); ref = sum(x[i] for x in universo_horas.values())
        totais[n] = (round(cap, 2), round(ref, 2), abs(cap - ref) < tol)
    diverg = sorted(t for t in universo_horas if t in by and any(abs(by[t][i] - universo_horas[t][i]) >= tol for i in range(4)))
    ok = not faltando and not extras and not diverg and all(x[2] for x in totais.values())
    return {'ok': ok, 'faltando': faltando, 'extras': extras, 'totais': totais, 'tasks_divergentes': diverg}

def validar_snapshot(snap):
    """Conformidade integral de um snapshot de contrato 1 (ponto de entrada estrito para a rotina/painel).
    cat_map/comparar/validar_horas continuam tolerantes a dem/universo para operar em snapshots parciais.
    Exige: forma e tipos (cat_map), 'universo' == tamanho da partição, 'dem' presente, toda demanda de rows
    e toda candidata de inconc existente em dem. Não valida horas (ver validar_horas)."""
    m, v = cat_map(snap)
    if v == 'legado': raise ContratoError('validar_snapshot exige contrato 1.')
    if 'universo' not in snap: raise ContratoError("campo 'universo' obrigatório em contrato 1.")
    u = snap['universo']
    if not _int_estrito(u) or u != len(m):
        raise ContratoError(f"campo 'universo'={u!r} ({type(u).__name__}) difere do tamanho da partição ({len(m)}).")
    if 'dem' not in snap: raise ContratoError("campo 'dem' obrigatório em contrato 1.")
    if not isinstance(snap['dem'], list): raise ContratoError(f"'dem' deve ser lista, recebido {type(snap['dem']).__name__}.")
    dem_ids = set()
    for n, d in enumerate(snap['dem']):
        if not isinstance(d, dict) or not _int_estrito(d.get('id')): raise ContratoError(f'dem[{n}]: item malformado (esperado objeto com id inteiro): {d!r}')
        if d['id'] in dem_ids: raise ContratoError(f"dem: demanda {d['id']} duplicada.")
        dem_ids.add(d['id'])
    for r in snap['rows']:
        if r[1] not in dem_ids: raise ContratoError(f'rows id={r[0]} campo=demanda: demanda {r[1]} inexistente em dem.')
    for d in snap['inconc']:
        for c in d.get('cands', []):
            c = c['id'] if isinstance(c, dict) else c
            if c not in dem_ids: raise ContratoError(f"inconc id={d['id']} campo=cands: candidata {c} inexistente em dem.")
    return {'ok': True, 'universo': u, 'rows': len(snap['rows']), 'inconc': len(snap['inconc']), 'orf': len(snap['orf']), 'dem': len(dem_ids)}

# Limitações registradas
# L1. Uma Task que permanece em 'inconc' com candidatas diferentes NÃO gera evento de comparação.
# L2. validar_horas comprova preservação dos valores; a regra Done => rem=cons=0 deve ser validada separadamente (PASSO 2).
# L3. Interpretação adotada para dois snapshots legados: mesma metodologia ('legado-legado'); reassociação vale,
#     mas entrada/saída não são verificáveis porque Tasks sem associação não aparecem em rows.
