#!/usr/bin/env python3
"""PASSO 5V — validação do contrato 1 antes de gravar.
Uso: python validar_5v.py doc.json ado_tasks.json [anterior.json]
 doc.json        documento do snapshot (rows/inconc/orf/oth/dem/universo/contrato ...)
 ado_tasks.json  {"<id>": {campos brutos do ADO das Tasks lidas (não Removed)}}  (System.State, ...Scheduling.*)
 anterior.json   snapshot anterior (opcional) para o item 7
Saída: uma linha OK/FALHA por item (1..7); exit code 0 só se os itens 1..6 passarem (item 7 é informativo)."""
import sys, json, math
sys.path.insert(0, __file__.rsplit('/', 1)[0] if '/' in __file__ else '.')
import contrato_check as C

DONE = {'Done', 'Concluído', 'Aprovado para Produção'}
OE, CW, RW = ('Microsoft.VSTS.Scheduling.OriginalEstimate', 'Microsoft.VSTS.Scheduling.CompletedWork', 'Microsoft.VSTS.Scheduling.RemainingWork')


def bruto(f):
    est = f.get(OE) or 0; cw = f.get(CW) or 0; rw = f.get(RW) or 0
    if f['System.State'] in DONE:
        return (est, 0, 0, cw)
    return (est, rw, est if est > 0 else rw, cw)


def main(a):
    doc = json.load(open(a[1], encoding='utf-8'))
    ado = {int(k): v for k, v in json.load(open(a[2], encoding='utf-8')).items()}
    res = []
    def run(n, nome, fn):
        try:
            det = fn()
            res.append((n, True, nome, det))
        except Exception as e:  # noqa
            res.append((n, False, nome, f'{type(e).__name__}: {e}'))
    # 1-2-4 (e 3 parcial): estrutura, tipos, IDs únicos, listas, dem, cands
    def i1():
        if not (type(doc.get('contrato')) is int and doc['contrato'] == 1):
            raise C.ContratoError(f"'contrato' deve ser o inteiro 1: {doc.get('contrato')!r}")
        return C.validar_snapshot(doc)
    run('1', 'contrato=1 inteiro; IDs inteiros e únicos; demandas inteiras; partição/dem/cands (itens 1,2,4)', i1)
    def i3():
        n = len(doc['rows']) + len(doc['inconc']) + len(doc['orf'])
        if doc.get('universo') != n or type(doc.get('universo')) is not int: raise C.ContratoError(f"universo={doc.get('universo')!r} != {n}")
        if n != len(ado): raise C.ContratoError(f'universo {n} != Tasks lidas do ADO {len(ado)}')
        return f'universo={n} == Tasks do ADO'
    run('3', 'universo = soma das três listas = Tasks lidas do ADO', i3)
    def i5():
        r = C.validar_horas(doc, {i: bruto(f) for i, f in ado.items()})
        if not r['ok']: raise C.ContratoError(json.dumps(r, ensure_ascii=False)[:600])
        return json.dumps(r['totais'], ensure_ascii=False)
    run('5', 'horas: est/rem/cons/cw finitas, não negativas; totais e Task a Task = universo do ADO', i5)
    def i6():
        viol = []
        reg = {r[0]: (r[2], r[4], r[5], r[6], r[7]) for r in doc['rows']}
        for d in doc['inconc'] + doc['orf']: reg[d['id']] = (d['s'], d['est'], d['rem'], d['cons'], d['cw'])
        for i, f in ado.items():
            if i not in reg: viol.append((i, 'ausente')); continue
            s, est, rem, cons, cw = reg[i]
            if f['System.State'] in DONE: ok = rem == 0 and cons == 0
            else:
                rw = f.get(RW) or 0; oe = f.get(OE) or 0
                ok = abs(cons - (oe if oe > 0 else rw)) < 0.005 and abs(rem - rw) < 0.005
            if not ok or s != f['System.State']: viol.append((i, 'regra'))
        if viol: raise C.ContratoError(f'{len(viol)} violações: {viol[:10]}')
        return '0 violações (recalculado dos campos brutos do ADO)'
    run('6', 'regra Done/não-Done recalculada de forma independente', i6)
    if len(a) > 3:
        def i7():
            ant = json.load(open(a[3], encoding='utf-8'))
            r = C.comparar(ant, doc)
            cont = {}
            for e in r['eventos']: cont[e['tipo'] if isinstance(e, dict) and 'tipo' in e else str(e)[:40]] = cont.get(e['tipo'] if isinstance(e, dict) and 'tipo' in e else str(e)[:40], 0) + 1
            return f"modo={r['modo']}; eventos={json.dumps(cont, ensure_ascii=False)}"
        run('7', 'comparação com o snapshot anterior (informativo)', i7)
    falhou = False
    for n, ok, nome, det in sorted(res):
        print(f"{'OK   ' if ok else 'FALHA'} item {n}: {nome} — {det}")
        if not ok and n != '7': falhou = True
    return 1 if falhou else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
