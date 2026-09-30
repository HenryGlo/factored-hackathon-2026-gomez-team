# data/

## Propósito

**[Decisión]** Esta carpeta es **solo documentación**. El repo es público y no sabemos si el dataset o sus derivados se pueden publicar (P-04 en [docs/open-questions.md](../docs/open-questions.md)). [.gitignore](../.gitignore) excluye todo lo que hay aquí salvo los `.md`.

⚠️ Localmente, esta carpeta contiene los PDFs del reto. El diccionario de datos incluye **credenciales de acceso al bucket**: no copiarlas a ningún archivo versionado ni a issues, PRs o slides. Usar variables de entorno ([.env.example](../.env.example)).

## Qué irá aquí

- Este README.
- Documentación del dataset: [docs/data/](../docs/data/README.md) (inventario, calidad, uso).

## Cómo obtener los datos

**[Oficial]** El dataset está en un bucket S3 de solo lectura para participantes; las instrucciones y credenciales están en el diccionario de datos.

**[Propuesta]** Descargar a un directorio fuera del repo (o a `dataset/`, ignorado) y apuntar `RAW_DATA_DIR` ahí. Un script de descarga irá en [scripts/](../scripts/README.md).

## Entradas y salidas

No aplica.

## Dependencias

Ninguna.

## Responsable sugerido

Data analyst.
