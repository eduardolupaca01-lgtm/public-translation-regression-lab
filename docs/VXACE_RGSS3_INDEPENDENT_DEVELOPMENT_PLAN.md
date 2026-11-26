# RPG Maker VX Ace / RGSS3 — plan de implementación independiente

## Identidad y punto de partida

- Repositorio: `eduardolupaca01-lgtm/public-translation-regression-lab`.
- Rama nueva: `feature/servidor-rpg-vxace-rgss3-independent-20261126`.
- Base exacta: `main` en `da386ca5652b28fa40b5d702189971de386688db`.
- Alcance: RPG Maker VX Ace / RGSS3.
- Estado: diseño y criterios de aceptación; todavía no hay ejecutable ni compatibilidad de producción declarada.

Esta rama se creó directamente desde `main`, no desde la rama MZ ni desde la rama RGSS3 experimental anterior. No incorpora commits, archivos fuente ni cherry-picks de Panda, Camacho o las ramas anteriores de Eduardo. Los repositorios previos se consultan como evidencia técnica y como registro de errores.

## Qué aprendimos de las ramas de Eduardo

### Método que sí conviene conservar

Las PR #8, #10 y #11 muestran un flujo útil:
- abrir una rama de función y una PR en borrador;
- declarar alcance y límites;
- separar pruebas del instalador, del complemento, del worker y del empaquetado;
- mantener la rama principal intacta;
- no presentar una compilación como aceptación dentro de un juego real.

### Errores de proceso que no repetiremos

La rama experimental RGSS3 anterior:
- se basó en `feature/servidor-v2-rpg-mz-20261124`, no en una base independiente;
- su workflow escuchaba tanto `push` como `pull_request` y apuntaba la PR a la rama MZ, generando ejecuciones repetidas;
- ejecutaba la comprobación Ruby solo en Windows y usaba Ruby 2.7.8, que no acredita compatibilidad con el Ruby integrado en VX Ace;
- usaba stubs/fixtures sintéticos, no el runtime RGSS3 original de un juego;
- la prueba TX440 aceptaba un subtítulo superpuesto mediante Sprite/Bitmap. Eso no demuestra sustitución nativa del texto dentro de la ventana original;
- la propia PR #12 reconocía que el instalador Go/UI y el empaquetador no despachaban el nuevo helper, que no se había probado con un juego real y que la compatibilidad de producción no estaba certificada.

No repetiremos esas pruebas como si fueran una aceptación nueva. Se conserva la información de sus fallos y límites, no su código.

## Registro de referencias externas y de otras cuentas

| Referencia | Información útil | Límite que debemos respetar |
|---|---|---|
| Panda TX437–TX444 | Hook RGSS en vivo, cola local, restauración, eventos de diálogo y diagnóstico | El prototipo interceptaba `Bitmap.draw_text`, creaba un subtítulo auxiliar y rechazaba archivos `.rgss3a`; no cumple la sustitución nativa requerida |
| Panda TX445–TX452 | Descriptor del worker, identidad del proceso, sesión autenticada y ciclo de vida | El artefacto descrito era diagnóstico sin pesos V95; no acredita traducción neuronal ni aceptación comercial |
| Camacho TX314–TX322 | Ciclo de vida, supervisor de procesos, recuperación de sesión y migración de adaptadores | Referencia de diseño de proceso, no implementación RGSS3 |
| Panda TX720–TX723 | Pruebas de texto japonés, elección, F10, nombre del jugador y límites del renderizado | Las pruebas de otras familias no certifican RGSS3 |
| Eduardo PR #8/#10/#11 | Separación de instalador, complemento, worker, modelos y empaquetado | Las pruebas sintéticas y los artefactos de diagnóstico no sustituyen la ejecución en el juego real |

## Hechos técnicos que condicionan el diseño

1. RGSS3 de VX Ace utiliza Ruby 1.9.2-p0. El runtime que carga el juego es el que debe validar el script final; una comprobación con Ruby 2.7 o Ruby moderno no basta.
2. El flujo de arranque usa `Game.ini`; si existe `Game.rgss3a`, el juego lee los scripts desde ese archivo cifrado. No debemos asumir que modificar un `Data/Scripts.rvdata2` suelto afectará al juego empaquetado.
3. `Scripts.rvdata2` es un contenedor Marshal con entradas de script comprimidas. El lector/escritor debe conservar IDs, nombres, orden, contenido y entradas ajenas al parche.
4. En el intérprete VX Ace, el comando 101 (Show Text) puede consumir los comandos siguientes de opciones (102), entrada numérica (103) y selección de objeto (104). El comando 102 también puede ejecutarse por separado. El texto desplazable utiliza el comando 105.
5. El hook visual debe trabajar con el flujo nativo de `Game_Message`/`Window_Message`. No se aceptará una segunda ventana, Sprite, OCR ni un subtítulo superpuesto como sustituto del texto original.

Fuentes técnicas consultadas:
- RGSS3 / Ruby 1.9.2 y carga de `Game.ini`, `Game.rgss3a` y `Scripts.rvdata2`: https://gist.github.com/qnighy/fcde38b116037cf75df8
- Formato de proyecto, lectura/escritura y comandos de `rvpacker-txt-rs`: https://github.com/RPG-Maker-Translation-Tools/rvpacker-txt-rs
- API de lectura/escritura Marshal y formatos de RPG Maker: https://docs.rs/rvpacker-txt-rs-lib/latest/rvpacker_txt_rs_lib/

`rvpacker-txt-rs` y su biblioteca son candidatos de investigación, no dependencias aprobadas automáticamente. Antes de fijarlos se verificará versión, licencia, procedencia, dependencias transitivas, soporte de CPU y comportamiento en Windows x64. Sus binarios publicados indican un baseline x86-64-v2/AES-NI; no se asumirá que funcionen en todos los equipos.

## Arquitectura que se construirá desde cero

1. **Fingerprint de solo lectura.** Identificar VX Ace por evidencias coherentes de `Game.exe`, `Game.ini`, biblioteca RGSS3 y archivos de datos. No ejecutar el juego ni modificar archivos durante detección.
2. **Lector de archivos y archivos cifrados.** Leer `Data/*.rvdata2` y `.rgss3a` con límites de tamaño, rutas seguras, detección de duplicados y rechazo de archivos truncados/ambiguos. Trabajar sobre copias temporales.
3. **Capa Marshal.** Extraer y reconstruir datos y scripts manteniendo IDs, orden, codificación y bytes/contenido de elementos no seleccionados.
4. **Modelo de texto tipado.** Diferenciar diálogo, opción, texto desplazable, base de datos, términos del sistema y nombres propios. Preservar códigos RGSS, variables, formato, índices y marcadores dinámicos.
5. **Adaptador de traducción.** Definir un contrato explícito con el worker V95: identidad, autenticación, lotes, orden, timeouts, errores, caché y publicación atómica. No aceptar un mock como prueba de modelo real.
6. **Runtime RGSS3 nativo.** Compatible con Ruby 1.9.2. Traducir la primera presentación dentro de la ventana original, conservar el avance de eventos y las IDs de elección, y no mostrar una segunda superficie. Si el servicio no responde, mantener el original y permitir continuar sin corromper la escena.
7. **Instalación y restauración.** Instalar únicamente en una copia cerrada/autorizada. Registrar SHA-256, respaldo, recibo y estado transaccional. Rechazar cambios externos y restaurar de forma idempotente.
8. **Integración y empaquetado Windows.** Solo después de aprobar las capas anteriores se conectará el selector/instalador y se preparará el EXE con todos los componentes y modelos autorizados.

## Matriz de aceptación: seis puertas, no una cadena interminable

| Puerta | Evidencia necesaria | Criterio de salida |
|---|---|---|
| A. Detección | Fixtures de VX Ace, XP, VX, MV/MZ, carpetas ambiguas y rutas Unicode | VX Ace se reconoce; otros motores y casos ambiguos se rechazan correctamente |
| B. Archivo/Marshal | Lectura, extracción, round-trip, entradas duplicadas, traversal, truncado y límites | Solo cambia el contenido previsto; entradas ajenas se conservan; restauración recupera el original |
| C. Runtime Ruby | Sintaxis/ejecución con Ruby 1.9.2 compatible, comandos 101/102/103/104/105, variables y códigos | Texto y opciones cambian en la ventana nativa; no hay overlay, doble ventana ni avance de evento |
| D. Worker real | Worker V95 identificado y autenticado, modelo real, caché fría/caliente, timeout y desconexión | La primera presentación se resuelve correctamente; respuestas tardías no contaminan otra escena |
| E. Instalación Windows | Copia de juego autorizada, rutas con espacios/Unicode, permisos, cierre/reapertura y restauración | Instalación y rollback verificables en Windows x64; partidas y datos no seleccionados intactos |
| F. Entrega | EXE, helper/runtime, modelos, manifiestos, licencias y hashes | El paquete contiene lo necesario y arranca; no se publica un ejecutable reducido o sin modelo como versión final |

### Regla para evitar repetir pruebas sin fin

- Cada puerta tiene fixtures y resultado de aceptación definidos antes de implementarse.
- Una puerta aprobada queda registrada con commit, workflow, artefacto y hashes.
- Un cambio posterior ejecuta primero las pruebas de la puerta afectada y sus dependencias; no vuelve a ejecutar toda la historia de otros motores.
- La batería completa se ejecuta una vez sobre el candidato final.
- Un fallo debe señalar una puerta y un caso reproducible. No se añaden pruebas genéricas sin una causa o riesgo concreto.
- Las pruebas simuladas, las pruebas con worker/modelo real y la prueba de juego comercial se reportan por separado.

## Política de rama y CI

- Una sola rama de desarrollo independiente y una PR en borrador dirigida a `main`.
- Un único workflow RGSS3 para esta rama/PR, con `pull_request` hacia `main` y `workflow_dispatch`; no duplicar la misma matriz con triggers simultáneos de push y PR.
- Concurrencia por PR para cancelar ejecuciones obsoletas.
- Sin artefacto de distribución hasta superar las puertas A–F.
- Sin fusionar automáticamente la PR ni modificar `main`.

## Estado actual

- Rama independiente creada desde `main`.
- Este documento fija el método y la matriz de aceptación.
- No se ha copiado código de las ramas RGSS anteriores.
- No se ha modificado `main`, ningún repositorio de Panda/Camacho ni ningún archivo de juego.
- No existe todavía un EXE VX Ace aprobado. La primera implementación será el fingerprint de solo lectura y su batería pequeña de fixtures; no se afirmará integración antes de completar las puertas correspondientes.
