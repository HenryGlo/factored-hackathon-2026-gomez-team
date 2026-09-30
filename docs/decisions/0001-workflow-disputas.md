# ADR-0001: Workflow de disputas en vez de crédito

Estado: Aceptada · Etiqueta: **[Decisión]**

## Contexto

- **[Oficial]** El reto pide elegir **un** flujo coherente. Ejemplos: consultas de cuenta o pagos, soporte de tarjetas, **recepción de disputas de transacciones**, información y elegibilidad de productos de crédito. Implementar más flujos no da puntos extra.
- **[Oficial]** El problema debe estar respaldado por datos: motivos de contacto, demanda, calidad de datos y restricciones operativas.
- **[Oficial]** En crédito se exige separar conversación, riesgo predictivo y política de elegibilidad, usando reglas aprobadas o un servicio de política sintético etiquetado.
- Exploración del equipo ([quality-report.md](../data/quality-report.md)):
  - La mora es aleatoria: AUC 0,513 con `credit_score` solo; el mejor modelo exploratorio llega a 0,623 con leakage temporal. No hay señal para un riesgo de crédito creíble.
  - "Cargo no reconocido" aparece en 12.297 quejas (18,3 %), aunque todas las subcategorías tienen un peso similar.
  - `transactions` es la tabla más rica para el flujo y `fraud_score` es la única señal real (AUC 0,847).

## Decisión

Construir el flujo de **disputas de cargos no reconocidos**: identificar el movimiento, crear un reclamo (con confirmación) o escalar con un handoff estructurado. Nunca aprobar devoluciones.

## Alternativas

| Alternativa | Por qué no |
|---|---|
| Crédito (información y elegibilidad) | Sin señal en la mora; exige inventar un servicio de política de elegibilidad completo. |
| Soporte de tarjetas (solo) | Menos pasos de decisión y menos espacio para ML; se incorpora parcialmente con `lock_card`. |
| Consultas de cuenta o pagos | Más simple, pero con poco control de automatización para demostrar (confirmación, política, escalamiento). |

## Consecuencias

- Hay un problema de ML real y medible: identificar la transacción ([ADR-0002](0002-ranker-en-vez-de-llm.md)).
- No hay etiquetas de disputa en el dataset → hay que generarlas ([ADR-0003](0003-reclamos-generados-sobre-transacciones-reales.md)).
- La justificación por demanda es débil por la uniformidad de los datos; se debe declarar como limitación.
- Las reglas de disputa (R1–R6) son supuestos del equipo ([policies.md](../policies.md)).
