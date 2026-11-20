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

Las acciones solo comprueban el código público. No publican paquetes, ejecutables ni versiones y no escriben en instalaciones. Los workflows neuronales independientes descargan modelos públicos temporalmente para pruebas, sin incorporarlos al repositorio.

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
corregido. Las pruebas simuladas no certifican traducciones reales. La evaluación neuronal
pública se realiza en workflows separados y conserva sus propios registros.


## Etapa neuronal pública (separada de las regresiones simuladas)

El workflow **.github/workflows/real-neural-acceptance.yml** instala
**Argos Translate 1.11.0** y descarga en un directorio temporal únicamente
los modelos públicos **ja → en** y **en → es** desde su catálogo oficial.
Los modelos no se guardan en Git, y no se publica ningún ejecutable.

La prueba emplea **12 frases originales y sintéticas**, con casos de saludos,
clubes escolares, referencias de mañana/tarde, monólogos, nombres,
códigos de control RPG, números y saltos de línea. La aceptación requiere
que se conserve la estructura y que aparezcan los conceptos semánticos
exigidos; no basta con recibir algún texto en español.

El proceso de prueba realiza dos fases:

1. Inferencia real mediante las dos etapas neuronales; guarda en SQLite
   solamente las traducciones que superen todas las validaciones.
2. Abre la base de datos en **otro proceso, sin cargar los modelos**.
   Debe recuperar exactamente las traducciones aprobadas, sin recalcularlas,
   y comprobar que ninguna traducción rechazada haya sido almacenada.

La ejecución solo puede terminar aprobada si **todos** los casos superan
ambas fases. Los errores se registran con su motivo; no se sustituyen
resultados por traducciones preparadas manualmente.

Fuentes de modelos y licencias:
- https://github.com/argosopentech/argospm-index
- https://github.com/argosopentech/argos-translate
- https://github.com/argosopentech/argos-translate/issues/533

**Límite de la prueba:** valida la ruta neuronal pública y el diseño de
la caché. No ejecuta ni certifica los modelos originales de la etapa
privada; una aprobación aquí no demuestra que aquel motor esté reparado.

La prueba se puede abrir en la pestaña Actions, bajo
**Public real-neural Japanese-to-Spanish acceptance**. No modifica
instalaciones ni crea entregables de software.


## Etapa aprobada: caché durable ante concurrencia y reinicios

La ejecución pública [44735970014](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44735970014)
aprobó en **Windows y Linux**. El workflow
[public-cache-stress.yml](.github/workflows/public-cache-stress.yml) comprueba
el mismo directorio SQLite desde **8 procesos independientes** para
**36 frases sintéticas distintas**: 288 solicitudes por plataforma,
36 llamadas al productor simulado, **0 inferencias duplicadas**.

También verifica de manera independiente que:

- Un proceso nuevo recupera las traducciones sin llamar al productor.
- Una traducción obsoleta se rechaza mediante un validador de calidad
  actualizado y se reemplaza una sola vez.
- Un proceso terminado abruptamente mientras ejecutaba una traducción
  libera su bloqueo; otra ejecución recupera la operación y guarda el
  resultado completo.
- Se conservan los códigos de control, números y saltos CRLF.
- La validación principal y los 93 casos unitarios se ejecutan tanto en
  Linux como en Windows.

Los informes JSON de cada sistema están adjuntos como *artifacts* a esa
ejecución. El productor es **simulado**, deliberadamente: esta prueba
mide repetición, atomicidad operativa y recuperación, no calidad lingüística.

El cambio principal está en `translation_lab/cache.py`, con bloqueos
advisory por clave distribuidos en un máximo de 256 archivos de bloqueo,
para coordinar procesos **en un mismo sistema de archivos**. No demuestra
coordinación entre máquinas independientes.

Como comprobación complementaria, la ejecución neuronal pública
[NLLB 44735121295](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44735121295)
aprobó **12/12 traducciones sintéticas** y **12/12 recuperaciones SQLite**
usando esta implementación de caché. NLLB conserva sus condiciones de
**investigación y uso no comercial**. Ninguna de estas aprobaciones
certifica motores privados o calidad universal del japonés → español.

### Repetir la prueba de concurrencia

Con Python 3.11 y desde la raíz del repositorio:

    python -m unittest discover -s tests -v
    python -m tools.cache_stress stress --workspace /tmp/cache-stress-new --cases 36 --workers 8

La carpeta `--workspace` debe ser nueva. El informe se escribe en
`cache-stress-report.json` dentro de esa carpeta, y el comando devuelve
un código distinto de cero ante un fallo.


## Etapa de generalización: conjunto ciego de diez diálogos nuevos

El workflow Public NLLB unseen Japanese dialogue holdout evalúa diez frases y
diálogos sintéticos que no pertenecen a los doce casos de desarrollo del
runner neural_acceptance. Incluyen negación, condiciones, causalidad, roles de
hablantes, cantidades, direcciones, horarios, códigos de control y saltos CRLF.

**La puerta es 10/10:** un solo error semántico o estructural impide aprobar
la etapa. El runner usa el modelo público NLLB directamente con la protección
estructural de translate_checked; no aplica paráfrasis de origen, correcciones
léxicas, respuestas preparadas ni reintentos específicos por caso. Las
comprobaciones semánticas se ejecutan antes de guardar y al recuperar SQLite.

La segunda fase abre la caché desde un proceso nuevo, sin cargar pesos, y
comprueba que se recuperen exactamente las traducciones aceptadas y que no se
haya guardado ninguna rechazada. Los informes JSON y la prueba de reinicio
quedan como artifacts de la ejecución, incluso si el holdout falla.

**Licencia y alcance:** facebook/nllb-200-distilled-600M declara
CC-BY-NC-4.0. Esta prueba es exclusivamente de investigación/no comercial;
no autoriza su uso en producción comercial ni certifica el motor original.
Un resultado 10/10 demuestra únicamente que este modelo público pasó este
pequeño conjunto sintético y sus validaciones, no calidad universal.


## Resultado del primer holdout y comparación de modelos con licencias permisivas

La primera ejecución real de NLLB sobre los diez diálogos nuevos terminó en
**4/10 (FAIL)**: seis traducciones fueron rechazadas por pérdida de
relaciones, instrucciones, tiempos o contexto. El registro original se
conserva en la ejecución
[44738336632](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44738336632).
No se modifica ese resultado ni se baja el umbral de aprobación.

Tras revisar el informe se corrigieron dos aspectos del validador: se acepta
el plural implícito de “iremos” como acción conjunta y se rechaza una cita que
afirma que los niños están callados cuando el original les pide guardar
silencio. También se reforzó la comprobación de que la hora y la llegada
pertenezcan a la misma frase. La primera ejecución NLLB sigue siendo el
registro histórico de la versión inicial; no se presenta como un resultado
recalculado.

La siguiente comparación ejecuta, sobre los mismos diez casos fijos, dos
modelos públicos con licencias declaradas más permisivas: Helsinki-NLP
opus-mt-ja-es (Apache-2.0) y facebook/m2m100_418M (MIT). Ambos se prueban
directamente, sin paráfrasis de origen, correcciones de destino, traducciones
preparadas ni reintentos específicos. La puerta sigue siendo 10/10 y cada
resultado tiene su propia prueba de reinicio SQLite.

Después de la primera ejecución, este conjunto ya no es ciego para el equipo:
se mantiene fijo como conjunto comparativo, sin usarlo para entrenar modelos.
Las licencias declaradas son una condición inicial de selección, no una
certificación legal de todos los usos o dependencias. Ningún resultado
autoriza el uso del motor original ni certifica calidad universal.


## Siguiente ruta evaluada: pivote japonés → inglés → español

Como los tres modelos directos no alcanzaron 10/10, se añadió una prueba
independiente de traducción en dos etapas con los modelos públicos
Helsinki-NLP opus-mt-ja-en y opus-mt-en-es, ambos con licencia declarada
Apache-2.0. Se reutilizan los mismos diez casos y los mismos controles
semánticos, estructurales y de persistencia.

La salida intermedia en inglés queda registrada para inspección. No se
permiten paráfrasis, correcciones manuales, glosarios ni reintentos por caso.
La puerta sigue siendo 10/10; cualquier caso rechazado queda fuera de la
caché aceptada. La recuperación SQLite se verifica en un proceso nuevo sin
cargar los modelos.

Esta ruta es una evaluación experimental: traducir por pivote puede introducir
errores adicionales. No se considera apta para producción hasta que pase el
conjunto completo y una revisión humana independiente.


## Etapa de recuperación: cola persistente de revisión humana

Los runners del conjunto NLLB, la comparación Marian/M2M100 y la ruta por
pivote ahora envían cada caso rechazado a una cola SQLite persistente. Se
conservan el texto de origen, la propuesta del modelo (si llegó a producirse),
el motivo del rechazo, el modelo utilizado y los fragmentos de salida cruda.
Una propuesta rechazada nunca se guarda como traducción aprobada.

La cola comparte el archivo translation-cache.sqlite3, pero usa tablas
separadas de las traducciones aceptadas. La aprobación humana y la promoción
de la corrección a la caché se realizan en una sola transacción SQLite. Se
requieren revisor, revisión vigente, confirmación humana explícita y notas.
La validación estructural se vuelve a ejecutar; la API también permite añadir
un validador semántico específico. Si ya existe otra traducción aprobada, el
reemplazo exige una opción explícita. Las propuestas competidoras quedan
marcadas como sustituidas.

Cada transición se registra en review_queue_events. Los comandos reject y
revise conservan el historial y permiten volver a poner una propuesta
rechazada en revisión sin borrar la decisión anterior. Las revisiones obsoletas
no pueden aprobarse. Los workflows adjuntan review-queue.json y la base
SQLite como artifacts para que la cola pueda recuperarse después del runner.

### Operar la cola

El argumento --workspace debe apuntar a la carpeta que contiene
translation-cache.sqlite3 (por ejemplo, la carpeta cache extraída del
artifact del workflow):

    python -m translation_lab.review_queue list --workspace ./cache
    python -m translation_lab.review_queue show --workspace ./cache --id ITEM_ID

Para aprobar una corrección después de comprobar manualmente el significado,
los hablantes, las negaciones, las cantidades y el contexto:

    python -m translation_lab.review_queue approve --workspace ./cache --id ITEM_ID --expected-revision 1 --reviewer "Nombre del revisor" --correction "Traducción corregida" --human-verified --notes "Verifiqué significado, sujetos, negación y contexto."

Para rechazar o volver a presentar una propuesta:

    python -m translation_lab.review_queue reject --workspace ./cache --id ITEM_ID --expected-revision 1 --reviewer "Nombre del revisor" --reason "La relación entre los hablantes no es correcta."
    python -m translation_lab.review_queue revise --workspace ./cache --id ITEM_ID --expected-revision 2 --reviewer "Nombre del revisor" --proposed "Nueva propuesta" --reason "Se corrigió la relación entre los hablantes."

La herramienta no aprueba traducciones automáticamente ni convierte una
revisión humana en una garantía universal. La aprobación registra quién
revisó el texto y vuelve a comprobar su estructura; la calidad semántica
depende de la revisión humana y, cuando se suministra, de un validador
semántico específico del caso.
