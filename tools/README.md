# tools/ — contrato de dados v1.5 (Outbound Delivery Intelligence)

- `odi_assoc.py` — associação Task→Demanda (lógica v3.1: E1 hierarquia, E2 raiz manual, E3 Related, E4s texto forte, E4w texto fraco; empate = inconclusiva; nunca o menor id).
- `contrato_check.py` — regras do contrato 1 (partição rows/inconc/orf, comparação por ID, validação de horas). Revisão rev4, 29 testes.
- `validar_5v.py` — PASSO 5V da rotina: valida o documento antes de gravar (exit code ≠ 0 = não gravar).
