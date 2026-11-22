# Compilar el Tenshixgame RPG original de Eduardo mediante Windows en el repositorio público

**Este trabajo se refiere al programa auténtico**, NO a la interfaz experimental de traducción de textos del laboratorio. La compilación usa exclusivamente el código original de Eduardo y ejecuta las verificaciones originales en un runner efímero de Windows.

## Código y procedencia

- Código real de la GUI, plugin RPG Maker, instalador, pruebas, worker y modelos: repositorio PRIVADO `eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build`.
- Commit exacto: `0faa1f31bf1069cada2b86b1d4ebce7344fd1035` de `fix/tx765-rpg-live-bridge-native-paint-20261121`.
- Workflow original: `.github/workflows/tx758-clean-current-baseline.yml` del mismo commit (emplea la suite TX765).
- Compilador público: `.github/workflows/eduardo-original-rpg-win64.yml` con `tools/replay_eduardo_original.py`.

El código privado, las DLL, los pesos V95 y el EXE sin cifrar NO se insertan en Git ni se suben como artifacts públicos. La distribución sin cifrar no está autorizada por los recibos de origen. Esta compilación está destinada exclusivamente a una prueba protegida por contraseña del propietario.

## Requisito de acceso: dos secretos en el repositorio público

Desde GitHub, abrir el repositorio público → **Settings → Secrets and variables → Actions → New repository secret** y añadir:

1. `EDUARDO_RPG_SOURCE_TOKEN`: token personal de GitHub de **alcance mínimo**, con acceso de SOLO LECTURA (`Contents: Read-only`) al repositorio privado `eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build`. No compartir el valor del token en chats, issues, archivos o logs. Crear el token en GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens, seleccionando únicamente ese repositorio de Eduardo. Los releases privados de V95 también requieren este acceso.
2. `EDUARDO_RPG_ARCHIVE_PASSWORD`: contraseña aleatoria fuerte de **al menos 20 caracteres**, elegida y conocida exclusivamente por el propietario. Se usará para cifrar con 7-Zip AES-256 el EXE final; no se envía al chat ni se incluye en el ZIP público.

## Ejecución

1. Abrir [el workflow del EXE original](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/workflows/eduardo-original-rpg-win64.yml).
2. Seleccionar **Run workflow** con la rama `build/eduardo-original-rpg-win64-20261121` (o volver a ejecutar los trabajos después de crear los dos secretos).
3. El runner verifica el SHA exacto del repositorio privado y comprueba los **26 pasos** del workflow original: GUI, V95 original, repaquetado de 21 componentes, 10 traducciones reales y 6 diálogos RPG, SQLite, instalación, primer y segundo arranque, integridad SHA, rollback y código de los plugins.
4. No ejecuta los dos pasos finales originales de modificación de la rama privada ni de creación de una release. El programa original se crea dentro del runner, se cifra con contraseña y solo el archivo cifrado y el recibo de hash pueden descargarse del artifact.
5. En caso de éxito, descargar el artifact **Eduardo-Tenshixgame-RPG-ORIGINAL-TX765-V95-Windows-TEST-ENCRYPTED**, extraer `Tenshixgame-RPG-TX765-V95-PRUEBA.7z` con 7-Zip y la contraseña propia, y ejecutar `Tenshixgame-RPG.exe` en Windows 10/11, primero sobre una copia del juego y de sus partidas.

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
