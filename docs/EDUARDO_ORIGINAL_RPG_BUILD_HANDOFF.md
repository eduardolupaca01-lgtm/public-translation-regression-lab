# Compilar el Tenshixgame RPG original de Eduardo mediante Windows en el repositorio público

**Este trabajo se refiere al programa auténtico**, NO a la interfaz experimental de traducción de textos del laboratorio. La compilación usa exclusivamente el código original de Eduardo y ejecuta las verificaciones originales en un runner efímero de Windows.

## Código y procedencia

- Código real de la GUI, plugin RPG Maker, instalador, pruebas, worker y modelos: repositorio PRIVADO `eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build`.
- Commit exacto: `091f7326101a61b02ecaa7a447370102f7952328` de `fix/tx765-rpg-live-bridge-native-paint-20261121`.
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

## Estado / límites

El preflight público no necesita secretos ni archivos privados. La compilación de la aplicación auténtica sí. Si el token o la contraseña no están configurados, GitHub genera **HOLD** y no finge disponer de un EXE probado.

El resultado no debe publicarse sin cifrar ni fusionarse a `main` automáticamente. El modelo real puede fallar en alguna comprobación; ese fallo debe diagnosticarse y corregirse en la fuente original, jamás eludirse creando traducciones simuladas o sustituyendo el motor por el del prototipo.
