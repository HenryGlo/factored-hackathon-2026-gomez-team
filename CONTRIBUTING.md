# Cómo contribuir

Guía interna del equipo. Todo lo que aquí aparece es **[Decisión]** o **[Propuesta]** del equipo; nada viene del reglamento oficial salvo lo marcado como **[Oficial]**.

## Ramas

**[Propuesta]**

- `main`: siempre desplegable. Solo entra por Pull Request con al menos una revisión.
- Ramas de trabajo con prefijo por tipo y carpeta:
  - `feat/backend-controlador`, `feat/ml-ranker`, `feat/eval-generador`
  - `fix/api-idempotencia`
  - `docs/adr-0006`
  - `exp/ranker-lambdarank` (experimentos que quizá no se integren)
- Una rama por tema. Si toca contratos ([api-contract.md](docs/api-contract.md), [tools-contract.md](docs/tools-contract.md), [handoff-schema.md](docs/handoff-schema.md)), el PR actualiza el documento en el mismo cambio.

## Commits

**[Propuesta]** Formato Conventional Commits, en español:

```
<tipo>(<alcance>): <resumen en imperativo>

<por qué, si no es obvio>
```

- Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `data`, `exp`, `chore`.
- Alcance = carpeta o componente: `backend`, `ml`, `eval`, `etl`, `frontend`, `infra`, `docs`.
- Ejemplo: `feat(ml): agrega baseline de ranking por monto y recencia`.
- Nunca commitear: datos del dataset, `.env`, credenciales (el diccionario de datos trae credenciales del bucket), artefactos de modelos. Ver [.gitignore](.gitignore).

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
