# R23-P2 — Modo visual experimental (Halva / Halva2)

Base: R23-P1 34a276350492888d57be832bb7e3fae96f3dfe56. El JS nativo mantiene su lógica y cambia BUILD_ID. La selección gráfica de Halva abre un modo visual local con OCR de Windows y los mismos modelos OPUS EN/JA→ES. La vía nativa sigue siendo preferida cuando está disponible.

Uso: abrir juego normalmente, seleccionar EXE en RPG, pulsar Abrir traductor visual, enfocar el juego durante la cuenta atrás, dibujar región de diálogo o menú y volver al juego. F10 alterna captura mientras el juego seleccionado tiene foco; no consume la tecla. El panel externo conserva texto original y traducción, ajusta líneas y permite desplazamiento. No es traducción nativa.

Requisitos: Windows 10/11 con OCR del idioma instalado y ventana visible, zona no cubierta por el panel. Los fotogramas se leen sólo tras selección explícita y con HWND/PID en primer plano. PNG temporal eliminado al terminar cada llamada; no hay envío a internet. La memoria SQLite se conserva en perfil local derivado de la ruta, no del título. Motor en subcarpetas versionadas fuera del juego. No se escriben paquetes, lanzador, código ni partidas.

Pruebas: Go cubre separación de rutas y versiones. Python cubre longitud, menús, errores, coordenadas y persistencia. CI real ejecuta OCR sobre imagen sintética si el idioma está instalado y OPUS real; distingue una prueba sin el idioma de OCR real. Requiere validación con ventana real, latencia y tipografías. Los RAR adjuntos no se pudieron abrir; no se incluyen archivos de terceros.

Fuentes:
- https://dragonhousehelpcenter.azurewebsites.net/manuals/rmcooktooldx/config
- https://dragonhousehelpcenter.azurewebsites.net/manuals/rmcooktooldx/devguide
- https://docs.lunatranslator.org/en/ocrparam.html
- https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine
- https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html
