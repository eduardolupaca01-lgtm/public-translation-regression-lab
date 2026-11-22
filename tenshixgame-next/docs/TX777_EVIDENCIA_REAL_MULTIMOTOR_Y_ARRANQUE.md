# TENSHIXGAME TX777 — Revisión cruzada de pruebas multimotor y corrección de arranque

**Fecha:** 22/11/2026. **Scope:** ramas Windows del traductor, no otras aplicaciones; solo se ha escrito en la rama pública de Eduardo. Las cuentas conectadas se consultaron en modo lectura. **Una prueba Windows correcta no equivale a que su adaptador esté ya unido a R1 ni a que todos los juegos comerciales funcionen.**

## 1. Causa reproducible de la bienvenida que aparece en todas las versiones

En la fuente exacta `aeb9ff9326e418fbabe2d53dff7891f4fb340c37`, `reference/tx541-rpg-onefile/tx771_portable_windows.go` define `tx771Welcome()` usando `user32.MessageBoxW` con título `TENSHIXGAME RPG - V95 portátil` y las mismas frases de la captura. Es **arranque del EXE único antes de abrir el instalador**, no el diagnóstico `rpg_dashboard_windows.go` que se amplió en TX776. Las pruebas originales `tx771_startup_windows_test.go` estaban diseñadas explícitamente para demostrar esa bienvenida antes de leer los 650 MB del bundle.

TX777 cambia los hooks por defecto a una **ventana Win32 propia que aparece sin diálogo modal**, muestra selección de Game.exe, progreso del modelo y botón para copiar errores. El paquete auténtico V95 se verifica y prepara igual que antes, dentro de la carpeta del juego. La interfaz interior TX776 toma el Game.exe ya elegido para no solicitarlo dos veces. En el desarrollo se conserva el comportamiento de las pruebas sintéticas antiguas por inyección de funciones y no se modifica la fuente histórica.

**Evidencia pendiente:** la versión TX777 debe pasar su compilación Windows cifrada y los 26 gates; una pantalla de código no es una captura del EXE ya ejecutándose en el PC del propietario. No dar un enlace de TX777 como aprobado hasta que esa ejecución termine con SUCCESS y artifact correcto.

## 2. Evidencia comprobada de los otros motores, que es mayor que «solo lectura»

La fuente anterior no estaba correctamente graduada en la primera matriz R1. Los siguientes identificadores de ejecución fueron consultados de nuevo y reportaron `completed/success` en GitHub Actions.

| Motor, variante | Ejecución verificada | Clase correcta de evidencia | Todavía NO demostrado |
|---|---|---|---|
| RPG Maker 2000/2003 (LCF) | [42602582533](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42602582533) | EXE TX200 real con V95, GUI y LCF binario de prueba, instalar/restaurar bytes exactos | Textos de juego comercial en pantalla |
| RPG Maker MV/MZ | [45049228765](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/45049228765) | Original V95 portátil TX776, 26 gates con diagnóstico, worker y caché; cifrado | Aceptación visual del juego del propietario |
| Godot 4.3 oficial | [42715415876](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42715415876) | **Motor oficial Windows ejecutado**, obtenido con SHA512 de origen. Proyecto propio corre en Godot, V95 GUI traduce EN/JA→ES, F10 y evento de botón, rollback | Todas las versiones/proyectos de terceros y reproducción en otro PC |
| TyranoScript 1.7.4 | [42666252946](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42666252946) | Chromium real renderizó texto ES, opciones, F10 y pausa/reanudación en API Tyrano de muestra | Motor y juego Tyrano completo de terceros |
| Visual Novel Maker 1.7.9 | [42709905707](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42709905707) y [42715423243](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42715423243) | EXE V95 + Chromium real; escenas EN/JA autoelaboradas, F10, eventos y restauración por SHA | Motor completo comercial y todos los paquetes |
| Java 17 / JAR | [42639074168](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42639074168) | **Aplicación JAR ejecutable real** tras GUI + V95 carga Bundle ES, y restaurar devuelve EN | GUI de videojuegos Java reales y JAR firmados |
| Node/i18next | [42647682867](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42647682867) | **Biblioteca i18next 23.0.0 real** consume ES de un catálogo escrito por V95 y revierte | Juegos NW.js comerciales y todas las configuraciones |
| KiriKiri/KAG | [42660338480](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42660338480) | EXE GUI+V95 convierte guiones KAG UTF-16, preserva macros, marca F10, rollback SHA | Motor jugable completo, empaquetados/cifrados |
| Unity Mono/IL2CPP | [42645706956](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42645706956) | GUI+V95 instala componentes en raíces de prueba y los restaura con defensa contra recibos maliciosos | Runtime Unity real y textos renderizados de título |
| Unreal LOCRES v2 | [42646864070](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42646864070) | GUI+V95 transforma LOCRES binario y restaura SHA, bloquea IoStore inseguro | PAK/IoStore y runtime Unreal comercial |
| GameMaker data.win | [42658820993](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42658820993) | GUI+V95 escribe cuatro cadenas JA en STRG de `data.win` sintético, punteros y SHA verificados | Juego ejecutable GameMaker, límites de variantes |
| Light.vn 1.9.7 | [42655275676](https://github.com/drimt902-netizen/tenshixgame-tx200/actions/runs/42655275676) | GUI+V95 instala guiones y recursos F10, protege F10 del autor y rollback por SHA | EXE Light.vn jugable, render o pulsación de F10 en escena |

Las ocho filas originales de TX776 infravaloraban las pruebas del verdadero runtime de Godot y algunas de Java/i18next/VNM. **Se corrigió la matriz machine-readable** `TX776_MATRIZ_MOTORES_17_CONTRATO.json` para conservar el estado histórico y los IDs de CI, sin marcar como `installer_enabled` a ningún motor todavía no importado.

### Clasificación verificable

- **Nivel A, V95 y prueba de motor/biblioteca real de muestra:** Godot 4.3, Tyrano en Chromium, VNM en Chromium, Java JAR, i18next real.
- **Nivel B, instalador y recursos propios de formato real con fixtures y rollback:** LCF, KAG, Unity, Unreal LOCRES, GameMaker STRG, Light.vn.
- **Nivel C, investigación de variantes o herramientas de lectura:** demás familias que no tienen cadena Windows V95 y restauración demostradas en fuente consultada.
- **No confundir nivel A con una prueba física de videojuegos completos**. Los tests no cubren plataformas distintas ni autores de juegos comerciales desconocidos.

## 3. Plan de recuperación sin volver a hacer pruebas ya superadas

1. **TX777 P0:** comprobar que el EXE original abre una GUI real sin popup V95 y sin leer el paquete neuronal antes de mostrar una ventana, que el código de error se puede copiar y que el juego anterior no sufre cambios.
2. **Integración multimotor P0:** rescatar el código, manifiestos, hashes y pruebas del último TX200 apto para los once motores con evidencia, en adaptadores independientes. No instalar plugin JS MV/MZ sobre KAG, Unity, LCF, LOCRES o JAR. Bloquear submotores ambiguos.
3. **Seguridad P0:** cada adaptador debe conservar journal de instalación, SHA original, rollback byte exacto, modelos dentro de la carpeta del juego, cierre de proceso y no modificar partidas ni complementos de autor.
4. **Evidencia P1:** ensayar uno por uno en el EXE unificado con la versión exacta del runtime, reconocer cuándo no hay motor real; no afirmar compatibilidad comercial por éxito de CI.
5. **Entrega P1:** pruebas visuales sobre copia de juego, después cerrar y mover la **carpeta completa** a otra computadora offline sin reinstalar modelos.
6. **Mantenimiento:** no repetir íntegramente los CI históricos con el mismo SHA por costumbre; preservar sus comprobantes, importarlos como regression tests y repetir solo cuando cambien fuentes, runtime o binario.

## 4. Origen y límites de los datos

Documentos del repositorio histórico (solo lectura): `docs/TX200_QA_EXE_UNIFICADO_VERIFICADO_20261109.md`, `docs/TX200_KAG_WIN32_REAL_EXE_V95_20261109.md`, `docs/TX200_TYRANO174_CHROMIUM_REAL_F10_20261109.md`, `docs/TX200_UNITY_NEW_EXE_NATIVE_GUI_QA_20261109.md`, `docs/TX200_UNREAL_LOCRES_NEW_EXE_QA_20261109.md`, `docs/TX200_JAVA_JAR_V95_RUNTIME_QA_20261109.md`, `docs/TX200_I18NEXT_ACTUAL_LIBRARY_NEW_EXE_QA_20261109.md`, `docs/TX200_LIGHT197_WIN32_NATIVE_GUI_F10_20261109.md`, `docs/TX200_GAMEMAKER_BINARY_STRG_NEW_EXE_QA_20261109.md`, `docs/TX200_VNM179_REAL_WIN32_V95_CHROMIUM_PASS_20261109.md`. El origen original de V95 es SHA privado fijado y la rama pública de reconstrucción es independiente.

**Once cuentas conectadas:** se verificaron sus repos pertinentes y ramas de trabajo; algunas tienen múltiples versiones de un programa de otra plataforma que no son fuente de un instalador Windows y no deben importarse ni tocarse. La parte Windows reutilizable concentra evidencias en Drimt, Eduardo, Panda y Camacho. No se han leído todos los commits de cada rama histórica ni se han realizado miles de ejecuciones reales.

**Ningún juego del propietario, repositorio histórico o tercero se modificó en esta revisión.**
