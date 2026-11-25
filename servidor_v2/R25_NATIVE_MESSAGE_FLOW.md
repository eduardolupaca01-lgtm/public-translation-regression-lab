# R25 — Flujo de diálogo y cobertura de etiquetas RPG

Base R24: 0e64f369cc226a94f1c71b27726336a1abbebc3d. El mismo núcleo OPUS, instalación MV/MZ/CTE/Halva y formatos de caché se conservan. La captura aportada muestra diálogo español junto al borde y la etiqueta Travel en inglés. Los RAR adjuntos no pudieron leerse por errores del entorno; no se identifica el motor o complemento exacto de este juego ni se afirma haber auditado su caché.

## Cambios
- Extiende la corrección nativa MV al estado de texto con búfer de MZ. Calcula el avance del búfer, ancho de palabra/glifo, iconos, origen de línea, margen de contorno y límites reales del contenido. Inserta únicamente saltos de visualización; la rutina nativa gestiona las páginas y pausas.
- Protege la medición del texto de mensaje de la segunda traducción. No recorta, reduce, modifica registros ni cambia la memoria para insertar saltos.
- Respeta la exclusión previa de alineaciones especiales/RTL; no promete adaptar un renderizador personalizado que no utilice Window_Message. Mantiene intacta la ruta específica CTE.
- Amplía el reconocimiento de campos tipados de MZ con idioma inglés declarado, sin sustituir adaptadores de localización externa. Unifica detección de mensajes, inventario y primera presentación. Añade equivalencias de interfaz como Travel, Fast Travel y World Map. Conserva nombres y controles.
- F10 muestra el contador de saltos MV/MZ. No OCR ni ventanas adicionales.

## Validación
Prueba sintética MZ de dibujo lento y rápido, búfer, margen, páginas, iconos, pausa, conservación carácter a carácter, rótulo Travel y exclusión de nombres/código/localización española. Se mantiene la prueba MV R22 y la de DTextPicture R24. El lanzador y los demás adaptadores no se modifican, excepto el identificador del ejecutable.

Fuentes: https://github.com/swquinn/rmmv-docs/blob/master/docs/Window_Base.md ; https://github.com/tonbijp/RPGMakerMZ/blob/master/Reference/MV.TextState.md ; https://github.com/tonbijp/RPGMakerMZ/blob/master/Reference/Window_Base.md ; https://www.yanfly.moe/wiki/Message_Core_(YEP) .

## Corrección de regresión R8 / idioma mixto
La ejecución Linux de R25 (45723258545, job 139586583684) confirmó que el nuevo flujo MZ pasó, pero una elección ya española se trató como inglesa y se mostró otra frase. La detección nativa protege español inequívoco, exige indicios positivos para el fallback MZ y no utiliza el locale como única evidencia. Los catálogos que declaran explícitamente la fuente mantienen su contrato. Se revalida la memoria anterior sin borrar el diario ni modificar su esquema. R8 reproduce también una entrada antigua equivocada y verifica que no llegue al modelo ni cambie las opciones. No se alteran el flujo de líneas, OPUS o las pruebas previas.
