# TENSHIXGAME — reconstrucción Windows y traducción original V95

**Estado verificado a 22-11-2026.** Este repositorio contiene **dos entregables distintos** y no deben confundirse ni instalarse simultáneamente como si fueran el mismo programa.

## 1. Detector R1 (nuevo, solo lectura)

`tenshixgame-next/` tiene una interfaz Win32 y CLI de catálogo de **17 familias** de motores. Identifica la familia, submotor y, cuando las firmas permiten comprobarla, la versión del juego seleccionado. RPG Maker se distingue entre 2000/2003, XP, VX, VX Ace, MV y MZ. La familia no demuestra compatibilidad del traductor: **el detector NO instala IA, NO ejecuta el juego y NO traduce**.

También inspecciona una instalación portátil propia de la generación TX771–TX775 sin modificar archivos: marcador propietario, SHA-256 del trabajador, presencia de complemento, manifiesto, caché por entrada, controles de nombre, parámetros RPG, cifras visibles, carpetas temporales e instalaciones App previas. El resultado no confirma que una escena haya mostrado español ni que todos los modelos estén completos.

Compilación y pruebas: [Windows/Linux para detector y QA](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/workflows/rebuild-tenshixgame-detection.yml). Descargar el artifact `TENSHIXGAME-NEXT-Deteccion-EXE-PRUEBA`; es un diagnóstico, **no el EXE traductor**.

CLI: `TENSHIXGAME-Detector-CLI.exe -catalogo` o `TENSHIXGAME-Detector-CLI.exe -familia rpg-maker -juego "D:\Juegos\Copia\Game.exe"`.

## 2. Traductor original V95 TX775 (RPG Maker MV/MZ, prueba protegida)

Se preservó la línea auténtica de Eduardo (Argos/OPUS local, sin proveedores externos) y se aplicó el arreglo TX775 para no rechazar diálogos españoles cuando un NPC conserva su nombre japonés protegido. Se conserva el código de control RPG, el texto original del evento, la caché durable y la instalación portátil. La fuente fue reconstruida **solo dentro de Windows CI** desde un commit privado fijado por SHA y sin cambiar su repositorio original.

**Compilación aprobada:** [GitHub Actions #45044374825](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/45044374825). Superó 26 controles originales de V95, pruebas JS de primer pintado y caché, validación del puente empaquetado, instalación y traslado de una copia sintética, y cifrado de la entrega.

Artifact: `Eduardo-TENSHIXGAME-TX775-V95-NOMBRES-PORTABLE-Windows-ENCRYPTED` (caduca el **6 de diciembre de 2026**). Dentro está el archivo protegido `Tenshixgame-RPG-TX775-NOMBRES-V95-PRUEBA.7z`; **SHA-256 del .7z cifrado**: `0f6143f0c90cfcf28d13a2557c74cd96389bd579b600cd66075f73000bcee12f`. Se necesita la contraseña del propietario ya configurada; no se publica ni se almacena en este repositorio.

**Importante:** el resultado aprobado es un **candidato de prueba para RPG Maker MV/MZ**, no una afirmación de que cada videojuego compatible muestre todos sus textos en español. Se necesita una aceptación visual dentro de una copia real del juego, preferentemente sin conexión, con nombres, opciones, variables, menús, segundo arranque y cierre de procesos.

**Actualización real TX772 → TX775 aprobada:** [Windows CI #45046277149](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/45046277149). Descifró ambos EXE originales solo en Windows desechable, comprobó sus recibos SHA, conservó caché y paquetes App anteriores, no modificó Game.exe ni plugins.js, y verificó reinicio, traslado de carpeta y ausencia de motor global en el perfil. Solo se publicó un pequeño recibo de PASS sin modelos. No es una prueba visual en el juego real.

## Diagnóstico nuevo TX776 (instalador original de Windows)

El área de **Estado de instalación** conserva los eventos anteriores en vez de reemplazarlos. El botón **COPIAR DIAGNÓSTICO PARA ENVIAR** recoge códigos, etapa y recomendaciones sin enviar nada por Internet ni copiar rutas personales, contraseñas ni textos privados del juego. Hay pruebas Go de Windows para la acumulación y seguridad del informe.

El overlay de instalación se aplica **únicamente** a la copia temporal del código V95 auténtico fijado por SHA, mediante el orquestador protegido. Este código R1 del detector NO se convierte en instalador por sí mismo. Antes de recomendar el EXE TX776, debe aprobar la compilación neuronal cifrada completa. El panel no cubre el arranque inicial del EXE único anterior a abrir la GUI.

[Cómo copiar el diagnóstico después de instalar](docs/TX776_COMO_COPIAR_DIAGNOSTICO_INSTALACION.md) · [Rompecabezas y pendientes de las 11 cuentas](docs/TX776_ROMPECABEZAS_11_CUENTAS_DIAGNOSTICO_Y_GATES.md).

## 3. Cómo probar sin poner en riesgo el juego

1. Conservar la carpeta original y sus partidas. Trabajar únicamente sobre una copia con el juego cerrado y el antiguo complemento no ejecutándose.
2. Descargar el artifact cifrado TX775 desde la ejecución enlazada y verificar el SHA-256 del `.7z` antes de extraerlo con la contraseña del titular.
3. Usar el EXE TX775 para seleccionar el `Game.exe` de la copia y realizar la opción propia de **instalar/actualizar traducción**. No manipular `plugins.js` ni cambiar los marcadores SHA a mano.
4. Cerrar el instalador, iniciar el `Game.exe` de esa misma copia y comprobar diálogo, nombre NPC, decisiones y F10. Reiniciar el juego y volver a observar el mismo diálogo para verificar reutilización del caché.
5. Para comprobar portabilidad, cerrar el juego y todos los trabajadores, trasladar **la carpeta completa** a otro disco/Windows sin reinstalar y volver a iniciar. Si el instalador indica archivo desconocido o cambiado, no borrar ni forzar una reparación.

## 4. Datos históricos recuperados y límites

En la SQLite histórica suministrada (6.664 segmentos), 6.646 estaban marcados `done` y 18 `retry`. Entre los completos, 3.874 conservaban japonés exclusivamente dentro del nombre protegido, 9 tenían japonés restante visible y 152 tenían diferencias de dígitos visibles; la unión de esos dos últimos tipos son 161 registros. **Estas cifras NO equivalen a 161 errores visuales observados ni a calidad certificada de los demás registros.** El validador R1 comprueba nombres y códigos intactos, y cifras visibles equivalentes, sin desactivar los filtros.

Informe reproducible con huella de la fuente: [auditoría TX775 de SQLite y códigos](docs/TX775_AUDITORIA_SQLITE_NUMEROS_Y_NOMBRES_20261122.md). Comparación de TX203 a TX772: [recuperación R1](docs/R1_RECUPERACION_V95_CACHE_Y_PORTABILIDAD.md). Estudio de las fuentes históricas: [11 cuentas](docs/RECUPERACION_11_CUENTAS.md).

## 5. Entorno de desarrollo

Go 1.22+; ejecutar `go test ./... -count=1` y `go vet ./...` desde `tenshixgame-next`. La CI compila GUI Win32 y CLI y prueba Windows/Linux. Los pesos originales, juegos, bases privadas y EXE descifrados nunca se agregan al repositorio público. El PR de integración permanece en borrador hasta aprobar las pruebas finales.
