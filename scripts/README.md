# scripts/

## Propósito

Utilidades de desarrollo que no pertenecen a un componente.

## Qué irá aquí

**[Propuesta]**

- Descarga del dataset desde el bucket a `RAW_DATA_DIR`, leyendo credenciales del entorno.
- Preparación del entorno local: crear la base, correr el ETL con el subconjunto de demo, cargar artefactos de modelos.
- Selección de clientes de demo por escenario (normal, ambiguo, requiere humano).
- Verificación de enlaces relativos en la documentación.
- Chequeo previo a publicar: que no haya datos, `.env` ni credenciales en el árbol de git.

## Entradas y salidas

Variables de [.env.example](../.env.example). Salida según el script.

## Dependencias

[data_pipeline/](../data_pipeline/README.md), [backend/](../backend/README.md).

## Responsable sugerido

Software developer.
