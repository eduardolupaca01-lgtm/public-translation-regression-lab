# TX765 — pruebas públicas de correcciones en Tenshixgame RPG

Esta rama usa los **runners públicos de Windows y Linux** porque GitHub no estaba asignando servidores a los trabajos del repositorio privado.

Los controles comprueban casos que reproducen los errores enviados en las capturas: la carpeta del puente de traducción puede llamarse `TenshigameTraduccion` o `TenshigameTranduccion`; si la traducción correcta está en caché debe reemplazar el japonés **en el primer dibujo**, incluso cuando el juego usa un Bitmap personalizado, sin superponer los idiomas. Si la traducción aún no está lista o existe una ventana independiente con el nombre del personaje, el programa debe evitar un repintado inseguro.

También se cuentan los archivos JSON de RPG Maker MV/MZ inspeccionados, leídos, omitidos y los que tienen errores, sin intentar traducir scripts ni modificar archivos de juego. El inventario es intencionadamente limitado a tipos conocidos de datos de RPG Maker.

**Alcance preciso de la prueba:** el código JS en esta rama es una reproducción pública independiente de los mecanismos de protección; **no contiene el plugin original privado, los 21 componentes del motor V95, modelos neuronales ni datos de partidas**. Por tanto, el resultado público valida estas reglas de comportamiento en Windows/Linux, pero NO demuestra por sí mismo que el ejecutable privado ya traduzca diálogos en un juego real.

La reparación específica de la aplicación original quedó en una rama separada y protegida:
[TX765, cambios del programa existente](https://github.com/eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build/tree/fix/tx765-rpg-live-bridge-native-paint-20261121).

Hasta que un runner con acceso legítimo al código y al motor original integre esas correcciones en el EXE, la compilación original y la prueba en el juego permanecen pendientes. El token del worker y los recursos privados no deben incluirse en este repositorio público.
