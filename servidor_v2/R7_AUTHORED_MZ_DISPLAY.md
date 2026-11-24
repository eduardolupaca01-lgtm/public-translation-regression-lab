# R7 — campos de presentación MZ mediante eventos y TextPicture

Base R6: 6d93a2b8. Se conserva el motor OPUS, la caché y el instalador.

Diagnóstico privado del usuario, sólo cifras agregadas: 218 mapas, 700 eventos comunes, 37 plugins activos, 640 comandos TextPicture/set (500 valores distintos), 28.392 asignaciones literales a la variable de entrada de mensajes. 1.154 registros JSONL y 711 SQLite. Las seis muestras reportadas no estaban en la memoria.

- TextPicture: inventario únicamente de args.text del comando set. El sprite original recibe una proyección temporal para que su propia rutina de tamaño y bitmap haga el reemplazo. No se añaden sprites, no se modifica la duración del video, no se reviven imágenes expiradas. Las peticiones tardías sólo afectan a la imagen aún vigente.
- Perfil de diálogo de variables: exige nombres de variables y el bloque de separación explícito que demuestra el flujo desde texto codificado a la variable de presentación. Extrae únicamente asignaciones literales de una línea mediante JSON.parse; no evalúa scripts ni modifica variables. Protege los códigos de animación y el token del actor. Las referencias dinámicas se proyectan sólo durante startMessage y se integran con la espera acotada de R6.
- Las pruebas usan contenido sintético propio; no se incorpora código, diálogos ni archivos originales del usuario al repositorio público.
- Referencia del contrato nativo: https://rpgmakerofficial.com/product/mz/plugin/make/koushiki.html
- Límites: no se traducen expresiones arbitrarias de JavaScript, imágenes/vídeos con texto incrustado o rutas sin contrato demostrado; la compatibilidad de plugins comerciales y el ajuste visual deben verificarse en el juego real.
