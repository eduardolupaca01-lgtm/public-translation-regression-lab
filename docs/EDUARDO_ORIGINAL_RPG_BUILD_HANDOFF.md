# Compilar el Tenshixgame RPG original de Eduardo mediante Windows en el repositorio público

**Este trabajo se refiere al programa auténtico**, NO a la interfaz experimental de traducción de textos del laboratorio. La compilación usa exclusivamente el código original de Eduardo y ejecuta las verificaciones originales en un runner efímero de Windows.

## Código y procedencia

- Código real de la GUI, plugin RPG Maker, instalador, pruebas, worker y modelos: repositorio PRIVADO `eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build`.
- Commit de esta prueba: `1e79a39df94be810918f50a377cfc1efb4e95f8f` de `fix/tx771-portable-game-local-worker-and-render-20261122` (rama privada, no rama principal).
- Workflow original: `.github/workflows/tx758-clean-current-baseline.yml` del mismo commit (emplea la suite TX765).
- Compilador público: `.github/workflows/eduardo-original-rpg-win64.yml` con `tools/replay_eduardo_original.py`.

El código privado, las DLL, los pesos V95 y el EXE sin cifrar NO se insertan en Git ni se suben como artifacts públicos. La distribución sin cifrar no está autorizada por los recibos de origen. Esta compilación está destinada exclusivamente a una prueba protegida por contraseña del propietario.

## Requisito de acceso: dos secretos en el repositorio público

Desde GitHub, abrir el repositorio público → **Settings → Secrets and variables → Actions → New repository secret** y añadir:

1. `EDUARDO_RPG_SOURCE_TOKEN`: token personal de GitHub de **alcance mínimo**, con acceso de SOLO LECTURA (`Contents: Read-only`) al repositorio privado `eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build`. No compartir el valor del token en chats, issues, archivos o logs. Crear el token en GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens, seleccionando únicamente ese repositorio de Eduardo. Los releases privados de V95 también requieren este acceso.
2. `EDUARDO_RPG_ARCHIVE_PASSWORD`: contraseña aleatoria fuerte de **al menos 20 caracteres**, elegida y conocida exclusivamente por el propietario. Se usará para cifrar con 7-Zip AES-256 el EXE final; no se envía al chat ni se incluye en el ZIP público.

## Ejecución

1. Abrir [el workflow del EXE original](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/workflows/eduardo-original-rpg-win64.yml).
2. Seleccionar **Run workflow** con la rama `build/eduardo-original-rpg-tx771-portable-20261122` (o volver a ejecutar los trabajos después de crear los dos secretos).
3. El runner verifica el SHA exacto del repositorio privado y comprueba los **26 pasos** del workflow original: GUI, V95 original, repaquetado de 21 componentes, 10 traducciones reales y 6 diálogos RPG, SQLite, instalación, primer y segundo arranque, integridad SHA, rollback y código de los plugins.
4. No ejecuta los dos pasos finales originales de modificación de la rama privada ni de creación de una release. El programa original se crea dentro del runner, se cifra con contraseña y solo el archivo cifrado y el recibo de hash pueden descargarse del artifact.
5. En caso de éxito, descargar el artifact **Eduardo-Tenshixgame-RPG-ORIGINAL-TX771-PORTABLE-V95-Windows-TEST-ENCRYPTED**, extraer `Tenshixgame-RPG-TX771-PORTATIL-V95-PRUEBA.7z` con 7-Zip y la contraseña propia, y ejecutar `Tenshixgame-RPG.exe` en Windows 10/11, primero sobre una copia del juego y de sus partidas.

## Evidencia actualizada de TX765 (2026-11-22)

- Fuente original congelada: `0faa1f31bf1069cada2b86b1d4ebce7344fd1035`, que incluye descubrimiento de las dos grafías históricas del puente, reemplazo en primer dibujo de Windows y diagnóstico de archivos.
- El compilador público compara sus 26 pasos contra el workflow original de ese commit y **rechaza** nombres, orden, SHA o correcciones ausentes.
- [Compilación pública #44973583953](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44973583953): la prevalidación del compilador terminó SUCCESS; esa compilación Windows anterior terminó con HOLD por `EDUARDO_PRIVATE_SOURCE_READ_ACCESS_REQUIRED`, antes de leer archivos privados, iniciar inferencia V95 o generar un EXE.
- [Pruebas públicas TX765 #44973042111](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44973042111): Windows y Linux SUCCESS, solo reglas públicas de dibujo y lectura, no prueba del motor original.
- [Regresiones generales #44973583898](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44973583898): SUCCESS en Windows y Linux.
- Sin token autorizado, ninguna compilación pública puede descargar automáticamente el repositorio privado, su archivo V95 de 604 MB ni reconstruir la aplicación. No fabricar una actualización de prueba ni publicar el binario anterior como corregido.

## Estado / límites

El preflight público no necesita secretos ni archivos privados. La compilación de la aplicación auténtica sí. Si el token o la contraseña no están configurados, GitHub genera **HOLD** y no finge disponer de un EXE probado.

El resultado no debe publicarse sin cifrar ni fusionarse a `main` automáticamente. El modelo real puede fallar en alguna comprobación; ese fallo debe diagnosticarse y corregirse en la fuente original, jamás eludirse creando traducciones simuladas o sustituyendo el motor por el del prototipo.

## Corrección TX766 de la autoprueba de V95

La ejecución 44974646131 llegó a superar las primeras cinco verificaciones originales y falló en el control 6. Una comprobación aislada en el servidor público, run 44975204310, localizó el fallo en TX760_SOURCE_SELFTEST. Al revisar el código privado se detectó que se leía `greeting_map` antes de inicializarlo. El commit `0faa1f31bf1069cada2b86b1d4ebce7344fd1035` mueve la inicialización a su posición correcta, sin cambiar los pesos del motor ni debilitar la comprobación de texto. Esta compilación nueva exige ese commit exacto. No declarar PASS del autodiagnóstico hasta confirmarlo en CI.

## TX766 — comprobación de integridad del ejecutable

Después de superar 16 de los 26 controles, la ejecución 44975387829 detectó que el test Go de integridad no reconocía el Git blob exacto del código de la interfaz que el propio fijador de hashes había firmado. Se amplió exclusivamente la lista de fuentes firmadas para incluir el blob verificado `7036a0c56a1f8a8418fdc456f77a5acac3e66996` bajo el esquema original, manteniendo todas las comprobaciones de SHA256 del trabajador, complemento y 21 recursos del motor. La nueva fuente privada fijada es `0faa1f31bf1069cada2b86b1d4ebce7344fd1035`. Esta nota no equivale a una prueba aprobada: el workflow vuelve a ejecutar los 26 controles originales.

## TX767 — Corrección de diálogo con ventana de nombre independiente

Nueva versión de origen inmutable: `0faa1f31bf1069cada2b86b1d4ebce7344fd1035` en `fix/tx767-rpg-visible-speech-20261122`. La compilación de Windows conserva las 26 verificaciones del motor y añade una guardia de fuente que exige la sustitución de diálogo ante namebox independiente (`separateName`, `nameVisible`, `localNameBox`). El ZIP de 7-Zip protegido se identifica como `Tenshixgame-RPG-TX767-V95-PRUEBA.7z` y solo se publica cifrado. Esta corrección debe probarse dentro del juego después de actualizar su plugin con el botón **Instalar traducción**; sustituir el EXE no reescribe `www/js/plugins/TenshixgameRPGLive.js` por sí solo. No se garantiza que el juego completo esté corregido hasta esa comprobación.

La primera fuente TX767 tenía un texto de confirmación del instalador incompatible con los tests heredados; la nueva fuente fijada `0faa1f31bf1069cada2b86b1d4ebce7344fd1035` conserva la frase verificada y añade la explicación del botón **Instalar traducción**. No se cambia el motor ni la lógica de instalación.

## Ajuste TX767 del control de instalación

La compilación pública 44979280454 aprobó 24/26 verificaciones, incluyendo motor V95 y render nativo, pero la comprobación de instalación TX591 exige que el mensaje de éxito preserve las palabras históricas `Traductor V95 instalado` y `el idioma original se detecta`, que se habían omitido al aclarar el paso de reinstalación. La rama privada `fix/tx767-rpg-visible-speech-20261122` ahora mantiene ambas frases exactas y conserva el consejo de cerrar y abrir el juego (commit `0faa1f31bf1069cada2b86b1d4ebce7344fd1035`). Esto cambia exclusivamente el texto del mensaje, sin desactivar ni modificar la instalación ni la restauración de complementos. La nueva compilación reevalúa obligatoriamente los 26 controles.

## TX768 — recuperar solicitudes perdidas y primer dibujo de voz con namebox independiente

Después de la ejecución TX767 #44980315118 (26/26 gates PASS, **no** equivale a aceptación del usuario) el propietario confirmó que siguen escenas japonesas sin reemplazo. El nuevo diagnóstico distingue la ausencia de solicitudes de diálogo visible de las traducciones de precarga; la evidencia histórica muestra `foregroundRequests=0` y también rechazos V95 por calidad. No atribuir automáticamente esos rechazos al motor o a un token sin observar la sesión.

Se descubrió una ruta sin probar por TX767: `request(text)` abandonaba mensajes que comenzaban por `\\N<name>`; un plugin nativo podía consumir ese prefijo y dibujar solo japonés hablado durante `startMessage`, pero la intervención previa exigía una igualdad de la frase completa. TX768 encola únicamente el cuerpo reconocido, preserva el nombre original, y reemplaza el cuerpo en el primer dibujo únicamente cuando la ventana de nombre pertenece a esa ventana de mensaje, las superficies son independientes, el japonés coincide exactamente y la traducción española está validada y cabe. Si alguna condición no se cumple no dibuja una segunda capa española.

La regresión `tests/js/test_tx765_no_overdraw_sync_custom_start.js` ahora comprueba marcadores dinámicos, actor con comillas, cuerpo separado, solicitudes únicas, bitmap propio, bitmap compartido, namebox ajeno, caché ausente y no-superposición. Un precontrol del workflow público ejecuta esa prueba sobre el código fuente privado descargado antes de reconstruir el motor V95. Luego se exigen los 26 controles originales sin omitir ninguna fase.

**Límite:** incluso con PASS, no se certificará el arreglo de las escenas concretas del propietario sin reinstalar el plugin dentro de la copia del juego y comprobar F10 + logs `*.live.json.diagnostics.jsonl`. El EXE no reemplaza automáticamente el JS previamente instalado dentro del juego. No compartir el token GitHub ni la contraseña AES-256 en mensajes.

## TX769 — persistencia SQLite y diagnóstico F10 de una sesión real

La captura F10 después de TX768 registra `Recibidos 7820/8591`, `Mostrados 8 · caché 2968`, `Puente: sin traducción lista` y el archivo `embedded-v87-status.json` registra `previous=7801`, `new=19`, `failed=711`, `pending=60`, `scanThrottled=true`, `foregroundRequests=0`. No interpretar los 7.820 «recibidos» como 7.820 diálogos mostrados, ni el estado de reintento como motor desactivado.

La rama privada `fix/tx769-rpg-sqlite-durable-restore-20261122` (commit exacto `08a181052f9c5eaa7ef6c71bb11eed487b7f97c0`) repara dos fallos de fuente: (1) las traducciones que llegan por `/updates` no tenían espejo durable individual, por lo que se podía perder la recuperación si el snapshot general superaba 5 MiB o no se guardaba; (2) una entrada individual anterior podía sobreescribir una revisión SQLite más nueva. El espejo emplea E/S asíncrona, verifica el archivo previo y nunca modifica JSON, partidas o motor del juego. Además añade el evento `native_lookup_untranslated` limitado y sin texto de juego ni token para diagnosticar escenas que siguen en japonés.

Nuevo control bloqueante: `tests/js/test_tx769_sqlite_durable_restart.js`, ejecutado sobre la plantilla real del complemento **antes** de reconstruir V95 en Windows. Simula un registro SQLite verificado, caché individual anterior incorrecta, snapshot general mayor de 5 MiB, reinicio con feed histórico vacío y ausencia de llamadas de traducción repetidas. El flujo público sigue exigiendo los 26 controles originales y cifra el único EXE con 7-Zip. Su PASS no sustituye la observación del juego real; queda pendiente la causa de todas las frases japonesas de formato personalizado y de los 711 rechazos por calidad. 

## TX770: diálogo visible, reutilización de caché y compatibilidad acotada

El propietario sigue viendo japonés pese a que V95 ya dispone de traducciones. El complemento real está activo y cargado al final de plugins.js. El único diagnóstico disponible era un ENOENT de snapshot; esto no demuestra que el worker carezca de traducciones. El análisis comparó el mecanismo del TX203-RC histórico con el adaptador RPG Maker de Ultra, sin adquirir ni copiar su motor de pago.

**Código fuente privado del mismo titular:** \`fix/tx770-rpg-foreground-cache-20261122\`, SHA exacto \`c6ed1b08d1140eec5f1e7fa6f46de86b0072ac33\`. Corrige un fallo probado: \`add()\` TX769 consultaba \`retryAfter\` ANTES de cargar desde disco una traducción guardada. TX770 siempre carga la entrada primero y limita a un reintento visible cada 30 segundos si faltó el resultado. Reconoce SOLO variaciones de espacio validadas en mensajes sin controles o nombres, evita colisiones y conserva la nueva variante en su propia entrada exacta. Registra \`runtime_bootstrap\`, \`native_adapter_installed\`, \`v95_sqlite_feed_unavailable\` y mantiene los diagnósticos existentes, sin texto ni secretos.

Los gates públicos nuevos deben aprobar \`test_tx770_foreground_cache_before_cooldown.js\` y \`test_tx770_sqlite_whitespace_recovery.js\` **antes** de los 26 controles privados originales. Los fixtures de pruebas no son el juego comercial ni demuestran que sus efectos de texto personalizados ya sean compatibles; no desactivar controles de nombres, opciones y no-superposición para aumentar artificialmente los contadores. El EXE incorpora el modelo local OPUS/Argos verificado, sin conexión a API de pago ni software adicional.

El artefacto se publica **solo cifrado** y sus archivos de código/modelos originales no aparecen en el repositorio público.

## TX770 — compatibilidad de actualizaciones in situ desde TX769 del propietario

**Hallazgo adicional revisado antes de entregar:** la cadena TX769 de JavaScript realmente instalada por el propietario tiene SHA-256 `bd4bbbbde3e9151ed40aef1cd75d3e7b7175da833efa5bffa4083fb1b82edd1e`. Al revertir únicamente el hash fijado del trabajador V95, reproduce byte por byte el blob oficial de plantilla TX769 `28417712f079c9a2fa836aa7641153d6872bc9cf`. El Go `rpgOwnedPluginHash` de anteriores versiones no reconocía ese SHA concreto, por lo que la nueva aplicación podía rechazar su actualización con `TX395_JOURNAL_OR_SOURCE_MISMATCH`.

Se añadió **sólo ese hash único y revisado**, sin copiar archivos ajenos ni debilitar la protección contra modificaciones arbitrarias. El nuevo gate público `TX770_OWNER_TX769_PREDECESSOR_HASH_PASS` exige un test Go que apruebe ese SHA y rechace archivos modificados, **además** de los dos controles JavaScript y los 26 controles originales Windows. El paquete sigue cifrado y contiene el motor local original, sin API comercial.

## TX771 — motor original V95 y caché PORTÁTILES por videojuego (22 de noviembre de 2026)

**Código privado exacto**: `1e79a39df94be810918f50a377cfc1efb4e95f8f` de la cuenta Eduardo. El EXE autosuficiente pregunta primero por `Game.exe`, detecta un único RPG Maker MV/MZ legítimo y prepara su V95 verdadero con 22 archivos originales verificados en `<Juego>/Tenshixgame-IA/`, con contenido de `App`, `.local/TENSHIXGAME-RPG/engine`, caché española, modelos Argos y archivos temporales. Esto vale para C:, D:, E: y juegos completos trasladados a otros PCs. No necesita un API ni motor ajeno. El instalador crea un marcador de propiedad SHA del trabajador y rechaza carpetas ya existentes sin prueba de propiedad; conserva todo el resto del juego, sus plugins y partidas.

**Nueva recuperación de TX769/TX770**: si el usuario borró el antiguo diario de C:, el nuevo instalador verifica el JS previo como código oficial (hash SHA o fuente TX770 completa normalizada con el Git blob inmutable), y reconstruye el respaldo desde un único registro `$plugins` generado de forma verificable por el instalador. No modifica ni adopta complementos desconocidos. Si falla la comprobación, aborta y conserva archivos en lugar de forzar cambios. 

**Dibujo personalizado**: únicamente durante `Window_Message.startMessage`, intercepta la salida del conversor nativo original de esa instancia, después de que procese códigos de nombres dinámicos y antes de que `MPP_MessageEX` o `SRD_ShakingText` dibujen glifos. Acepta solamente una traducción completa, medida y validada en caché; no altera la ventana del personaje, entradas de juego ni el render global, y no pinta español encima de japonés ya dibujado. Prueba Windows del core oficial `TX771 CUSTOM NATIVE CONVERTER FIRST PAINT PASS`, además de la anterior TX768.

**Pruebas de liberación**: después de los 26 pasos originales de inferencia neural V95 real, se ejecuta el EXE real en un videojuego MV sintético dentro de la unidad de trabajo, comprueba que instale su IA y el marcador original dentro del juego (no en C:), copia toda la carpeta a otra ubicación y abre el EXE con esa copia sin reinstalar el motor ni cambiar su hash. No se publica el EXE sin el PASS de estos pasos ni sin cifrado AES-256. **La simulación de ventanas NO constituye prueba en el título específico del propietario**: tras descargar debe verificarse japonés→español, nombres separados, persistencia en disco y reinicio de Game.exe sobre una copia legítima. Cualquier resultado fallido queda como HOLD para corrección, no se declarará versión funcional a ciegas.

Flujo Windows público protegido: `https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/workflows/eduardo-original-rpg-win64.yml` (rama TX771 nombrada arriba).
