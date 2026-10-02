# Prompt 09 — Esta noche: sistema completo en local, lo más parecido a producción

Objetivo: cuando Henry vuelva, que pueda probar TODO el sistema en local, con una sola
orden y en una configuración casi igual a la de producción. Él no estará presente: no
te detengas salvo en lo marcado como DETENTE. Si algo es ambiguo, toma la opción más
segura, anótala en docs/STATUS.md y sigue.

Reglas: modo rápido (en local solo los tests de lo afectado + harness con LLM fake;
"gh pr merge --auto --squash", nunca con la CI roja; PR pequeños; reportes de 3 líneas).
No despliegues, no recargues crédito, no hagas público el repo. Las pruebas van siempre
en bases separadas, nunca en "bank". Usa claude -p con moderación.

Hay dos sesiones. Cada una ejecuta SOLO su parte.

---

## PARTE 1 — Sesión de backend (la actual)

1. Decisiones de Henry (confirmadas):
   - Recorte del harness real: dejar terminar sistema y sistema_cascade en dev, cancelar
     dev_paraphrase y todo_llm con LLM real, y correr baseline.
   - Bloque 5 de 07: PR + tag v0.11.0, con la nota de que la tabla completa se corre el
     sábado con la API en la versión desplegada.
   - Riesgo: calibrated risk-v1 POR DEFECTO, sin tabla ampliada. La ficha
     docs/ml/fraud-risk.md, policies.md y STATUS deben decir lo mismo.
   - #48: una pasada con claude -p (Opus) sobre los feedbacks sembrados para regenerar
     el reporte de ese PR. Sigue sin fusionarse.

2. Entorno "prodlike" en local: scripts/prodlike_up.sh (y prodlike_down.sh)
   - Postgres en su propio contenedor y base (bank_prodlike, otro puerto), cargado con
     el MISMO subconjunto demo y los MISMOS scripts de roles y migraciones que usará
     Render (infra/render/). La app se conecta con el rol de la app, no como
     superusuario.
   - Backend con el mismo comando de arranque que en producción (workers, proxy
     headers) y la configuración de producción: DEMO_MODE=true, rate limiting,
     presupuestos, cabeceras de seguridad, logs JSON, RISK_MODEL por defecto y
     VOICE_ENABLED=false.
   - LLM: en producción será anthropic_api, pero hoy no hay crédito. Usa claude_cli
     corriendo el backend en el host. Además, haz una prueba de humo de la IMAGEN
     Docker de producción con LLM_PROVIDER=fake, para validar el Dockerfile (con
     models/ incluido).
   - Frontend: build de producción (no el servidor de desarrollo) servido detrás de un
     proxy local (Caddy o similar) en UN solo origen, con /api hacia el backend, igual
     que el rewrite de Render. Que también se pueda abrir desde el iPad en la red local.
   - El script imprime al final:
     - las URL (Mac e iPad);
     - los usuarios demo con su escenario: cliente con cargo claro, con cargos
       parecidos, de riesgo alto, agente de soporte y admin;
     - dónde está la contraseña de demo (sin imprimirla).
   - Debe funcionar con el código de main de ese momento: cada vez que Henry lo corre,
     toma lo último que se fusionó.
   - docs/prodlike.md: diferencias exactas con producción (proveedor del LLM, TLS,
     dominio) y cómo apagarlo.

3. Prueba de humo automatizada: scripts/prodlike_smoke.sh con Playwright o HTTP
   - login de cliente;
   - cargo claro de punta a punta (con la referencia RCL);
   - caso ambiguo;
   - riesgo alto → ticket urgente;
   - fuera de alcance;
   - historial de conversaciones y feedback;
   - un agente ve y toma el ticket;
   - un admin ve los SLO;
   - el rate limiting responde 429.
   El resultado va a docs/STATUS.md.

4. Al final, deja prodlike LEVANTADO con el último main, y factored-dev intacto
   (no lo reinicies). En docs/STATUS.md, al principio, la sección "Para Henry al
   volver": URL, usuarios, qué probar (docs/manual-test-script.md) y problemas
   conocidos.

---

## PARTE 2 — Sesión de frontend (nueva, en el worktree ../factored-ui)

Lee docs/STATUS.md, docs/api-contract.md y docs/prompts/08-frontend-landing.md
(Parte B). Esta noche la prioridad es que TODAS las pantallas existan y funcionen
contra el backend real. El pulido viene después. Orden:

1. B0 rápido: tokens de diseño y componentes base (botones, tarjetas, chips,
   formularios, layout).
2. B1 + B3: landing de BankyFicticious con "Tengo un reclamo" y "Inicio de sesión de
   agentes de soporte", y el chat que se abre con la presentación de Banky y la
   elección texto/voz. Con VOICE_ENABLED=false, la opción de voz explica que no está
   disponible.
3. B5: el chat profesional, con el feedback al cerrar.
4. B6: "Mis conversaciones", "Mis movimientos" y "Mis reclamos".
5. B7: portal de agentes (login, bandeja de tickets y detalle con el handoff).
6. B8: panel admin (SLO, latencia, resolución, costo, logs y mejora continua).
7. B2: Banky animado con estados ligados a las fases reales del turno (diseño ORIGINAL,
   sin parecido a personajes existentes).
8. B4: la interfaz de voz detrás del flag.
9. B9: e2e con Playwright de los 3 recorridos y capturas en escritorio y celular en cada
   PR.

Prueba contra tu propio backend (LLM_PROVIDER=fake, otro puerto y otra base). Fusiona
cada pantalla a main en cuanto pase la CI, para que el prodlike de la Parte 1 la tome.
Si el contrato no alcanza, abre un issue y usa un mock mientras tanto; no modifiques
backend/.

DETENTE solo si un cambio de contrato bloquea varias pantallas: anótalo en STATUS y
sigue con las que no dependen de él.
