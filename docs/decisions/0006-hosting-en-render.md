# ADR-0006: Hosting de la demo en Render

Estado: Aceptada · Etiqueta: **[Decisión]** (2026-10-01, líder del equipo)

## Contexto

- **[Oficial]** La entrega pide una aplicación desplegada y accesible para los jueces.
- La demo dura unas dos semanas con uso bajo. Detrás hay un LLM de pago (`anthropic_api`), así que el despliegue tiene que
  mantener el rate limiting, el presupuesto de LLM y los secretos fuera del repo.
- El equipo tiene pocos días: el tiempo de puesta en marcha pesa tanto como el costo.
- AWS App Runner, la opción gestionada más simple de AWS, **no acepta clientes nuevos desde el 30 de abril de 2026**; AWS
  recomienda Amazon ECS Express Mode ([aviso de disponibilidad](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html),
  [ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)).

## Decisión

**Render**, con un Blueprint versionado ([render.yaml](../../render.yaml)): backend en Docker (Starter), PostgreSQL gestionado
(Basic-256mb) y frontend estático con rewrite de `/api` al backend. Detalle operativo en [deployment.md](../deployment.md).

- Costo: ≈ $13,30/mes (≈ $7 por las dos semanas de demo). Precios de [render.com/pricing](https://render.com/pricing)
  consultados el 2026-10-01: Starter $7/mes, Basic-256mb $6/mes, disco $0,30/GB, sitio estático $0, workspace Hobby $0.
- Puesta en marcha: una tarde (Blueprint + secretos + carga demo), sin redes ni IAM que diseñar.
- Cuenta necesaria: una cuenta de Render con tarjeta.

## Alternativas

| Alternativa | Por qué no (para la demo) |
|---|---|
| **AWS: ECS Express Mode + RDS en VPC privada + S3/CloudFront** (la de "banco real", abajo) | ≈ $75/mes y uno o dos días de trabajo (VPC, IAM, NAT, certificados). Es la arquitectura que se propondría a un banco; no se despliega |
| AWS App Runner + RDS | App Runner no acepta clientes nuevos desde el 30/04/2026 |
| Railway | Precio por uso (plan Hobby $5/mes con $5 de uso; ≈ $10 por GB de RAM y $20 por vCPU al mes, [railway.com/pricing](https://railway.com/pricing), 2026-10-01): costo parecido, pero sin Blueprint declarativo con despliegue condicionado a la CI ni rewrites de sitio estático como los de Render |
| Plan gratuito de Render | El web service se duerme tras 15 min sin tráfico (≈ 1 min para despertar) y la base gratuita vence a los 30 días ([docs](https://render.com/docs/free)) |

### La alternativa de "banco real": ECS Express Mode + RDS en VPC privada (estimación, sin desplegar)

Qué cambia frente a Render: la base y el backend quedan en subredes privadas, la salida a la API de Anthropic pasa por un NAT
con IP fija (lista de permitidos), los secretos están en Secrets Manager con rotación, los logs y métricas en CloudWatch, y el
acceso se gobierna con IAM. Es lo que pediría el área de seguridad de un banco.

Costo mensual estimado en us-east-1 (730 h; precios del AWS Price List del 2026-10-01 y de
[aws.amazon.com/vpc/pricing](https://aws.amazon.com/vpc/pricing/)):

| Recurso | Cálculo | USD/mes |
|---|---|---|
| Fargate (ECS Express), 0,25 vCPU + 0,5 GB, 1 tarea | 0,25 × $0,04048 × 730 + 0,5 × $0,004445 × 730 | 9,01 |
| Application Load Balancer (lo crea Express Mode) | $0,0225 × 730 + LCU mínimas ($0,008/LCU-h) | ≈ 17 |
| RDS PostgreSQL db.t4g.micro, Single-AZ, 20 GB gp3 | $0,016 × 730 + 20 × $0,115 | 13,98 |
| NAT Gateway (salida de la subred privada hacia Anthropic) | $0,045 × 730 + $0,045/GB | ≈ 33 |
| Secrets Manager (3 secretos) | 3 × $0,40 | 1,20 |
| S3 + CloudFront (frontend estático, tráfico de demo) | dentro de la capa gratuita de CloudFront | ≈ 1 |
| **Total** | | **≈ $75** |

- Para producción real se sumarían Multi-AZ en RDS (≈ el doble de la instancia), al menos 2 tareas, WAF y copias de seguridad
  con retención: no están en esta estimación.
- El código no cambia: la misma imagen ([backend.Dockerfile](../../infra/render/backend.Dockerfile)), las mismas variables de
  entorno y el mismo paso de migraciones. La protección DDoS de red la daría AWS Shield / CloudFront ([security.md](../security.md)).

## Consecuencias

- La demo queda en una sola instancia sin alta disponibilidad; el rate limiting y las fases del turno, en memoria del proceso
  (correcto con una instancia).
- El despliegue es reproducible desde el repo (Blueprint) y solo ocurre con la CI en verde.
- La carga de datos es manual y desde un equipo con el dataset, porque el dataset no puede estar en el repo ni en la imagen.
- Migrar a AWS es un cambio de infraestructura, no de aplicación.
