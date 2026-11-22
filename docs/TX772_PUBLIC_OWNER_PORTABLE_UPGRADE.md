# TENSHIXGAME RPG — TX772, actualización portátil verificada (prueba del propietario)

**Repositorio de trabajo:** `eduardolupaca01-lgtm/public-translation-regression-lab` (público).  
**Rama aislada:** `build/eduardo-original-rpg-tx772-public-update-20261122`.  
**Build:** [GitHub Actions #45034400292](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/45034400292).  
**Fuente de aplicación:** commit fijado `aeb9ff9326e418fbabe2d53dff7891f4fb340c37`, descargado con permisos de solo lectura en un Windows efímero. No se modifica el repositorio de origen.

## Defecto que motiva la corrección

El TX771 instalaba el original V95 bajo `<Juego>/Tenshixgame-IA/` en un juego nuevo, pero un EXE reconstruido con otro checksum del paquete podía buscar `App/<checksum-nuevo>` dentro de un sidecar que aún contenía exclusivamente `App/<checksum-viejo>`. La validación abortaba antes de preparar el paquete nuevo. La nueva actualización reconoce únicamente su propia instalación marcada y verificada.

## Cambios TX772

- `tools/tx772_public_portable_upgrade.py` añade **solo durante la compilación Windows**, después de comprobar el SHA de la fuente, el adaptador Go de actualización en la copia de trabajo efímera.
- En una instalación existente exige marcador oficial, directorios sin enlaces y SHA256 exacto del trabajador antiguo antes de crear la nueva versión de la aplicación.
- Instala el nuevo paquete firmado en otra carpeta `App/<checksum>` del **mismo disco del juego**, sin reescribir las partidas, `plugins.js` ni la caché.
- El host verifica los 22 recursos del motor antiguo antes de actualizar; una sustitución de modelos exige mecanismo de reemplazo con respaldo del instalador original, y los 22 recursos resultantes deben coincidir con el manifiesto del nuevo paquete.
- El marcador de propiedad se actualiza mediante archivo temporal y renombrado tras comprobar el SHA del trabajador nuevo. Si la instalación está alterada o incompleta, debe detenerse; no se eluden estas verificaciones.
- Se conservan las pruebas de JS, la caché duradera, la compatibilidad de nombre/diálogo y **los 26 controles originales** del motor neuronal V95. El EXE no se publica sin cifrar.
- `tools/tx772_accept_previous_on_windows.ps1` realiza la prueba adicional con los dos ejecutables originales descifrados exclusivamente en Windows CI: instalación TX771, actualización TX772, persistencia de caché, integridad del juego y ausencia de una instalación global en el perfil Windows.

## Requisitos de entrega y límites

Un `SUCCESS` confirma que el ejecutable construido y las pruebas automatizadas indicadas aprobaron; **no confirma** todavía que el videojuego específico del propietario muestre todos sus diálogos japoneses en español. Las extensiones de mensajes personalizadas, calidad semántica, textos con números y superposiciones aún requieren una prueba visual en su copia real.

El titular debe probar el paquete en una **copia del juego cerrado**, no mezclar el complemento de TX203, conservar sus partidas/respaldos, ejecutar el botón de instalación/actualización de TX772 y reiniciar `Game.exe`. Comprobar F10, cinco escenas con nombre de personaje y opciones, segundo arranque, carpeta `Tenshixgame-IA`, cache y cierre de procesos; si falla, conservar el diagnóstico sin compartir tokens ni contraseñas.

La versión TX771 se conserva intacta. La actualización TX772 no borra automáticamente carpetas antiguas `App` para evitar borrar archivos ajenos; por ello puede ocupar temporalmente más espacio **dentro del disco del juego**, no en la unidad de perfil del usuario. Las antiguas versiones pueden retirarse solamente después de acreditar su identidad y confirmar una copia de seguridad.

**Archivo previsto:** `Eduardo-Tenshixgame-RPG-ORIGINAL-TX772-PORTABLE-V95-Windows-TEST-ENCRYPTED` (Artifact de GitHub Actions); `Tenshixgame-RPG-TX772-PORTATIL-V95-PRUEBA.7z` protegido con AES-256 y la contraseña ya configurada por el propietario. No afirmar que está disponible hasta que aparezca el artifact de un run terminado en `success`.
