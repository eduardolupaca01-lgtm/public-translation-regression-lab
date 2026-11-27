# R31 — auditoría de advertencias de compilación

Referencia verde preservada: commit e200dc4a8d6298132c4743222b31ff622573fc3d.
Integración 45924791479 (Ubuntu/Windows) y compilación OPUS 45924791429 aprobadas.
Artefacto cifrado 15166057518, publicado y verificado. El registro confirma los dos procesos onefile cerrados, caché liberada, restauración de archivos sueltos y empaquetados, limpieza estricta, MV/MZ/CTE/Halva y cifrado.

## Advertencias observadas

- GitHub Actions: Node.js 20 obsoleto; las acciones antiguas se ejecutaban forzosamente con Node.js 24. Migración conservadora de checkout a v5, setup-go/python/node a v6 y upload-artifact a v6, todos con runtime Node.js 24. El Node.js 22 de pruebas, Go 1.23.2, Python 3.11 y Ruby 3.2 no se cambian. Las advertencias DEP0040 (punycode) y DEP0169 (url.parse) estaban en las herramientas de automatización, no en el motor de traducción. Su desaparición se confirma con registros nuevos, no se oculta.
- Go: setup-go buscaba go.sum en la raíz. Ahora usa servidor_v2/go.sum. No cambia el código ni las dependencias de Go. No se necesita caché de npm para las pruebas Node directas.
- Rust: unused_mut en read_bounded, línea 93. Se elimina exclusivamente el modificador innecesario; file.take sigue leyendo el mismo máximo.
- PyInstaller: mensaje INFO que indica que existe warn-IATraductora.txt. El contenido de ese archivo no quedó en los artefactos del build aprobado. No se puede clasificar retrospectivamente cada importación. La nueva auditoría registra identificadores de módulos, importadores, categorías y entradas no reconocidas sin volcar rutas. No se cambia la versión de PyInstaller ni sus parámetros. La verificación real del EXE y de los dos idiomas OPUS continúa siendo obligatoria.

Fuentes de mantenimiento: notas oficiales de actions/checkout v5, setup-go v6, setup-python v6, setup-node v6 y upload-artifact v6. Se actualizan solamente los dos workflows R31. No se modifica la rama R30 ni se fusiona la PR. El candidato aprobado anterior conserva sus pruebas y artefacto. La nueva ejecución comprobará las advertencias restantes; no se afirma compatibilidad con un juego RGSS3 real únicamente por aprobar recursos sintéticos.
