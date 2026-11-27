# R31 — finalización completa del ejecutable onefile

Evidencia: 45923729201 aprobó Windows y Ubuntu. 45923772294, job 140260307661, confirmó tres cierres limpios de Python y SQLite (dos sueltos y uno empaquetado) y los dos recorridos de traducción/restauración con OPUS auténtico. El fallo fue WinError 5 al eliminar packed/IA Traductora/.local/Rpg/engine/IATraductora.exe, no un bloqueo SQLite.

PyInstaller --onefile ejecuta un bootloader padre que permanece activo después de terminar Python mientras limpia los archivos extraídos. Documentación: https://pyinstaller.org/en/stable/feature-notes.html#onefile-mode-and-temporary-directory-cleanup. Esta es la causa probable del bloqueo; el registro anterior no contenía el handle del bootloader.

El helper registra ahora el PID exacto devuelto por spawn en un recibo local atómico, asociado al PID del juego. La aceptación abre los dos handles mientras Ruby sigue vivo, verifica que ambos ejecutan el binario instalado y exige salida normal de los dos. Conserva la verificación de SQLite, lock, persistencia, restauración y partidas. Tras todas las comprobaciones elimina el ejecutable de cada fixture generado, y mantiene la limpieza estricta del workspace. No se amplían tiempos de traducción ni se ignoran errores de permisos. No se cambia OPUS, las reglas de calidad, los plugins de presentación ni la rama estable.

La validación sigue usando Ruby de escritorio y recursos sintéticos; no equivale a RGSS301.dll real.
