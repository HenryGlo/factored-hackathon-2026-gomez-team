## Integración: harness con la API real (2026-10-01) — contaminado por el entrenamiento

**El número principal del experimento es el de la validación cruzada de arriba (183/187, 13,9 % al LLM).** Lo que sigue se midió sobre
mensajes que el modelo vio al entrenar: comprueba la integración, no el modelo.

Variante `sistema_cascade` frente a `sistema_api`, 1 repetición, mismo código, bases de prueba separadas con datos reales.
Reportes: [dev](../../eval/results/20261001-1601_comparacion_dev.md),
[dev_paraphrase](../../eval/results/20261001-1601_comparacion_dev_paraphrase.md).

| Split | Variante | Pasan todo | Inseguros | Intención que llega al LLM | Costo por caso | Latencia/turno p50 / p95 |
|---|---|---|---|---|---|---|
| dev (81) | `sistema_api` | 81/81 | 0/81 | 87/87 (100 %) | $0.0072 | 1,4 s / 4,4 s |
| dev (81) | `sistema_cascade` | 81/81 | 0/81 | 15/87 (17,2 %) | **$0.0044** (−39 %) | 1,3 s / 5,2 s |
| dev_paraphrase (96) | `sistema_api` | 96/96 | 0/96 | 100/100 (100 %) | $0.0073 | 1,4 s / 4,5 s |
| dev_paraphrase (96) | `sistema_cascade` | 96/96 | 0/96 | 8/100 (8,0 %) | **$0.0046** (−37 %) | 1,4 s / 4,8 s |

- **Costo:** baja ~38 % por caso, porque la llamada de intención era el 39 % del costo y la cascada evita la mayoría; además
  el turno no llama a `extract` cuando la intención resuelta en local no necesita datos del mensaje.
- **Latencia: no mejora.** La mediana es igual y el p95 no baja: en los turnos de disputa `extract` sigue yendo al LLM en
  paralelo, y el p95 lo dominan `explain` y `handoff_summary`. La cascada ahorra costo, no tiempo. **Trabajo futuro:** extracción
  con reglas o con un modelo pequeño cuando la intención se resuelve en local.
- **Calidad e inseguros:** iguales (todos los casos pasan, 0 inseguros en las dos variantes).
- **Advertencia: el harness mide sobre mensajes que el modelo vio al entrenar** (dev y dev_paraphrase). Estos números son
  optimistas para la cascada. La medida honesta es la validación cruzada de arriba (13,9 % de turnos al LLM con el mismo
  acierto que Haiku) y, sobre todo, el split test escrito a mano, que no se ha usado.

## Conclusión

La hipótesis se sostiene **en costo, no en latencia**: en validación cruzada la cascada iguala el acierto de Haiku
(183/187) enviando al LLM el 13,9 % de los turnos, y en el harness reduce el costo por caso ~38 % sin casos fallidos ni
inseguros. Límites: (1) 187 mensajes reales, muy desbalanceados, y varias intenciones solo tienen datos sintéticos, así que
para esas clases no hay validación real; (2) la calibración sigmoide no mejoró la confiabilidad; (3) falta la medida sobre
el split test. Por eso **`sistema_api` sigue siendo la configuración de producción** y `sistema_cascade` queda como
variante evaluada, lista para activarse con `INTENT_CLASSIFIER=cascade` si el test final confirma el resultado.
