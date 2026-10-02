# Entorno "prodlike": el sistema completo en local, casi igual a producción

Sirve para probar todo el sistema de punta a punta antes de desplegar, con una sola orden. No reemplaza al entorno de
desarrollo (`scripts/dev_up.sh`, tmux `factored-dev`, base `bank`): corre aparte y no lo toca.

```bash
scripts/prodlike_up.sh            # toma lo último de origin/main y lo levanta (o lo actualiza)
scripts/prodlike_smoke.sh         # prueba de humo por HTTP (cliente, agente, admin, límite 429)
scripts/prodlike_smoke.sh --image # además construye y prueba la imagen Docker de producción con LLM_PROVIDER=fake
scripts/prodlike_down.sh          # lo apaga; los datos quedan. Con --purge borra datos y secretos locales
```

Requisitos: Docker, tmux, Node y el entorno de Python del repo (`.venv`). Al terminar, `prodlike_up.sh` imprime las URL
(Mac e iPad), los usuarios demo con su escenario y dónde está la contraseña.

## Qué levanta

| Pieza | Prodlike | Igual que en producción |
|---|---|---|
| Código | `origin/main` en un worktree propio (`../factored-prodlike`); cada corrida toma lo último fusionado | Render despliega `main` cuando la CI pasa |
| Base de datos | PostgreSQL 17 en el contenedor `factored-prodlike-postgres-1`, base `bank_prodlike`, puerto 5544, dueño `bank_owner` | Misma versión; base gestionada con un usuario dueño |
| Roles y migraciones | `infra/render/predeploy.sh` (`roles.py` + Alembic + usuarios demo) | Es el mismo script: el `preDeployCommand` de Render |
| Datos | Subconjunto demo de 200 clientes (`data_pipeline.run full --customers-sample 200`) | La misma carga que `scripts/render_load_demo.sh` |
| Backend | `infra/render/start.sh`: uvicorn con `--proxy-headers`, un proceso, conectado con `bank_app` (grupo `app_rw`), sin la URL del dueño | Es el mismo script de arranque |
| Configuración | `infra/render/prod.env`: `APP_ENV=production` (cookies `Secure`), `TRUST_PROXY`, logs JSON, límites de peticiones, presupuesto de LLM, `VOICE_ENABLED=false`, `DEMO_MODE=true`, `RISK_MODEL` por defecto (calibrado) | Es la misma lista que `envVars` de `render.yaml` |
| Frontend | `npm run build` servido por Caddy en **un solo origen**, con `/api/*` hacia el backend y las cabeceras de seguridad del sitio estático | Mismo esquema que el sitio estático de Render con su rewrite |

El backend corre en una sesión de tmux llamada `factored-prodlike` (`tmux attach -t factored-prodlike` para verlo); su log
está en `~/.factored-prodlike/backend.log`. Los secretos locales (contraseñas de la base y `DEMO_PASSWORD`) están en
`~/.factored-prodlike/env`, fuera del repo y con permisos 600; se generan la primera vez y `DEMO_PASSWORD` se copia del
`.env` de desarrollo si existe, para que la contraseña de demo sea la misma.

## Diferencias exactas con producción

| Tema | Producción (Render) | Prodlike | Por qué |
|---|---|---|---|
| Proveedor del LLM | `anthropic_api` con IDs de modelo fijos | `claude_cli` (`claude -p`) en el host | Hoy no hay crédito de API. La latencia y el costo **no** representan producción (referencia: $0.0079 por caso y p50/p95 de 1,5–4,6 s por turno con la API). `PRODLIKE_LLM_PROVIDER=fake` lo corre sin LLM |
| Dónde corre el backend | Dentro de la imagen Docker | En el host, con el mismo `start.sh` | `claude -p` necesita la sesión de Claude Code del host. La imagen se valida aparte: `prodlike_smoke.sh --image` |
| TLS | Certificado público de Render | CA interna de Caddy (`tls internal`) | El navegador avisa una vez del certificado; hay que aceptarlo. Hace falta TLS porque en producción las cookies son `Secure` |
| Dominio | `*.onrender.com` | `https://localhost:8443` y `https://<IP local>:8443` | — |
| Proxy | Proxy de Render + rewrite del sitio estático | Caddy en Docker | Las cabeceras (`CSP`, `HSTS`, etc.) se copiaron de `render.yaml` |
| Base | Gestionada, sin acceso externo | Contenedor local en `127.0.0.1:5544` | — |
| Secretos | Panel de Render | `~/.factored-prodlike/env` | — |

## Abrirlo desde el iPad

1. El iPad y la Mac en la misma red wifi.
2. Abrir la URL de iPad que imprime `prodlike_up.sh` (`https://<IP local>:8443`).
3. Safari avisa que el certificado no es de confianza (es la CA local de Caddy): "Mostrar detalles" → "Visitar este sitio web".

Si la IP de la Mac cambia, volver a correr `scripts/prodlike_up.sh` (el certificado se emite para la IP del momento).

## Prueba de humo

`scripts/prodlike_smoke.sh` entra por el proxy, como un navegador, y comprueba: un solo origen con TLS y cabeceras; login de
cliente con cookie `Secure` y CSRF; cargo claro de punta a punta con su referencia RCL; caso ambiguo (pide elegir); riesgo
alto → ticket urgente sin reclamo automático; fuera de alcance; historial y feedback (una conversación ajena da 404); un
agente ve y toma el ticket (un cliente recibe 403); un admin ve los SLO (un agente recibe 403); y el límite de peticiones
responde 429 con `Retry-After`. Usa el LLM del backend (unos 12 turnos con `claude -p`) y escribe en la base prodlike.

Se puede repetir: en la segunda corrida el cargo claro ya tiene su reclamo y la prueba comprueba que no se duplica. Para
empezar de cero: `scripts/prodlike_down.sh --purge && scripts/prodlike_up.sh`.

El último paso agota a propósito el cupo por minuto de **una** sesión de prueba (`demo_revertido_2`); los límites por IP son
más altos, pero si justo después el navegador recibe un 429, espera un minuto.

## Apagarlo

```bash
scripts/prodlike_down.sh          # detiene backend y contenedores; los datos quedan en el volumen
scripts/prodlike_down.sh --purge  # además borra el volumen y ~/.factored-prodlike/env
```
