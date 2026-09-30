# backend/policy/

## Propósito

Evaluar las reglas R1–R6 en código y devolver `permitir`, `informar`, `denegar` o `escalar` con la regla y la evidencia. ⚠️ Las reglas son **supuestos de práctica del equipo**: [docs/policies.md](../../docs/policies.md).

## Qué irá aquí

**[Propuesta]**

- Una función por regla, pura y testeable, que recibe hechos verificados (no texto del modelo).
- El evaluador que aplica el orden de reglas y devuelve el primer resultado distinto de `permitir`.
- Configuración de parámetros (60 días de R1, banda de riesgo de R6) leída de un solo lugar y registrada en la traza.

Ejemplo: cargo confirmado de hace 75 días → R1 → `escalar` con evidencia `{days_since: 75, limit: 60}`.

## Entradas y salidas

Entrada: transacción confirmada, reclamo existente, riesgo, fecha de referencia. Salida: decisión + reglas evaluadas.

## Dependencias

Ninguna de otras carpetas de código (recibe los datos ya resueltos por el controlador).

## Responsable sugerido

Software developer, con revisión del data analyst.
