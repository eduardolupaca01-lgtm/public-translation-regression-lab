# Servidor · Ren'Py R1 (programa independiente)
Nuevo desde cero. Primera posición del menú. Solo comparte con RPG y WEB la ventana de navegación y el motor de inferencia OPUS local ya incorporado; no importa adaptadores históricos.
 
## Alcance inicial
Windows, copia del juego cerrada, detección de estructura `game/`, `renpy/`, `lib/`; inventario de scripts y archivos RPA. Se instala un complemento propio en `game/ia_servidor_renpy/` y un sidecar independiente. No se descomprimen ni reescriben archivos originales. Recuperar mueve el complemento propio fuera de game/ y conserva la memoria. Se deben investigar instalaciones con rutas alternativas, Python 2.7/3, filtros y clases antiguas, traducciones ya existentes, múltiples archivos y pantallas personalizadas. Una detección no equivale a una certificación de versión.

## Evidencia y criterios
Documentación oficial: https://www.renpy.org/doc/html/translation.html ; https://www.renpy.org/doc/html/text.html ; https://www.renpy.org/doc/html/python.html ; https://www.renpy.org/doc/html/config.html
Los informes históricos son referencia de casos, no código reutilizado ni prueba de este programa. Las pruebas unitarias nuevas usan textos y un traductor determinista de laboratorio. No son inferencia OPUS real.
 
## Puertas de aceptación pendientes
- SDK oficial de 6.99, 7.8.7, 8.3.7 y versiones actuales, con checksum del editor; ejecución nativa, no solo detección.
- Diálogos, narración, comillas internas y finales, menús, elecciones, notificaciones, texto dinámico; preservar variables, etiquetas, formato, rutas y controles.
- Comprobar nombres introducidos por usuario, escenas, guardado/carga/rollback, restauración, cierres inesperados y aislamiento frente a RPG/WEB.
- Medir cobertura real y latencia (inventario, traducidos, caché, rechazados); evitar afirmar 100% en juegos desconocidos.
- Compilar y comprobar paquete completo con OPUS real antes de distribuir un EXE. No publicar pesos o archivos privados.
