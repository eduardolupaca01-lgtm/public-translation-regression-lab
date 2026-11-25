# R23-P1 — Dragonhouse/Halva: diagnóstico y continuidad RPG

Base exacta: R22 `4a47672e3dc073bfa3cd15b66679f43dc601ac99`. Se mantiene el mismo complemento MV/MZ, los modelos OPUS, sus regresiones y las rutas de instalación ya soportadas. En el JS cambia exclusivamente BUILD_ID. El instalador usa el mismo identificador, con regresión de concordancia.

## Estado y evidencia
- Los marcadores de estructura son GameConfig.sbcf y GamePackages, con lanzador Dragonhouse personalizable.
- Cook Tool permite paquetes comprimidos y/o cifrados, código compilado y cachés regenerables. No se presupone que una extensión implique cifrado ni que implique posibilidad de modificar el paquete.
- En esta fase no se han verificado los bytes del juego aportado. No se incluyen archivos del videojuego en el repositorio.
- **No es todavía un adaptador de traducción Halva.** La nueva identificación de solo lectura impide que una estructura empaquetada o mixta se instale como un proyecto suelto. No toca paquetes, cachés, ejecutables ni registros.
- Para una exportación de desarrollo autorizada con recursos MV/MZ accesibles, se conserva el recorrido de instalación original. La aceptación de una distribución Halva debe demostrar una vía de integración permitida por el desarrollador, la persistencia de la memoria fuera de cachés temporales y funcionamiento real del lanzador.

## Diagnóstico reproducible
`Servidor.exe -inspect -game "C:\\juego\\Game.exe"`

La selección gráfica informa del formato y permite copiar el diagnóstico. La salida contiene únicamente conteos acotados de extensiones .halva, .halva2 y otras, con indicador de inventario parcial; no lee ni muestra la configuración confidencial. Cualquier selección nueva inválida invalida también el juego anterior.

## Referencias oficiales
- https://dragonhousehelpcenter.azurewebsites.net/manuals/rmcooktooldx
- https://dragonhousehelpcenter.azurewebsites.net/manuals/rmcooktooldx/config
- https://dragonhousehelpcenter.azurewebsites.net/manuals/rmcooktooldx/devguide

Las pruebas sintéticas comprueban identificación, rechazo sin escrituras, límites del inventario, selección y continuidad. No certifican traducción de paquetes Halva comerciales. No sustituir la entrega funcional de R22 por una promesa de compatibilidad Halva.
