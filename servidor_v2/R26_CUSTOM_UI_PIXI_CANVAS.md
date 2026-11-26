# R26 — Captura de interfaces personalizadas Roundscape/RPG Maker

Base: R25 corregida. El instalador, OPUS, los flujos de mensajes/opciones, la memoria y la compatibilidad MV/MZ/Halva se mantienen.

## Evidencia del juego aportado
- El registro plugins.js contiene complementos activos JsScript115Set, JsScript116Set, JsScript117Set, JsScript120Set y JsScript121Set. IATraductora está al final del registro.
- JsScript117Set declara Word Wrapping=false, Description Wrap=false y Tight Wrap=false. El menú de creación y los paneles de origen usan textos de presentación distintos de los diálogos habituales.
- El código R25 sólo habilitaba el hook Canvas de Bitmap.context para plugins NEV_. Por ello no cubría los renderizadores JsScriptNNNSet de este juego.
- R25 no instalaba hooks en PIXI.Text ni PIXI.BitmapText. Los textos que esos objetos calculan/renderizan fuera de Window_Base y Bitmap.drawText podían quedar fuera de la captura.
- La detección de una sola palabra no incluía roles/orígenes como Farmer, Noble, Templar, Prowess, etc.; frases como “Every legend starts somewhere. Shape yours.” tampoco contenían suficientes señales léxicas previas.

Los archivos js.zip y data.zip adjuntos no se pudieron abrir en el entorno de análisis; por tanto, no se atribuye el texto a un archivo o función concreta del juego sin esa evidencia. La adaptación se basa en el registro de plugins.js y las rutas de renderizado que R25 dejaba fuera.

## R26
- Hook de PIXI.Text y PIXI.BitmapText en updateText. Traduce sólo strings reconocidos en superficies de texto; conserva el texto fuente del objeto y vuelve a pintar el mismo objeto cuando la traducción asíncrona queda lista.
- Para PIXI.Text, une saltos blandos de párrafos largos antes de consultar OPUS, conserva párrafos en blanco y pares cortos título/subtítulo, y usa el ancho original de wordWrapWidth (o una estimación acotada) sólo durante el render traducido. Restaura estilo y texto originales inmediatamente.
- Extiende el hook Canvas de Bitmap.context a llamadas cuyo stack procede de un JsScriptNNNSet activo, sin autorizar plugins desactivados ni otros canvas globales. Acepta inglés y japonés; el resto del juego queda intacto.
- Añade vocabulario específico de interfaces RPG y frases de creación de personaje.
- Escanea parámetros de plugins activos como datos JSON, nunca evalúa código, omite claves de script/código y limita profundidad, nodos y tamaño.
- F10 muestra contadores PIXI, Canvas y parámetros.

## Regresiones
La nueva prueba sintética cubre PIXI.Text/BitmapText, descripciones inglesas preenvolvidas, reflujo temporal, restauración del texto/estilo original, etiqueta de una palabra, japonés, nombre propio, texto ya español, plugin Canvas activo/inactivo y parámetros JSON sin ejecutar código. Se conserva la batería previa R3–R25 y la prueba real OPUS de CI.

No se afirma todavía compatibilidad verificada en ejecución con el archivo JS original del juego, porque el ZIP de JavaScript no se pudo extraer en el entorno. La validación final requiere que CI pase y que el juego real muestre las pantallas traducidas.
