# Laboratorio público de regresiones de traducción japonés → español

Este repositorio está diseñado para **continuar pruebas técnicas sin gastar el presupuesto de cómputo de repositorios privados**. Solo contiene código de prueba independiente y ejemplos sintéticos. No es la distribución del traductor ni del juego.

## Qué verifica

- División de frases japonesas sin perder caracteres.
- Conservación exacta de códigos de control del RPG, marcadores y fechas.
- Protección de términos antes de enviar texto a un traductor.
- Restauración de los términos después de unir los fragmentos y sin etiquetas internas visibles.
- Rechazo de texto japonés sin traducir, respuestas vacías y marcadores corruptos.
- SQLite persistente: una frase aprobada se recupera después de reiniciar sin volver a traducir.

## Qué no afirma

**No ejecuta ni certifica los 21 artefactos del motor original.** No incluye modelos, archivos privados, ejecutables, credenciales, instaladores o datos de partidas. Los modelos originales se mantienen fuera del repositorio público. La fidelidad semántica neuronal real debe validarse por separado con una fuente y una licencia que permitan ejecutar legalmente los modelos elegidos.

Las pruebas usan traductores falsos y deterministas para verificar el *circuito* de texto, no para simular una traducción neuronal aprobada. Las frases del conjunto de prueba son sintéticas.

## Ejecución local

Requiere Python 3.11 o posterior, sin dependencias externas.

```bash
python tools/publication_guard.py
python -m compileall -q translation_lab tests tools
python -m unittest discover -s tests -v
```

## Cómo subirlo a un repositorio público

1. En la cuenta correcta de GitHub, crea un repositorio **nuevo y público** llamado, por ejemplo, `public-translation-regression-lab`.
2. Sube únicamente estos archivos, manteniendo la estructura `.github/workflows/public-tests.yml`.
3. GitHub Actions ejecutará las regresiones en `ubuntu-latest` y `windows-latest` con runners estándar.
4. Concede acceso del conector de GitHub al nuevo repositorio si quieres seguir editándolo desde el chat.

**No conviertas el repositorio privado existente a público ni copies los modelos o su archivo ZIP a este laboratorio.**

Las acciones de este laboratorio solo comprueban el código público. No publican paquetes, ejecutables ni versiones; no conectan servicios externos y no escriben dentro del juego.

## Publicación opcional con GitHub CLI

Si tienes `gh` autenticado en la cuenta correcta, desde la carpeta del laboratorio:

```bash
git init
git add .
git commit -m "test: public safe translation regressions"
gh repo create eduardolupaca01-lgtm/public-translation-regression-lab --public --source=. --remote=origin --push
```

El conector de esta conversación permite trabajar sobre repositorios ya existentes, pero **no dispone de una acción para crearlos**. Crear el repositorio público es un paso de GitHub que debe ejecutar la cuenta propietaria. Si el repositorio ya existe, no ejecutes `gh repo create` de nuevo: sube los archivos con `git push`.

## Diagnóstico corregido (regresiones adicionales)

El primer envío del repositorio contenía únicamente un ZIP; GitHub Actions no
puede descubrir un workflow dentro de un archivo comprimido. Por eso las pruebas
no se ejecutaban. El código de este repositorio debe estar **descomprimido en la
raíz** y el workflow en `.github/workflows/public-tests.yml`.

La ampliación de pruebas cubre fallos reproducibles que no detectaba la batería
inicial: IDs como `HP99` y `v2.3` alterados por espacios, fechas y horarios
cambiados por una traducción, omisiones de números repetidos, procesamiento de
monólogos japoneses sin dividir por oraciones y reutilización de entradas
incompletas de caché. El guardado exige validar previamente el resultado; tras
reiniciar un proceso distinto, la misma traducción aprobada debe recuperarse
sin invocar el traductor de nuevo.

**Alcance:** estas pruebas públicas validan el diseño del procesamiento de
texto y de la caché SQLite; no implican que un motor neuronal privado esté
corregido. La etapa de traducción neuronal real sigue pendiente y no debe
marcarse como aprobada únicamente por superar estas pruebas con dobles.
