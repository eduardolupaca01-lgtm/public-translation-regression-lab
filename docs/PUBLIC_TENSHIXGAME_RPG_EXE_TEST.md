# Tenshixgame RPG — EXE público de prueba para Windows de 64 bits

**Alcance:** nueva herramienta **experimental** construida desde fuentes públicas y motores abiertos; NO es el ejecutable original del producto anterior y no incorpora sus archivos ni modelos. No actualiza automáticamente ninguna instalación ni traduce el texto de un juego en ejecución.

## Cómo comprobar que traduce

Descarga el artifact de la ejecución **Public Tenshixgame RPG Windows EXE with authentic JA-ES model test** en GitHub Actions, descomprime el ZIP, y ejecuta **Tenshixgame-RPG-Prueba.exe** en Windows 64 bits.

1. Escribe en la caja superior `ありがとうございます。` o alguna otra frase japonesa original.
2. Pulsa **Traducir japonés** y revisa la traducción española abajo.
3. En el primer uso requiere Internet: descarga desde el catálogo oficial modelos públicos Argos Translate **japonés → inglés → español**. Los guarda fuera del EXE, en el directorio local del usuario. Después puede funcionar sin Internet.
4. La inferencia es neuronal real; las salidas no están codificadas ni simuladas. El resultado puede contener errores semánticos: debes revisarlo personalmente.

## Exportación opcional de diálogos RPG Maker MV/MZ

Si posees un RPG Maker MV/MZ que tengas permiso para modificar, elige su carpeta con **Elegir juego MV/MZ** y selecciona una carpeta de destino externa mediante **Exportar diálogos a una COPIA**.

La herramienta busca archivos `Map*.json`, `CommonEvents.json` y `Troops.json` en `www/data` o `data`. Procesa texto de evento 401, texto desplazable 405, opciones 102 y ramas de opción 402. Únicamente escribe los JSON traducidos en una **carpeta nueva** llamada `Tenshixgame-RPG-ES419-prueba` fuera de la instalación original, junto con un informe. No modifica partidas, scripts, la carpeta del juego ni otros datos.

**Límites importantes:** no reemplaza diálogos en pantalla mientras juegas; no traduce imágenes, recursos binarios, bases de datos de objetos, nombres de actores ni código JavaScript. No es un instalador de plugins para el juego. Está diseñado solo para MV/MZ con archivos JSON compatibles. La aplicación no se comunica con procesos de juegos.

## Verificación de Windows

El workflow `.github/workflows/public-tenshixgame-rpg-trial-win64.yml` ejecuta antes todas las pruebas públicas, instala `argostranslate==1.11.0` y PyInstaller, genera un EXE sin modelos y lo **ejecuta en el runner de Windows**. Solo si el EXE descarga modelos públicos reales y supera los controles de traducción JA→ES, persistencia SQLite y un ejemplo de eventos RPG Maker, el artifact de Windows se entrega. Los errores aparecen en la ejecución y no se declara aprobación artificial.

La compilación es una prueba de ingeniería, no certificación lingüística ni aprobación profesional. Los modelos se descargan en el equipo del usuario conforme a sus licencias; ningún peso, fuente, partida ni archivo privado se incorpora al repositorio público. El ZIP del artifact contiene la suma SHA256 del EXE.

Proyecto y biblioteca pública: https://pypi.org/project/argostranslate/ y https://argos-translate.readthedocs.io/en/latest/ .
