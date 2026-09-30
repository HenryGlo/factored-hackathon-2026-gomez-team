# eval/cases/test/

**Vacío a propósito.** El set de test lo escribe el equipo a mano (30–50 reclamos por persona, es/pt) y no se usa para desarrollar ni ajustar nada ([docs/evaluation.md](../../../docs/evaluation.md)).

- Formato: el mismo de `dev/` ([schema.py](../schema.py)), con `split: test`.
- El runner se niega a correr `--split test` sin `--i-know-this-is-final` y registra cada ejecución en `eval/results/test_runs.log`.
