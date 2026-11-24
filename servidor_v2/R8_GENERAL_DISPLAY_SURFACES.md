# R8 — cobertura general de superficies de texto MV/MZ

Base: R7 (2735961ae04d27c11935dfb894c390edde93f770).

## Hallazgos reproducibles en los datos de prueba

- El idioma del juego es `en_US`.
- Las opciones se almacenan como comandos de elección, separados de sus ramas por índice.
- Hay controles de presentación como `\\pop[-1]` y `\\b[2]` que no son texto traducible.
- Las etiquetas `<If ... Capped>` aparecen literalmente en las opciones visibles; sus delimitadores deben conservarse mientras se traduce el contenido.
- Los perfiles de actores incluyen variables `\\N[n]` y saltos de línea; algunos plugins expanden el nombre antes de dibujar el texto.
- Hay ventanas y complementos que dibujan directamente con `Bitmap.drawText`, sin pasar por el ciclo normal de mensajes.

## Cambios R8

1. Clasificación conservadora de etiquetas de interfaz de una palabra en superficies confirmadas, sin inferir nombres propios como inglés.
2. Señales de inglés adicionales para etiquetas de menú y frases cortas como fechas y ubicaciones; se permiten símbolos decorativos comunes (por ejemplo, corazones) sin perderlos del texto original.
3. Los delimitadores de etiquetas visibles `<If ... Capped>` se protegen por separado; su contenido queda disponible para traducción.
4. Plantillas de nombre se registran desde cualquier texto preprocesado, no sólo desde CSV, y admiten perfiles multilínea con `\\N[n]`.
5. El mismo proyector de caché/traducción se usa en `Window_Base`, `Bitmap.drawText`, medición de texto y opciones, tanto en MV como en MZ.
6. Si una ventana propietaria puede refrescarse de forma segura, se solicita un redibujado después de completar la traducción. La cadena original, la lista de opciones, los índices de ramas y los datos del actor no se modifican.

## Seguridad y límites

- No se evalúan scripts ni se traducen nombres de archivos, expresiones de código, variables numéricas ni controles de animación.
- Las opciones se sustituyen sólo durante el dibujo/medición; los valores originales se restauran inmediatamente.
- Los perfiles se proyectan en pantalla; no se reescriben `Actors.json` ni los datos del juego.
- La cobertura general se comparte entre RPG Maker MV y MZ. Otros motores no RPG Maker requieren su propio adaptador de renderizado.
- Las pruebas usan contenido sintético y no incluyen los archivos privados del usuario.
