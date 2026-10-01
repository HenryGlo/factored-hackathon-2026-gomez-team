# Seguridad y protección de la API

Estado: **[Decisión]** implementado en la fase 2 del [prompt 05](prompts/05-produccion.md) ([backend/app/protection/](../backend/app/protection/)). Configuración en [backend/config/security.toml](../backend/config/security.toml), con override por entorno.

Con una URL pública y un LLM de pago detrás, el abuso es un riesgo de **costo** y de **seguridad**. Este documento separa lo que cubre la aplicación de lo que tiene que cubrir la plataforma de hosting o un CDN.

## Lo que cubre la aplicación

### Límites de peticiones (429 + `Retry-After`)

Ventana fija por regla y clave. La clave es la IP o la sesión; la sesión se identifica por el SHA-256 de la cookie, nunca por la cookie en claro. Al superar el límite: `429 rate_limited`, la cabecera `Retry-After` en segundos y `details: {rule, retry_after_seconds}`.

| Regla | Ruta | Clave | Por defecto | Variable |
|---|---|---|---|---|
| `ip_all` | todas las `/api/*` | IP | 120 / min | `RATE_IP_ALL` |
| `session_all` | todas las `/api/*` | sesión | 60 / min | `RATE_SESSION_ALL` |
| `login_ip` | `POST /api/auth/login` | IP | 10 / min | `RATE_LOGIN_IP` |
| `turns_session` | `POST /api/conversations/{id}/turns` | sesión | 20 / min | `RATE_TURNS_SESSION` |
| `turns_ip` | `POST /api/conversations/{id}/turns` | IP | 40 / min | `RATE_TURNS_IP` |
| `conversations_session` | `POST /api/conversations` | sesión | 10 / min | `RATE_CONVERSATIONS_SESSION` |

- `/api/health` y `/api/ready` no cuentan: los usa el balanceador. Las peticiones `OPTIONS` (preflight de CORS) tampoco.
- **Login:** el límite por IP se suma al bloqueo por fallos de autenticación que ya existía (5 fallos por usuario o 20 por IP en 15 minutos, [api-contract.md](api-contract.md#autenticación)).
- **IP real:** detrás de un proxy propio se usa `X-Forwarded-For` solo con `TRUST_PROXY=true`. Sin eso no se confía en la cabecera, porque el cliente podría falsificarla.
- **Almacenamiento:** en memoria, un contador por proceso.
  - **[Supuesto]** Despliegue de una sola instancia. Con varias instancias cada una cuenta lo suyo, así que el límite efectivo se multiplica por el número de instancias.
  - Para un límite compartido hace falta un almacén común, por ejemplo Redis. La interfaz `MemoryStore.hit` permite agregarlo sin tocar el middleware. Hoy no se usa Redis.
- **Apagado (solo para el harness):** `RATE_LIMITS_ENABLED=false`. El harness mide el comportamiento del sistema, no los límites; `eval/run.py` lo apaga por defecto.

### Presupuesto de LLM (costo)

| Tope | Por defecto | Variable |
|---|---|---|
| Llamadas por día (global, UTC) | 3.000 | `LLM_BUDGET_DAILY_CALLS` |
| Costo por día (global) | 5 USD | `LLM_BUDGET_DAILY_COST_USD` |
| Llamadas por sesión | 80 | `LLM_BUDGET_SESSION_CALLS` |
| Costo por sesión | 0,40 USD | `LLM_BUDGET_SESSION_COST_USD` |

- **De dónde sale la cuenta:** de `app.traces`, con los pasos `llm` de hoy y sin contar las plantillas del modo degradado. Así sobrevive a reinicios y vale con varias instancias.
- **Cuándo se revisa:** al empezar cada turno. Un turno puede pasarse por unas pocas llamadas, porque las del propio turno se guardan al final.
- **Si se supera, modo degradado:** el turno no llama al LLM. Usa las plantillas del cliente `fake` y la intención por palabras clave, y la conversación sigue funcionando.
- **Nunca falla en silencio:** queda un paso `presupuesto_llm` en la traza, con el motivo y los consumos, y un aviso `llm_budget_exceeded` en el log.
- **Con `LLM_PROVIDER=fake`** no se revisa, porque no hay costo.
- **Complemento recomendado:** un límite de gasto en la consola de Anthropic, que es la última barrera.

### Tope del mensaje

- **Límite:** 2.000 caracteres (`MAX_MESSAGE_CHARS`).
- **Si se supera:** `422 message_too_long`, con un mensaje amable ("Tu mensaje es muy largo… Resúmelo en menos de 2.000 caracteres") y `details: {max_chars, chars}` para que el frontend lo muestre en el idioma del cliente.
- **Tope duro:** el cuerpo de la petición rechaza más de 20.000 caracteres antes de procesarlo.

### Cabeceras de seguridad

En todas las respuestas, incluidos los `429`:

| Cabecera | Valor |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-Frame-Options` | `DENY` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Permissions-Policy` | sin cámara, micrófono, geolocalización ni pagos |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; …`. La API solo devuelve JSON. |
| `Cache-Control` (rutas `/api/*`) | `no-store`: las respuestas tienen datos del cliente. |
| `Strict-Transport-Security` | solo con `APP_ENV=production`: `max-age=31536000; includeSubDomains`. |

- **Documentación de la API:** en producción no hay `/docs`, `/redoc` ni `/openapi.json`. En desarrollo existen y no llevan la CSP de la API, porque cargan scripts de un CDN.
- **CSP del frontend:** la pone quien sirve los archivos estáticos (hosting o CDN). La sugerida está en [headers.py](../backend/app/protection/headers.py) (`FRONTEND_CSP`):

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';
connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```

### CORS

- **Cerrado por defecto:** sin `CORS_ALLOW_ORIGINS` no hay CORS. En desarrollo el frontend usa el proxy de Vite (mismo origen).
- **En producción:** `CORS_ALLOW_ORIGINS=https://<dominio-del-frontend>`, una lista separada por comas.
  - Con credenciales, porque la sesión va en una cookie.
  - Solo `GET` y `POST`.
  - Solo las cabeceras `Content-Type`, `X-CSRF-Token` e `Idempotency-Key`.
- **Si el frontend y la API comparten dominio**, por ejemplo con el frontend en `/` y la API en `/api`, no hace falta CORS.

### Lo que ya existía (prompt 03)

- **Autenticación:** contraseñas con argon2id, cookie de sesión httpOnly (`Secure` en producción), CSRF de doble envío y bloqueo por fallos de login ([api-contract.md](api-contract.md#autenticación)).
- **Identidad:** el `customer_id` sale siempre de la sesión. Los cuerpos rechazan campos desconocidos.
- **Base de datos:** el backend usa el rol `app_rw` y la consola `app_ro`; nunca el dueño de los esquemas ni el superusuario.
- **Confirmaciones:** tokens de confirmación de un solo uso (R4). El token no queda en las trazas.
- **Texto del LLM:** guarda R5 (ningún texto promete ni aprueba devoluciones), entrada minimizada (P-05) y texto del cliente delimitado como dato.

## Lo que debe cubrir la plataforma o un CDN

| Riesgo | Por qué no lo cubre la aplicación | Dónde se cubre |
|---|---|---|
| DDoS de red y de volumen (SYN flood, inundación HTTP masiva) | Cuando el tráfico llega a la aplicación, ya consumió red y CPU. | Protección DDoS del hosting o un CDN/WAF (Cloudflare, AWS Shield + WAF). |
| Límites distribuidos entre instancias | El contador es por proceso. | WAF con *rate-based rules*, o Redis compartido. |
| TLS y redirección HTTP → HTTPS | La aplicación solo envía HSTS. | Balanceador o plataforma (certificado gestionado). |
| CSP y cabeceras del frontend estático | La API no sirve el frontend. | Configuración de cabeceras del hosting estático o del CDN. |
| Bots y credential stuffing a escala | El límite por IP no frena botnets con muchas IPs. | WAF con detección de bots y CAPTCHA si hiciera falta. |
| Secretos (`ANTHROPIC_API_KEY`, `DATABASE_URL`, `DEMO_PASSWORD`) | No deben estar en el repositorio ni en la imagen. | Gestor de secretos de la plataforma. |
| Gasto total del LLM | El presupuesto de la aplicación es por instancia y por día. | Límite de gasto en la consola de Anthropic. |
| Copias de seguridad y acceso a la base | Fuera del alcance del proceso. | PostgreSQL gestionado (backups, red privada). |
