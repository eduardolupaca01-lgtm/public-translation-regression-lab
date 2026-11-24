# Servidor v2 R6 — primera presentación MV/MZ y formulario
Base: R5 (144b3424c7f23b56a40acda3f9a4b3ec423a2861).
- La espera se inserta en updateWait del ciclo nativo, antes del primer dibujo; mensajes y elecciones esperan resultados válidos, no bloquean el event loop. Límite de 30 s; sin conexión, 8 s. Si no hay traducción válida se conserva el original.
- Las elecciones se proyectan únicamente al medir/dibujar, sin alterar índices, símbolos ni callbacks; se mantiene la actualización segura de opciones personalizadas.
- 111_InputForm: aislamiento de eventos de teclado en sus elementos HTML, preserva valor del nombre y Enter. El botón fijo de confirmación se localiza. Se inhibe la traducción visual y el redibujo tardío durante el formulario.
- El archivo original-plugins.js suministrado declara Alpha_ABSZ activo, isUseExtCollisionsSystem:b=true y getExtCollisionShowLayerKey=c. La documentación del complemento describe los colores de la captura. La prueba del juego real aún es necesaria; no se cambian colisiones ni mapas.
- No se cambian OPUS, SQLite/JSONL, modelos, partidas ni datos del videojuego. Mantener el cifrado existente.
- Regresiones añadidas: MV y MZ primera presentación fría, elección sola y nombre/teclado/fallback desconectado. Las pruebas antiguas de llamada directa comprueban la ruta de compatibilidad y redibujo seguro; no sustituyen la prueba del ciclo normal.

La segunda revisión usa la cola deduplicada de solicitudes visibles, prueba claves TSV con memoria fría en MV y MZ, y exige una sola presentación de diálogos y elecciones en la aceptación con los modelos OPUS reales. El caso sin locale verificable conserva el comportamiento previo en lugar de escoger una columna arbitraria.
