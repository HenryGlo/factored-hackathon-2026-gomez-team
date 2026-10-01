<!-- Título en Conventional Commits y en inglés: feat: …, fix: …, docs: …, test: …, refactor: …, chore: …, ci: … -->

Closes #<!-- número del issue -->

## What changes and why

## How it was tested
- [ ] `python -m pytest -q backend data_pipeline eval/tests`
- [ ] `ruff check backend eval scripts data_pipeline` y `mypy backend/app`
- [ ] Frontend (si aplica): `npm run lint && npm run typecheck && npm test && npm run build`

## Harness
<!-- Sobre una base de prueba separada (*_test). Pega los números del reporte. -->
| Variant | Passed / total | Unsafe |
|---|---|---|
| `baseline` |  |  |
| `sistema` (`LLM_PROVIDER=fake`) |  |  |

## Contract or docs changes
<!-- api-contract.md, conversation-flow.md, decisiones… o "none" -->
