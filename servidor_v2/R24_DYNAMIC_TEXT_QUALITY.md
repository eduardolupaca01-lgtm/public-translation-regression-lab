# R24 — Proyección de textos dinámicos antes del render

Base: R23-P4 corregida (465dd181). La ruta Halva, los modelos OPUS, el código de instalación/reversión y las regresiones anteriores se conservan.

## Evidencia y alcance
Las capturas del usuario muestran rótulos japoneses y texto español concatenado/incoherente en una interfaz personalizada. Los archivos RAR no pudieron leerse en el entorno de ejecución; no se identifica todavía qué plugin usa el juego concreto ni se afirma que se haya auditado su caché. El código público de RPG Maker MV y DTextPicture confirma que existen renderizadores por glifo y que traducir a nivel de Bitmap durante la pintura rompe el cálculo de anchuras. El arreglo es general para ese contrato, no dependiente de un título.

## Cambios
- Proteger la medición y el dibujo de glifos de MV y drawTextEx. No inferir una traducción desde un carácter japonés aislado de un bitmap sin contexto.
- Si DTextPicture está activo y su contrato está presente, proyectar el texto completo antes de calcular el tamaño y dibujar. Usar la rutina original. No modificar Game_Picture, sus variables, controles ni datos guardados. Revalidar la identidad del objeto para un redibujado tardío; no hacerlo si el plugin publica dimensiones en variables. Mantener formato vertical o comandos desconocidos sin alterar.
- Separar contadores con límites explícitos (etiqueta, separador, cifra, unidad). Conservar el valor numérico y su representación; usar unidades españolas. Incorporar equivalencias exactas de interfaz neutra.
- Rechazar cadenas japonesas breves cuyo resultado concatena múltiples fragmentos oracionales sin separación. Aplicar tanto a nuevas inferencias como al uso de memoria SQLite/JSONL; no borrar la memoria ni cambiar su esquema.
- F10 informa si DTextPicture está detectado y de sus renderizados. No OCR ni ventana nueva.
- Las imágenes con letras incorporadas no quedan traducidas por esta ruta de texto. Requieren identificar los recursos de interfaz/localización autorizados, no modificar archivos arbitrarios.

Pruebas nuevas: DTextPicture MV y MZ simulados, medición/dibujo, contador, controles, revalidación de caché. No equivalen a validar el juego real.

Referencias: https://github.com/triacontane/RPGMakerMV/blob/master/DTextPicture.js ; https://github.com/triacontane/RPGMakerMV/blob/mz_master/DTextPicture.js ; https://github.com/swquinn/rmmv-docs/blob/master/docs/Window_Base.md ; https://rpgmakerofficial.com/product/MZ_help-en/01_11_01.html .
