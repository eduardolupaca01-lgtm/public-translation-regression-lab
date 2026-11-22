# TENSHIXGAME TX200 — Contrato de juego autocontenido y trasladable

**Auditoría técnica · 22 de noviembre de 2026.** Trabajo en rama pública aislada de Eduardo. Fuentes históricas consultadas en solo lectura; no se han publicado juegos, textos privados ni modelos de IA. No equivale a una prueba real de partida.

## Requisito del propietario: no confundir dos clases de portabilidad

A. El instalador puede ser un EXE que se abre sin instalarse en Windows.
B. La copia del JUEGO ya traducido debe funcionar sin ese instalador, incluso al copiarla a otra computadora Windows compatible, conservar todos los modelos y todas las traducciones dentro del propio juego, sin un programa de IA instalado aparte, ni API ni Internet.

**Es B lo que hay que demostrar.** El jugador debe abrir directamente Game.exe en una copia del juego. Una frase traducida previamente debe salir de la caché local; una frase nueva debe llegar al modelo local del mismo juego. El proceso de traducción debe terminar cuando termina el juego. No se deben reescribir guardados ni romper elecciones o eventos.

## Estructura actual de MV/MZ con motor local original

    Juego/
      Game.exe
      www/js/plugins.js
      www/js/plugins/TenshixgameRPGLive.js
      Tenshixgame-IA/
        portable-owner-v1.json
        App/<paquete_verificado>/
        .local/TENSHIXGAME-RPG/
          engine/engine/TenshixgameAI.exe
          engine/engine/bundle_manifest.json
          engine/engine/models/
          live-cache/

Esta estructura describe únicamente la rama actual de RPG Maker MV/MZ. Los otros motores del catálogo requieren sus propios adaptadores y pruebas; no se deduce que 17 familias funcionen porque haya 17 tarjetas en pantalla.

## Evidencia nueva del RAR dividido TX203 enviado por el propietario

- RAR5 multivolumen: 42 archivos, 847.555.437 bytes descomprimidos.
- Worker local TenshixgameAI.exe: 237.780.444 bytes. Contiene modelos OPUS y Argos locales para traducciones JP/EN a español.
- Los archivos pequeños relevantes fueron contrastados contra sus entradas RAR por tamaño y CRC-32.
- La base embedded-v88-pending.sqlite3 conserva 6.664 segmentos: 6.646 completados y 18 en retry. El contador embedded-v91-frontend-status.json registra únicamente 8 coincidencias visuales. No dividir estos dos números como si midieran el mismo evento.
- El manifiesto antiguo install-manifest-v84.json lleva una ruta de Windows absoluta game_root. El bridge antiguo conserva un PID, puerto y token efímeros y hay archivo lock. No se puede considerar trasladable reutilizar ese estado en otro PC sin regenerar sus identificadores.
- El RAR incluye plugins.js.original.v84, que es una copia previa, no el JS de producción actualmente instalado dentro del juego; por tanto no certifica qué plugin se ejecuta en la sesión actual.

## Manual público de Ultra Translator y cómo usarlo como referencia

- Manual público del autor: https://github.com/robinpierr/Ultra-Renpy-Translator-Public
- Sitio oficial: https://www.ultra-translator.com/
- Integración pública RPG Maker: https://github.com/robinpierr/Ultra-Renpy-Translator-Public/blob/main/dist/lib/modular/data/rpgmaker_overlay.js

El EXE principal de Ultra no requiere instalador tradicional. Su integración en RPG Maker carga un diccionario dentro del juego (data/UltraTranslations.json), consulta claves exactas/normalizadas y sustituye texto usando puntos de dibujo y mensajes. Su módulo integrado busca evitar la superposición de cajas adicionales. Esa es la arquitectura a estudiar, no una garantía de compatibilidad de todos los juegos.

Google/Bing requieren Internet y la opción IA local de Ultra puede necesitar Ollama o LM Studio en el equipo de destino. **No satisface por sí sola** el requisito de motor, modelos y traducciones 100 % dentro del juego. No copiar código de terceros sin revisar licencia/autorización; implementar de forma independiente la arquitectura útil.

La normalización agresiva de códigos de escape y un hook global de Bitmap.drawText podrían alterar variables, colores, nombres o lógica del juego. Evitar copiar esos interceptores indiscriminadamente: aislar los diálogos reales, opciones y etiquetas de interfaz, preservando comandos y estado.

## Fuentes de todas las líneas de trabajo relevantes

- Historial TX203 y 13 grupos QA con un mismo EXE en escenas propias: https://github.com/drimt902-netizen/tenshixgame-tx200/blob/ad77dccc763424428003377a53848ed311bd1e21/docs/TX203_ENTREGA_VERIFICADA_20261110.md
- Matriz original de 17 familias, con pruebas limitadas y variantes bloqueadas: https://github.com/drimt902-netizen/tenshixgame-tx200/blob/ad77dccc763424428003377a53848ed311bd1e21/docs/TENSHIXGAME_TX200_MATRIZ_17_FAMILIAS_20261107.md
- Recuperación de 486 archivos fuente y hashes, Camacho: https://github.com/camachogomez791-byte/tenshixgame-tx20026/blob/main/audit/source-lock.json
- Experimento de Panda sobre diálogo original, propietarios de ventana, opciones y control: https://github.com/pandascanlation-art/tenshixgame-tx/blob/bbbd2c306539a3afde8f8f97da168f116137a864/docs/TX710_REINICIO_TX203_CONTINUIDAD_Y_GATES.md
- Auditoría pública anterior de TX769 frente a TX203 y Ultra: https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/blob/a7b4788b434237b81912ac8ed7d88bfb358ccfd9/docs/TX769_AUDITORIA_TX203_RC_ULTRA_RENPY_Y_RPG.md
- TX772 build público aprobado: https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/45034400292
- TX772 prueba de actualización TX771->TX772 en juego sintético: https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/45035130728

Las pruebas TX203 y TX772 utilizan fixtures y motores en Windows CI. **No** confirman el juego comercial del propietario, ni prueban que tras copiarlo a otro PC limpio todo se traduzca como esperaba. TX772 mejora almacenamiento local y copia de carpeta, pero no certifica lectura visual completa ni segundo equipo.

## Errores principales que deben cerrar los siguientes cambios

1. Identidad idéntica de la frase entre el escáner, la caché SQLite, el adaptador y el texto final pintado; preservar códigos de control. No confundir recibido con mostrado.
2. Traducción en la misma ventana nativa del videojuego; no poner texto español encima del japonés. Resolver primer dibujo y traducción tardía sin reiniciar eventos, nombre, decisiones ni alterar índices de selección.
3. Garantizar que modelos, ejecutable del trabajador, caché, JSON, SQLite, logs persistentes y todos los temporales del motor estén dentro del juego. Las rutas del perfil de Windows pueden usarse solo para cosas ajenas a la instalación persistente y nunca como dependencia del juego.
4. La instalación original y actualización deben registrar SHA y permitir restaurar solo sus propios archivos. Regenerar PID, puerto, token y locks; jamás transportar procesos antiguos en actividad.
5. Probar que ejecutar Game.exe directamente, SIN abrir TENSHIXGAME, hace que el juego encuentre su IA y su traducción guardada.
6. Probar cierre completo del trabajador y que Windows permita mover o borrar una COPIA de prueba del juego inmediatamente después del cierre.
7. Probar traslado real a otra computadora Windows limpia, sin conexión y sin herramientas externas. Repetir diálogos, opciones y F10, confirmando caché persistente y ninguna dependencia del disco C:.

## Nueva herramienta de prueba pública añadida

tools/audit_tx200_game_local.py es auditoría **solo lectura**. Comprueba diseño de carpetas, propietario, SHA del trabajador, los hashes listados en el manifiesto, presencia de caché y plugin. Su --self-test crea carpetas sintéticas, las copia, acepta su reubicación y rechaza worker modificado o marcador ajeno. Se ejecuta en Windows y Linux mediante .github/workflows/tx200-game-local-contract.yml.

El resultado de esa prueba se etiqueta STRUCTURAL_ONLY: **NO** demuestra que se haya ejecutado un Game.exe real en otra PC, ni la calidad visual de una traducción. Este programa de control tampoco se distribuye a jugadores, quienes no deben instalar Python.

## Decisión de desarrollo

Mantener el motor local y manifiestos verificados de TX772, recuperar el catálogo visual de TX200 y los buenos puntos de sustitución nativa de TX203. Tomar de Ultra la idea de precalcular + cargar diccionario dentro del juego + cubrir texto dinámico, pero con motor V95 propio dentro de la carpeta. Las 17 tarjetas no deben marcarse como soportadas antes de certificación por motor y versión. No entregar otro EXE como "todos los problemas resueltos" hasta superar la prueba real en copia de juego y después en segundo Windows limpio.
