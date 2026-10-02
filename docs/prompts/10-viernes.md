# Prompt 10 — Viernes 2 de octubre: producto completo y pulido en prodlike

Meta del día: al final del viernes, prodlike (scripts/prodlike_up.sh) muestra el
producto COMPLETO y presentable. Todas las pantallas existen y el flujo es sólido. El
sábado solo queda desplegar, correr la evaluación final y abrir el repo.

Reglas para las dos sesiones:
- Modo rápido: en local solo los tests de lo afectado + harness con LLM fake;
  "gh pr merge --auto --squash", nunca con la CI roja; PR pequeños; reportes de 3
  líneas.
- No despliegues, no recargues crédito, no hagas público el repo. Las pruebas van
  siempre en bases separadas, nunca en "bank". Usa claude -p con moderación.
- Cada dos o tres merges, actualiza prodlike con scripts/prodlike_up.sh y corre
  scripts/prodlike_smoke.sh. Si el humo falla, eso va primero.
- Henry revisa en prodlike y manda sus comentarios agrupados. Esos comentarios tienen
  prioridad sobre lo que estés haciendo.
- Al cerrar el día, docs/STATUS.md lleva al principio "Para Henry: viernes noche" con lo
  hecho, lo pendiente, los problemas conocidos y qué probar.

---

## SESIÓN BACKEND

1. Pendientes de anoche, si quedó alguno: "no reconozco ese cargo" en la confirmación
   del movimiento, DEMO_MODE con /api/demo/info, y el borrador #24 al día con main.
2. Arreglos de la revisión de Henry en prodlike (prioridad máxima cuando lleguen).
   Cada arreglo lleva su test y su caso en dev.
3. Voz (A3), solo si Henry carga ELEVENLABS_API_KEY en ~/.factored-prodlike/env:
   - prueba real de STT y TTS, latencia y costo por minuto;
   - activa VOICE_ENABLED en prodlike.
   Si no hay clave, no hagas nada de esto.
4. Preparación del sábado (sin desplegar):
   - scripts/predeploy_check.sh: verifica que el render.yaml está al día, que las
     variables requeridas aparecen documentadas, que la imagen Docker se construye,
     que el escaneo de secretos pasa y que no hay datos del dataset en el repo;
   - checklist en docs/deployment.md con el orden exacto del sábado: crédito → Blueprint
     → secretos → carga demo → humo público → corrida final con la API → repo público
     → protect_main.sh → tag v1.0.0-rc.
5. Evaluación final lista para correr con un solo comando:
   - scripts/final_eval.sh: test congelado con --i-know-this-is-final, sobre la URL o la
     base que se le indique, con anthropic_api y la tabla en formato para las
     diapositivas (n/N, inseguros, p50/p95, costo por caso);
   - pruébalo SOLO con LLM fake y en dev, NUNCA con el split test;
   - si el test escrito a mano del equipo llegó (issue #19), valida su formato con un
     dry-run que NO lo ejecute contra el sistema.
6. Documentación en inglés (los jueces la leen):
   - README: qué es, demo, arquitectura con diagrama, decisiones clave, resultados
     (con huecos para la tabla final), cómo correrlo y limitaciones;
   - docs/architecture.md y los ADR revisados;
   - un "Results at a glance" con los números ya medidos: baseline / todo LLM / sistema
     / API, cascada (validación cruzada), riesgo risk-v1, hallazgo de seguridad de
     tema. Cada número con su fuente.

## SESIÓN FRONTEND (worktree ../factored-ui)

1. Termina la Parte 2 de docs/prompts/09-noche-local.md: B0–B9, todas las pantallas
   funcionando contra el backend real.
2. Login con DEMO_MODE: aviso de "entorno de demostración con datos ficticios" y
   tarjetas de usuarios demo con su escenario (de /api/demo/info). La contraseña no
   aparece en el frontend: el aviso indica dónde está documentada para los jueces.
3. Pase de pulido profesional sobre TODO:
   - consistencia de espaciado, tipografía y colores;
   - estados vacíos, de carga y de error en cada pantalla;
   - microanimaciones sobrias;
   - Banky integrado en la landing y en el chat, con estados ligados a las fases
     reales;
   - textos es/pt revisados.
4. Calidad:
   - Lighthouse ≥ 90 en rendimiento y accesibilidad en la landing y el chat (pega los
     números en el PR);
   - teclado, foco visible, contraste AA y prefers-reduced-motion;
   - capturas en escritorio (1440 px) y celular (390 px) de cada pantalla en
     docs/screenshots/ (servirán para las diapositivas).
5. Recorrido del video: un modo o ruta que deje el sistema listo para grabar 3
   recorridos sin pasos manuales (cargo claro, ambiguo, riesgo alto → agente atiende
   el ticket → admin ve los SLO). Documenta el guion de clics en docs/demo-script.md.
6. Arreglos de la revisión de Henry (prioridad máxima cuando lleguen).

---

## TAREAS DE HENRY Y DEL EQUIPO (no son para los agentes)
- Henry: revisar prodlike en la mañana y a media tarde, con comentarios agrupados y
  capturas.
- Henry, opcional: clave de ElevenLabs en ~/.factored-prodlike/env si se quiere la voz.
- Data analyst: test escrito a mano listo el sábado al mediodía (issue #19), desde su
  cuenta y con su PR.
- Alguien del equipo: confirmar en el Slack de Factored la hora límite del lunes y si se
  permiten la API de Anthropic y ElevenLabs con datos sintéticos.
