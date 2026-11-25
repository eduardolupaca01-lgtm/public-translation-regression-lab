# R23-P3 — Retirar el OCR; requisito de traducción RPG nativa

La prueba de usuario de R23-P2 rechazó explícitamente la ventana de reconocimiento visual. Se retira por completo el modo visual y se restaura la base funcional R23-P1, preservando la lógica acumulada de R22 y todas las pruebas nativas. No hay captura de pantalla, panel OCR, dependencia Pillow ni opción de seleccionar una región. No se eliminan datos, cachés ni partidas del usuario. El historial de commits conserva P2, pero no forma parte de esta compilación.

## Halva: estado pendiente, no anunciar compatibilidad

La detección de `GameConfig.sbcf` y `GamePackages` sigue siendo de solo lectura. No se puede considerar un juego Halva compatible hasta verificar una vía de integración nativa. No se ha podido leer el contenido de los RAR aportados por errores del entorno antes de la apertura de archivos; no hay evidencia de que sean archivos corruptos o demasiado grandes.

El manual oficial documenta compilación opcional de JavaScript a binarios NW.js, empaquetado Halva y cifrado opcional, caché configurable, y compilaciones de prueba para desarrolladores. No documenta una interfaz universal para instalar plugins externos sobre cualquier distribución comercial. Investigar formatos accesibles, localización soportada o exportaciones de desarrollo autorizadas; no asumir que todos los archivos .halva estén cifrados, ni modificar los paquetes o la caché temporal del juego a ciegas.

## Criterios de aceptación de la futura integración

- Seleccionar el EXE desde RPG, sin exigir título de juego o reglas por título.
- Reemplazar el inglés/japonés por español dentro del mismo cuadro nativo al aparecer, sin OCR ni panel externo.
- Conservar el flujo, los iconos, variables, opciones, paginación, memoria de traducciones y F10.
- Mantener el lanzador normal, partidas y datos originales; instalación reversible y verificada.
- Probar juegos MV/MZ sintéticos, una exportación Cook Tool autorizada y una configuración Halva representativa.
- No publicar compatibilidad nativa Halva hasta probarla de verdad.

Fuentes oficiales: https://dragonhousehelpcenter.azurewebsites.net/manuals/rmcooktooldx/config y https://dragonhousehelpcenter.azurewebsites.net/manuals/rmcooktooldx/devguide .
