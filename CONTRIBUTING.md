# Cómo contribuir

Guía interna del equipo. Todo lo que aquí aparece es **[Decisión]** o **[Propuesta]** del equipo; nada viene del reglamento oficial salvo lo marcado como **[Oficial]**.

**[Decisión]** Convenciones de GitHub desde el 2026-10-01. Factored evalúa también las prácticas de GitHub: ramas, PR pequeños y
frecuentes, commits claros y versiones con etiqueta.

## Flujo

1. **Un issue por trabajo real** (plantillas *Bug* y *Feature* en `.github/ISSUE_TEMPLATE/`).
2. **Una rama por cambio**, desde `main` actualizado:
   - `feat/…`: capacidad nueva;
   - `fix/…`: corrección;
   - `docs/…`: solo documentación;
   - `chore/…`, `ci/…`, `test/…`, `refactor/…`: mantenimiento, CI, pruebas, refactor;
   - `exp/…`: experimentos que quizá no se integren.
   Si el cambio toca contratos ([api-contract.md](docs/api-contract.md), [tools-contract.md](docs/tools-contract.md),
   [handoff-schema.md](docs/handoff-schema.md)), el PR actualiza el documento en el mismo cambio.
3. **PR pequeño a `main`** con la plantilla (`.github/pull_request_template.md`): qué cambia y por qué, cómo se probó,
   resultado del harness (pasan/total e inseguros por variante) y `Closes #N` del issue.
4. **Antes de fusionar:** CI en verde (`ci.yml`: secretos, backend + pipeline + harness, frontend) y la suite y el harness de
   dev con `baseline` y `sistema` (`LLM_PROVIDER=fake`) sobre una base de prueba separada (`*_test`), con **0 inseguros**.
5. **Fusión** con merge commit (`gh pr merge --merge`); la rama se puede borrar después. Nada de force push ni de reescribir
   el historial de `main`.

## Bases de datos: nunca probar sobre `bank`

**[Decisión]** 2026-10-01. Las pruebas de carga, el harness de evaluación, los tests y cualquier script que cree
conversaciones, reclamos o handoffs van **siempre** en una base separada (`*_test`: `bank_test`, `bank_eval_test`,
`bank_perf_test`…), nunca en `bank`, que es la base de la demo y de las pruebas manuales.

- El harness ya lo exige: solo corre contra bases cuyo nombre contiene `_test` (`EVAL_DATABASE_URL`).
- Un contenedor o servidor levantado para medir (memoria, latencia, carga) se conecta a una base `*_test`, no a la de `.env`.
- Motivo: el 2026-10-01 una prueba de carga del contenedor del backend usó `bank` y creó 8 conversaciones y 4 handoffs de
  usuarios demo. Se borraron por id, pero no debe repetirse.

## Commits: Conventional Commits, en inglés

```
<tipo>(<ámbito opcional>): <resumen en imperativo, ≤ 72 caracteres>

<cuerpo opcional: qué y por qué, no cómo>
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci` (y `data`, `exp`, `perf`, `build` si aplica). Ámbito =
carpeta o componente (`backend`, `controller`, `llm`, `ml`, `eval`, `etl`, `frontend`, `infra`, `docs`). Ejemplos:
`feat(controller): answer greetings without the LLM`, `fix(eval): strict status-label exception`.

- Títulos y descripciones de PR, también en inglés. Los textos que ve el cliente siguen en español y portugués, y la
  documentación existente en español.
- Cambia la propuesta inicial (commits en español): desde el 2026-10-01, commits y PR en inglés. Los 10 commits anteriores
  tienen títulos en español sin prefijo; no se reescriben (el historial de `main` no se toca).
- La revisión de otra persona es recomendable, pero no obligatoria: la puerta es la CI y el harness con 0 inseguros.

## Secretos y datos

- Nunca en el repositorio: `.env`, claves (`ANTHROPIC_API_KEY`), contraseñas reales, credenciales (el diccionario de
  datos trae las del bucket), datos del dataset ni artefactos
  grandes. Los secretos van en variables de entorno o en los secretos de GitHub (`eval-llm`).
- `gitleaks` revisa todo el historial en cada PR (job *Secretos* de la CI). Local: `gitleaks git . --redact`.
  Falsos positivos revisados: `.gitleaks.toml` (reglas) y `.gitleaksignore` (huellas), con su motivo.

## Versiones

- [SemVer](https://semver.org/lang/es/) con **tags anotados** sobre el merge commit de cada hito fusionado (`v0.x.y` mientras
  dure el desarrollo; **`v1.0.0` es la versión que se entrega**).
- Cada versión tiene su sección en [CHANGELOG.md](CHANGELOG.md) ([Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)).
  Lo que se fusiona sin versión va en `[Unreleased]`.
- Publicar: mover `[Unreleased]` a `[x.y.z] - AAAA-MM-DD` en el PR del hito y, tras fusionarlo,
  `git tag -a vX.Y.Z -m "…" <merge commit> && git push origin vX.Y.Z`. El workflow `release.yml` corre la CI sobre ese
  commit y crea el GitHub Release con las notas del CHANGELOG.

## Protección de `main`

Exigir PR, CI en verde y prohibir force push y borrado: [`scripts/protect_main.sh`](scripts/protect_main.sh). GitHub solo lo
permite en repositorios públicos o con GitHub Pro; hoy el repo es privado en el plan gratuito, así que se aplica al hacerlo
público.

## Cómo agregar un caso de evaluación

**[Propuesta]** Detalle de la taxonomía y de los splits en [docs/evaluation.md](docs/evaluation.md).

1. Decide la **categoría**: `normal`, `ambiguo`, `requiere_humano` o `adversario`, y el **idioma**: `es` o `pt`.
2. Decide el **split**:
   - `dev`: se puede mirar y usar para ajustar prompts y umbrales.
   - `test`: **congelado**. No se agregan ni editan casos después de la fecha de congelamiento (ver [docs/evaluation.md](docs/evaluation.md)). Si un caso de test está mal, se documenta como defecto y se crea una versión nueva del set; no se corrige en silencio.
3. Crea el caso en `eval/cases/<split>/` siguiendo el esquema descrito en [eval/cases/README.md](eval/cases/README.md): mensajes del cliente, cliente de prueba, transacción objetivo (si existe), resultado esperado (`reclamo_creado`, `aclaracion`, `abstencion`, `escalado`, `rechazo_seguro`), motivo de escalamiento esperado y reglas de política que aplican.
4. Si el caso es **escrito a mano**, marca `origen: manual` y tu rol como autor. Si es **generado**, marca `origen: generado` con la versión del generador.
5. La transacción objetivo debe ser una transacción **real** del dataset del cliente de prueba (ver [ADR-0003](docs/decisions/0003-reclamos-generados-sobre-transacciones-reales.md)).
6. Revisión cruzada: otra persona del equipo valida la etiqueta esperada antes de hacer merge.

## Cómo registrar un experimento

**[Propuesta]**

1. Crea una rama `exp/<tema>`.
2. Registra el experimento en `eval/results/` (ver [eval/results/README.md](eval/results/README.md)) con:
   - ID (`EXP-AAAAMMDD-<tema>`), autor, fecha y commit.
   - Hipótesis y qué variante se compara contra qué baseline.
   - Datos: versión del ETL, split usado y tamaño (n).
   - Versión de modelo, de prompt y de umbrales.
   - Semillas y número de repeticiones (para medir variabilidad entre corridas).
   - Métricas **siempre con numerador y denominador** (por ejemplo "41/50 = 0,82"), costo y latencia p50/p95.
   - Conclusión y limitaciones, incluidos los fallos.
3. Nunca usar el split `test` para elegir hiperparámetros, prompts ni umbrales.
4. Si el resultado cambia una decisión, abre o actualiza un ADR en [docs/decisions/](docs/decisions/README.md).

**[Oficial]** El reto pide reportar número y mezcla de casos, calidad de las etiquetas, versiones de modelo y prompt y variabilidad entre corridas cuando aplique.
