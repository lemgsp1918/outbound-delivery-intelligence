#!/usr/bin/env python3
"""Associação Task -> Demanda (contrato v1.5, lógica v3.1) do Outbound Delivery Intelligence.

Entrada (JSON): {"dem":{id:{fields}}, "feat":{id:{fields}}, "items":{id:{fields}},
                 "related":{demId:[ids]}, "manual":{demId:[ids]}, "forcar_inconc":{taskId:demId}}
 - dem: Demandas; feat: Features/PBIs/Epics (não Removed); items: Tasks (Task, Task Funcional, Bug API; não Removed).
 - fields = nomes de campo do ADO (System.Title, System.State, System.Parent, System.WorkItemType, ...).
Saída: partição exaustiva das Tasks em 'ok' (associada), 'inconc' (inconclusiva) e 'orf' (sem associação).
Regra: usa SOMENTE o nível de evidência mais forte (E1>E2>E3>E4s>E4w); 1 candidata = associada; >=2 = inconclusiva;
nenhuma = sem associação. Nunca escolhe a demanda pelo menor id. Sem similaridade difusa.
"""
import re, unicodedata, json, sys
from collections import Counter

STRIP_MIN = {'municipais', 'municípais'}
STRIP_EXT = STRIP_MIN | {'api', 'abap', 'api/abap', 'front', 'melhoria abap', 'arquitetura', 'outbound config', 'public'}
STOP = {'para', 'de', 'do', 'da', 'dos', 'das', 'a', 'o', 'as', 'os', 'e', 'em', 'no', 'na', 'com'}
PREFIX = {'adequacao', 'implementar', 'implementacao'}
MODEL = re.compile(r'\b(nf-?c-?e|nf-?s-?e|nf-?e|ct-?e-?os|ct-?e|mdf-?e|dc-?e|epec)\b', re.I)
CITYUF = re.compile(r'^[^/\[\]]+/\s*[A-Za-z]{2}$')
TIERS = ['E1', 'E2', 'E3', 'E4s', 'E4w']
DONE = {'Done', 'Concluído', 'Aprovado para Produção'}
MANUAL_PADRAO = {42: [19, 2678, 166, 2254], 133: [132, 352, 1792], 1170: [1082], 1479: [2373], 1483: [1272],
                 1486: [1760, 168], 1740: [1738], 2705: [2702], 2706: [2846], 2709: [2849, 3154], 2710: [3006]}
FORCAR_INCONC_PADRAO = {2423: 2641, 2424: 2641}


def deacc(t):
    t = unicodedata.normalize('NFD', t.lower())
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn')


def brackets(t):
    return [b.strip().lower() for b in re.findall(r'\[([^\]]*)\]', t)]


def tokens(t, strip):
    def rep(m):
        c = m.group(1).strip().lower()
        return ' ' if c in strip else ' ' + m.group(1) + ' '
    t = re.sub(r'\[([^\]]*)\]', rep, t)
    t = re.sub(r'[^\w\s]', ' ', deacc(t))
    tk = [w for w in t.split() if w not in STOP]
    while tk and tk[0] in PREFIX:
        tk = tk[1:]
    return tuple(tk)


def body(t):
    t = re.sub(r'\[[^\]]*\]', ' ', t)
    t = re.sub(r'[^\w\s]', ' ', deacc(t))
    tk = [w for w in t.split() if w not in STOP]
    while tk and tk[0] in PREFIX:
        tk = tk[1:]
    return tuple(tk)


def models(t):
    return {re.sub('-', '', m.lower()) for m in MODEL.findall(t)}


class Motor:
    def __init__(self, dados):
        self.dem = {int(k): v for k, v in dados['dem'].items()}
        self.feat = {int(k): v for k, v in dados['feat'].items()}
        self.items = {int(k): v for k, v in dados['items'].items()}
        self.related = {}
        for k, l in dados.get('related', {}).items():
            self.related.setdefault(int(k), set()).update(int(x) for x in l)
        self.manual = {int(k): [int(x) for x in v] for k, v in (dados.get('manual') or MANUAL_PADRAO).items()}
        self.forcar = {int(k): int(v) for k, v in (dados.get('forcar_inconc') or FORCAR_INCONC_PADRAO).items()}
        self.allf = {}
        for src in (self.dem, self.feat, self.items):
            for k, f in src.items():
                self.allf.setdefault(k, f)
        c = Counter()
        for src in (self.dem, self.feat, self.items):
            for f in src.values():
                for b in brackets(f['System.Title']):
                    c[b] += 1
        self.vocab = {b for b, n in c.items() if n >= 3 and not CITYUF.match(b)}

    def idents(self, t):
        return Counter(b for b in brackets(t) if b not in self.vocab and b not in STRIP_EXT)

    def blocked(self, td, tf):
        md, mf = models(td), models(tf)
        if md and mf and md != mf:
            return 'modelo'
        if self.idents(td) != self.idents(tf):
            return 'cidade/UF/identificador'
        return None

    def text_match(self, dt, ft, strip):
        a, b = tokens(dt, strip), tokens(ft, strip)
        if a and a == b:
            return 'forte'
        ba, bb = body(dt), body(ft)
        if ba and ba == bb and not self.blocked(dt, ft):
            return 'fraco'
        return None

    def raizes(self, strip=STRIP_MIN):
        R = {d: {'E2': set(), 'E3': set(), 'E4s': set(), 'E4w': set()} for d in self.dem}
        for d, l in self.manual.items():
            if d in R:
                R[d]['E2'].update(x for x in l if x != 19)
        for d, l in self.related.items():
            if d in R:
                R[d]['E3'].update(x for x in l if x in self.feat)
        for d, f in self.dem.items():
            for i, ff in self.feat.items():
                m = self.text_match(f['System.Title'], ff['System.Title'], strip)
                if m == 'forte':
                    R[d]['E4s'].add(i)
                elif m == 'fraco':
                    R[d]['E4w'].add(i)
        return R

    def cadeia(self, i):
        c = []
        seen = {i}
        while True:
            p = self.allf.get(i, {}).get('System.Parent')
            if not p or p in seen:
                break
            c.append(p)
            seen.add(p)
            i = p
        return c

    def classificar(self, carry=None):
        """Universo (opção B): Tasks com evidência (ok/inconc) + Tasks do snapshot anterior (carry) ainda não removidas.
        Sem evidência e fora do carry: ficam fora do universo."""
        carry = set(carry or ())
        R = self.raizes()
        universo = sorted(t for t, f in self.items.items() if f['System.State'] not in ('Removed', 'Removido'))
        out = {}
        for t in universo:
            anc = self.cadeia(t)
            aset = set(anc)
            ev = {k: set() for k in TIERS}
            for d in self.dem:
                if d in aset:
                    ev['E1'].add(d)
                for k in ('E2', 'E3', 'E4s', 'E4w'):
                    if R[d][k] & aset:
                        ev[k].add(d)
            best = next((k for k in TIERS if ev[k]), None)
            if best is None:
                cls, dm, cands = 'orf', None, []
            else:
                cands = sorted(ev[best])
                cls, dm = ('ok', cands[0]) if len(cands) == 1 else ('inconc', None)
            if cls == 'orf' and t not in carry:
                continue
            out[t] = {'cls': cls, 'd': dm, 'tier': best, 'cands': cands, 'anc': anc, 'sug': False}
        for t, d in self.forcar.items():
            if t in out and out[t]['cls'] == 'ok' and out[t]['d'] == d:
                out[t].update({'cls': 'inconc', 'd': None, 'cands': [d], 'tier': 'E4s', 'sug': True})
        return out


def horas(f):
    est = f.get('Microsoft.VSTS.Scheduling.OriginalEstimate') or 0
    cw = f.get('Microsoft.VSTS.Scheduling.CompletedWork') or 0
    rem0 = f.get('Microsoft.VSTS.Scheduling.RemainingWork') or 0
    if f['System.State'] in DONE:
        return est, 0, 0, cw
    return est, rem0, (est if est > 0 else rem0), cw


def nome(v):
    if not v:
        return ''
    return v.split('<')[0].strip() if isinstance(v, str) else (v.get('displayName') or '')


def montar(motor, out):
    """Devolve rows, meta, inconc, orf (contrato 1)."""
    it = motor.items
    def linha(t, d):
        f = it[t]
        e, r, c, w = horas(f)
        return [t, d, f['System.State'], nome(f.get('System.AssignedTo')), e, r, c, w, f.get('System.IterationPath', '')]
    rows = [linha(t, v['d']) for t, v in out.items() if v['cls'] == 'ok']
    meta = {str(t): {'t': it[t]['System.Title'], 'tp': it[t]['System.WorkItemType'], 'p': it[t].get('System.Parent'),
                     'it': it[t].get('System.IterationPath', '')} for t in out}
    def lado(t, v):
        r = linha(t, None)
        f = it[t]
        return {'id': t, 't': f['System.Title'], 'tp': f['System.WorkItemType'], 's': r[2], 'r': r[3] or None,
                'est': r[4], 'rem': r[5], 'cons': r[6], 'cw': r[7], 'it': r[8], 'pai': f.get('System.Parent'),
                'anc': [(a, motor.allf[a]['System.WorkItemType'], motor.allf[a]['System.Title']) for a in v['anc'] if a in motor.allf]}
    inconc, orf = [], []
    for t, v in out.items():
        if v['cls'] == 'inconc':
            d = lado(t, v)
            d.update({'cands': [{'id': c, 't': motor.dem[c]['System.Title']} for c in v['cands']], 'tier': v['tier'],
                      'motivo': ('Sugestão textual (E4s: título idêntico ao PBI pai); sem Parent/Related ADO que a confirme; não atribuída'
                                 if v['sug'] else 'Empate na evidência mais forte (%s) entre as demandas candidatas; sem evidência para desempatar' % v['tier'])})
            if v['sug']:
                d['sug'] = True
            inconc.append(d)
        elif v['cls'] == 'orf':
            d = lado(t, v)
            d['motivo'] = 'Nenhuma evidência (E1-E4) liga a Task a uma demanda'
            orf.append(d)
    return rows, meta, inconc, orf


if __name__ == '__main__':
    dados = json.load(open(sys.argv[1], encoding='utf-8'))
    m = Motor(dados)
    carry = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else []
    out = m.classificar(carry)
    rows, meta, inconc, orf = montar(m, out)
    json.dump({'rows': rows, 'meta': meta, 'inconc': inconc, 'orf': orf, 'universo_ids': sorted(out)}, open(sys.argv[2], 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print('associadas', len(rows), 'inconclusivas', len(inconc), 'sem associação', len(orf), 'universo', len(out))
