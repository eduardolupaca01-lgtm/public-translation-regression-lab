# Auditoría comparativa: TX203-RC, Ultra Ren'Py y Tenshixgame RPG TX769

**Fecha:** 22 de noviembre de 2026. **Alcance:** investigación de fuentes y pruebas, **sin modificar el ejecutable ni juegos**. Este informe público no contiene archivos privados, tokens, rutas personales, textos del juego ni pesos neuronales.

## Conclusión ejecutiva

Las 26 pruebas Windows de TX769 y el resultado del motor neuronal prueban construcción y funcionamiento sobre fixtures, **NO** que un videojuego con ventanas personalizadas reciba, identifique, sustituya y reutilice sus traducciones. Hay al menos dos bloqueos de diseño capaces de producir «motor con miles de traducciones» y «casi nada traducido» simultáneamente:

1. **Claves divergentes**: TX769 usa SHA-256 del idioma + la cadena original exacta. Si el escáner guardó una frase con una disposición y el juego la presenta con prefijo de actor, secuencias de escape, espacios, otros saltos de línea o fragmentos, el resultado persistido no necesariamente coincide con la clave que consulta el renderizador.
2. **Repintado tardío prohibido**: después de un dibujo japonés síncrono del juego, TX769 activa `_tx765UnsafeSynchronousPaint` y `Window_Message.update()` retorna sin repintar. Una respuesta V95 recibida después ya no cambia los píxeles de esa página. Las pruebas incluyen deliberadamente la garantía «no superponer» pero no certifican el repintado del título concreto.

La integración de nombres, superficies y plugins personalizados añade condiciones de rechazo. TX769 puede mostrar `Puente: sin traducción lista` aun cuando el worker V95 haya precalculado traducciones de otros registros. La caché nueva TX769 guarda pares SQLite verificados, pero **no corrige las claves divergentes ni desbloquea el repintado de una ventana específica**. La persistencia efectiva requiere un par **guardado Y consultado bajo la misma clave**.

**Diagnóstico: NEEDS REVISION para el juego observado.** No se atribuye el fallo definitivo a uno de los dos mecanismos sin los diagnósticos de esa instalación.

## Fuentes revisadas y niveles de evidencia

1. [TX769: ejecución pública y 26 gates de Windows](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44987427230): SUCCESS. Ejecuta regresiones de nombre, caché, modelo neuronal real y empaquetado. Su juego de prueba es sintético, no el juego comercial del propietario.
2. **Auditoría histórica interna de TX203**: paquete verificado con SHA-256 `d64ae17ef473a273534088a463b75fc4f041867385f0997fe08f510b2cd190fd`; lectura mediante `tx710_compare_original_tx203_clean.py`, `tx577_compare_historic_tx203.py` y `tx657_review_tx203_native_game_hooks.py`. El EXE histórico y su release privada no pudieron descargarse directamente con la conexión pública de Eduardo; por tanto, los detalles originales se sustentan en fuentes auditadas, no en una nueva ejecución local de TX203-RC.
3. [Ultra Ren'Py Translator: repositorio público](https://github.com/robinpierr/Ultra-Renpy-Translator-Public): distribución, descripción y scripts. El archivo público [RPG Maker overlay](https://github.com/robinpierr/Ultra-Renpy-Translator-Public/blob/main/dist/lib/modular/data/rpgmaker_overlay.js) implementa la ruta de dibujo aquí comparada.
4. [Ultra Ren'Py v0.06 — Full Release Report](https://www.patreon.com/UltraRenpyTranslator/posts/ultra-renpy-v0-155215751): explica correcciones **de Ren'Py** basadas en `encode_say_string`, IDs hash MD5 nativos, archivos `.rpy` de diálogo y eliminación de cachés `.rpyc`. **No** constituye una prueba de RPG Maker.
5. Código privado leído, sin copiarlo aquí: fuente de instalación de TX769 fijada en el commit `08a181052f9c5eaa7ef6c71bb11eed487b7f97c0`, plantilla `tx757-patched-template.js`, núcleo del adaptador y flujo de compilación. Solo se publica la caracterización técnica mínima.

## Cómo se construyó TX203-RC y qué se conservó

La documentación histórica identifica un EXE original TX203-RC para Windows que incluía un paquete neuronal local de OPUS/Argos y un conjunto original de recursos del motor. La fuente archivada muestra conectores de ventanas MV/MZ, decisiones, preservación de nombres y mecanismos de repintado. El auditor comparativo comprobó que TX203 tenía interceptores más amplios y rutas de repintado tardío; también identificó problemas de superposición y reejecución de `startMessage`. **TX203 no era perfecto**, y que funcionara en una prueba del usuario no acredita todos los juegos.

La cadena TX769 vuelve a construir el trabajador local y verifica por manifiesto y SHA los **21 componentes originales de modelo y supervisor** y el JavaScript que Go incorpora al EXE. La compilación pública aprobó los 26 pasos; no hay indicio confirmado de que se haya eliminado el modelo. En cambio, **sí cambió el comportamiento de los interceptores**: la ruta moderna restringe `Bitmap.drawText` genérico a etiquetas conocidas de interfaz y limita la sustitución de diálogo a una ventana de mensaje verificable, con guardas de estado y superficie. Es una restricción deliberada, susceptible de reducir la cobertura.

La fuente pública del proceso Windows demuestra integridad del EXE; **no** demuestra qué versión del plugin está instalada actualmente en la copia del juego del usuario.

## Comparación técnica

| Dimensión | TX203-RC histórico | Ultra Ren'Py (RPG Maker público) | TX769 |
|---|---|---|---|
| Traducción precalculada | Modelo local y caché | Diccionario JSON de juego, preparado previamente | SQLite del worker V95, sincronizada al JS por `/updates` |
| Clave de consulta | Interceptores históricos; comportamiento exacto no verificado en el juego actual | Exacta, `trim()` y forma normalizada sin controles/espacios | `SHA256(sourceLanguage + NUL + source)`, cadena exacta |
| Captura de diálogo | Hooks de mensajes y ventanas | `Game_Message.add`, `Window_Base.convertEscapeCharacters`, `drawTextEx`, `Bitmap.drawText` | `Game_Message.add` y `Window_Message.startMessage`, con guardas de propiedad |
| Nombres separados | Protección histórica de actores | Hooks generales, también nombres y otras ventanas | Pruebas estrictas de propietario, bitmap, nombre y fuente |
| Si el modelo llega tarde | Existía repintado, con riesgos conocidos | El diccionario normalmente ya está preparado; si no hay entrada, devuelve original | `Window_Message.update` puede repintar sólo bajo condiciones estrictas; en dibujo síncrono protegido se abandona |
| Caché al reiniciar | Persistencia local del trabajador histórico | JSON dentro de la carpeta de datos del juego; se vuelve a cargar | SQLite V95 + caché por ruta absoluta del juego e idioma en `LOCALAPPDATA` |
| Protección de estado del juego | No acreditada para todos los títulos | Hooks amplios, potencial riesgo de afectar otra lógica | Más conservadora: rechaza sustituciones ambiguas para preservar estados |
| Evidencia comercial | El propietario comunica funcionamiento; no repetido aquí | El usuario comunica funcionamiento; repo/documentos describen capacidades | El propietario comunica ausencia de traducción; CI sólo probó fixtures |

**No confundir dos tecnologías distintas de Ultra:** el informe v0.06 describe archivos nativos de Ren'Py con hashes propios de ese motor; el overlay público RPG Maker usa un diccionario y hooks JavaScript. No basta copiar un algoritmo MD5 de Ren'Py para reparar MV/MZ.

## Hallazgos del código moderno

### A. El cambio en hooks reduce la cobertura del título

En TX769 existe `Bitmap.prototype.drawText`, pero su cuerpo indica que **sólo sustituye etiquetas deterministas de HUD/menú**. La ruta general de diálogo no pasa por esa traducción. El `Window_Base.drawTextEx` del menú se condiciona a tipos de ventana, sin cobertura global arbitraria. Ultra, por el contrario, consulta `tr(text)` en varios puntos de captura y dibujo de RPG Maker, además de métodos de registros. **No es recomendable copiar sus hooks indiscriminadamente**: podrían traducir nombres editables, comandos o texto de lógica del juego.

### B. Bloqueo irrevocable de pintura tardía para una clase de ventanas

En la plantilla TX769, `WM.prototype.startMessage` observa dibujo sincrónico en su bitmap; si el primer dibujo no pudo traducirse, define `_tx765UnsafeSynchronousPaint=true`. En `WM.prototype.update`, la primera condición es `if(this._tx765UnsafeSynchronousPaint)return result;`. Por tanto, una traducción que llegue después no puede actualizar esa página por ese camino. Para el primer dibujo traducido se exige, entre otros requisitos, `state.index===0`, texto japonés exacto, bitmap identificado, traducción ya validada y espacio suficiente. Las ventanas de nombre sin dueño verificable bloquean otras rutas. Se evita la superposición, pero puede quedar japonés persistente en la pantalla actual.

### C. Persistencia no equivale a reutilización

TX769 añadió espejo individual asíncrono de pares SQLite. Sin embargo, su función `key(source)` usa el idioma + el texto **byte por byte**. Su `localCachePath` también deriva de la ruta real del juego (tratando especialmente `www`) y del idioma configurado. Cambiar de copia o ubicación, o que el texto fuente cambie por un plugin, produce un identificador distinto; pueden quedar miles de traducciones válidas en disco sin acertar el diálogo mostrado.

### D. El contador F10 no valida el efecto visual ni la versión instalada

La interfaz indica `TENSHIXGAME RPG · V95` independientemente de que la fuente se etiquete TX768 o TX769: **la cabecera no identifica el commit instalado**. `Recibidos` consulta totales del motor; `Mostrados` registra sustituciones confirmadas. El diagnóstico previo compartido por el usuario mostraba `Recibidos 7820/8591`, `Mostrados 8`, `caché 2968` y `Puente: sin traducción lista`: son contadores de ámbitos diferentes y no prueban que se hayan perdido exactamente 4.852 traducciones. Sin un informe fresco posterior a TX769 y el hash del plugin del juego, no se puede certificar qué versión estaba corriendo.

### E. Rechazos de calidad y riesgo de validar demasiado

El historial registra rechazos por números omitidos, traducciones idénticas y restos japoneses. Son reales como categorías, pero sin ejemplos de esas frases no demuestran que esos rechazos expliquen la mayoría de diálogos sin traducir. Desactivar la validación para subir `Mostrados` sería un falso arreglo: reintroduciría traducciones truncadas o corruptas.

## Verificaciones decisivas antes de otra versión

**P1 — Identidad:** calcular SHA-256 del JS realmente instalado dentro del juego; comprobar el registro de instalación y la posición final en `plugins.js`. Comparar con el SHA del ejecutable TX769 entregado. El F10 no basta.

**P2 — Cadena para una sola línea:** en una copia de prueba del mismo juego y escena, correlacionar (sin enviar texto privado ni token al repositorio público): fuente cruda de `Game_Message`, fuente que pinta `Window_Message`, hash de petición, hash de entrada SQLite, resultado de `lookup`, estado `_tx765UnsafeSynchronousPaint`, último motivo de salto y píxeles efectivamente dibujados.

**P3 — Persistencia de una frase conocida:** comprobar `cache_entry_persisted` / `cache_entry_loaded`, `sqlite_update_rejected`, `native_lookup_untranslated` y `bridge_descriptor_located` en el diagnóstico privado del usuario. Reiniciar **desde exactamente la misma ruta** y verificar que la frase guarda y recupera el mismo hash. No borrar cachés como primera medida.

**P4 — Tiempo del primer dibujo:** abrir una frase no traducida y dejar el diálogo quieto mientras el motor completa la traducción. Si la entrada válida aparece pero la página no cambia, revisar el guard de dibujo síncrono. La prueba debe asegurar que nunca se agregue una capa española encima de los píxeles japoneses.

**P5 — Calidad y coincidencia:** agrupar las frases rechazadas por código y analizar muestras controladas, sin desactivar protecciones numéricas ni comandos. La normalización segura debe preservar todos los códigos de control y los nombres originales.

**P6 — Aceptación real, no simulación:** ejecutar el juego concreto, con sus plugins y con dos arranques consecutivos; confirmar al menos varios diálogos con nombres, elecciones y fragmentos dinámicos, sin mezcla japonés/español y con reutilización en disco. No aprobar un nuevo EXE basándose sólo en los mismos fixtures de CI.

## Priorización y límites

| Hipótesis | Evidencia actual | Cómo confirmarla |
|---|---|---|
| Protección de pintura síncrona impide sustituir resultados tardíos | **Mecanismo de código confirmado**; falta observarlo en ese juego | Estado de ventana + hora de llegada del resultado |
| Diferencia entre clave del escáner y frase presentada | **Mecanismo de código confirmado**; caso real todavía hipotético | Hash de fuente precargada frente a hash de fuente visible |
| Caché escrita pero consultada con otra identidad | **Posibilidad confirmada por diseño** | Comparar raíz canónica, idioma y clave entre dos lanzamientos |
| Worker/modelos faltantes en el EXE TX769 | **Poco compatible con pruebas de empaquetado** | Verificar instalación local, no repetir sólo CI |
| Plugin instalado viejo/desincronizado | **No descartable**; F10 carece de versión TX | Hash del JS real + recibo del instalador |
| Faltan traducciones por calidad neuronal | **Rechazos históricos confirmados**; proporción de la escena desconocida | Logs de `translation_rejected` + frases afectadas |

**Decisión:** no lanzar TX770 a ciegas. La siguiente intervención debe medir una línea real de extremo a extremo, recuperar su traducción en el primer dibujo o realizar una sustitución segura, y demostrar reutilización tras reiniciar. Sólo entonces compilar un EXE para pruebas de ese juego.

## Fuentes públicas para inspección

- CI real TX769: https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44987427230
- Ultra RPG overlay: https://github.com/robinpierr/Ultra-Renpy-Translator-Public/blob/main/dist/lib/modular/data/rpgmaker_overlay.js
- Ultra README: https://github.com/robinpierr/Ultra-Renpy-Translator-Public
- Informe Ultra v0.06: https://www.patreon.com/UltraRenpyTranslator/posts/ultra-renpy-v0-155215751

*Límites de evidencia:* esta auditoría no abre el juego del propietario, no dispone de los registros nuevos de TX769 ni ha ejecutado directamente el EXE histórico TX203-RC con la conexión de Eduardo. Las causas propuestas para ese título son hipótesis sujetas a las comprobaciones P1–P6, no arreglos ya demostrados.
