# TENSHIXGAME — comparación de 11 cuentas y estado del rompecabezas TX776

Fecha: 22 de noviembre de 2026. Solo se escribió en la rama pública de reconstrucción de Eduardo. Los repositorios de origen se consultaron en modo lectura. No se ejecutó código de los otros proyectos ni se manipularon datos de juegos del usuario.

## Método: qué se revisó y qué NO se afirma

Se enumeraron las once cuentas GitHub conectadas, sus repositorios pertinentes, ramas de desarrollo (páginas disponibles), árboles de fuente y documentos primarios sobre adaptación de motores, construcción Windows, instalación, seguridad y texto visible. Algunas ramas superan 100 resultados y necesitan paginación adicional: **no se han examinado todos los commits, ni existen 3000 verificaciones literales**. Los estados se fijan por SHA y por tipo de prueba, para no contar una misma rama compartida entre cuentas como varios avances.

Escala: E0 = fuente/doc identificados; E1 = test sintético; E2 = EXE Windows real con IA original verificada y paquete cifrado; E3 = prueba de traducción visible dentro de juego del propietario; E4 = traslado de carpeta y ejecución offline en otro Windows real.

## Cuentas y contribuciones a recuperar

| Cuenta conectada | Fuente relevante | Evidencia y decisión |
|---|---|---|
| ronal-huaman | Listado de 8 repositorios; ninguno identificado como traductor Windows de esta línea | No reutilizar ni modificar los repositorios de otros proyectos |
| traductPoll | [renpy-universal](https://github.com/traductPoll/renpy-universal) | Matrices de runtime Ren'Py; revisar como investigación de versiones, no como adaptador Windows certificado |
| eduardolupaca01-lgtm | [V95 original](https://github.com/eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build) y [laboratorio público](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab) | Fuente canónica del modelo y puente MV/MZ. TX771–TX775 compilado cifrado y QA de 26 gates. R1/TX776 en rama pública aislada |
| mario1999lupaca-hue | [renpy-universal-lab](https://github.com/mario1999lupaca-hue/renpy-universal-lab) | Investigación Ren'Py por versión; su main comparte SHA con otra cuenta: no sumar como prueba diferente |
| camachomauricio961-del | [renpy-universal-lab](https://github.com/camachomauricio961-del/renpy-universal-lab) | Matrices de guardados y menús; pruebas de otra plataforma no habilitan un instalador para Windows |
| lupacaeduardo0-gif | [renpy-universal-lab](https://github.com/lupacaeduardo0-gif/renpy-universal-lab) | Investigación general de compatibilidad; no mover ejecutables, estado de partidas ni código de aplicaciones ajenas |
| blogsloprz-ship-it | [renpy-universal-lab](https://github.com/blogsloprz-ship-it/renpy-universal-lab) | Historial de formatos, runtimes y catálogos; conservar hipótesis verificables sin mezclar aplicaciones |
| mauriciocamacho98765-byte | [renpy-universal-lab-qa](https://github.com/mauriciocamacho98765-byte/renpy-universal-lab-qa) | Precedente mínimo de pruebas de runner; no contiene un traductor Windows final en su main |
| drimt902-netizen | [tenshixgame-tx200](https://github.com/drimt902-netizen/tenshixgame-tx200) | Matriz histórica TX200 de 17 familias, pruebas TX203 y datos de recuperación. No reinstalar íntegramente su antiguo supervisor |
| camachogomez791-byte | [tenshixgame-tx20026](https://github.com/camachogomez791-byte/tenshixgame-tx20026) | Sonda TX207, contratos de 17 perfiles, ciclo de vida de procesos y TX710 diagnóstico JSONL. Su escritura en AppData NO cumple el modelo totalmente portátil del usuario |
| pandascanlation-art | [tenshixgame-tx](https://github.com/pandascanlation-art/tenshixgame-tx) | TX657–667 sustituyen diálogo y opciones dentro de sus ventanas nativas, con F10 y sin caja sobrepuesta; fixtures no equivalen a juego real |

Duplicados comprobados: los SHA principales 5c89a246e2497fe412a7846b4dea934c23f54b66 y 21a60a2a0b2748cec02b758435f37d9f3768e495 aparecen en más de una cuenta. No son desarrollos distintos solo porque figuren con dos propietarios.

## Motores: catálogo versus capacidad real

El catálogo original de 17 grupos incluye RPG Maker, Ren'Py, Godot, TyranoScript, KiriKiri/KAG, HTML5/NW.js, Light.vn, Flash/SWF, SRPG Studio, Visual Novel Maker, WOLF RPG, Unity, Unreal Engine, GameMaker, Java/JVM, RPG Developer Bakin y Node/i18next. Son grupos de selección, NO 17 instalaciones certificadas.

- RPG Maker MV/MZ: puente V95 local, caché, instalación/restauración, F10, diálogos y opciones en ventana nativa. E2 sintético, E3/E4 no acreditados sobre el juego del propietario.
- RPG Maker XP/VX/VX Ace: puente Ruby RGSS histórico; no conectado como instalador certificado al mismo botón. RPG Maker 2000/2003: LCF de lectura/preflight sin escritor/inyección verificados.
- WOLF RPG, SRPG Studio y RPG Developer Bakin: inventarios y recursos acotados; no habilitar instalación automática sin adaptación runtime.
- Ren'Py y motores web, 3D, Java y catálogos restantes: pruebas de formatos/versiones y algunos runtimes controlados en distintas ramas, no certificado universal con 52 escenarios físicos Windows.

Fuentes contrastadas: [matriz TX200](https://github.com/drimt902-netizen/tenshixgame-tx200/blob/ad77dccc763424428003377a53848ed311bd1e21/docs/TENSHIXGAME_TX200_MATRIZ_17_FAMILIAS_20261107.md), [TX354 17/17/5 y 0 de 52 escenarios físicos en aquel corte](https://github.com/camachogomez791-byte/tenshixgame-tx20026/blob/e259a80801e0d3ef971c41d14db939b25730932b/audit/TX354_SEVENTEEN_FAMILIES_CONTRACT.json), [TX590 seis familias RPG](https://github.com/eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build/blob/109fdc73a835e894b8804a27133e66360e4ba8c6/docs/TX590_RPG_SIX_ENGINE_REAL_V95_AUDIT.md), [TX657–667 ventana nativa](https://github.com/pandascanlation-art/tenshixgame-tx/blob/9ddbc298741a803db7a9346e3e6e2a5edb8a69f3/docs/TX657_667_RPG_REAL_TX203_NATIVE_DIALOGUE_CHOICE_F10.md).

## Componentes que hay que conectar

| Bloque | Recuperado / prueba | Pendiente real |
|---|---|---|
| Detector y selección | R1 identifica 17 familias por firmas, variantes ambiguas se bloquean | Adaptador específico por versión y juego |
| IA V95 original | TX775 compiló el EXE cifrado con 26 gates en Windows; usa local sin servicio externo | Prueba de traducción real y archivo local al cambiar computadora |
| Cache/diccionarios | TX757–TX775 y R1 comparten clave nativa, verifican textos, números y códigos RPG | Contar realmente frases solicitadas, persistidas, recuperadas y dibujadas |
| Ventana nativa y F10 | Panda + Eduardo hooks MV/MZ y pruebas TX768 | Nombres personalizados, opciones, menús y primera pantalla del juego del propietario |
| Backup y journal | TX395, TX589, TX771–TX775; CI de actualización TX772→TX775 verde | Recuperación de otros estados parciales y restauración en juego real |
| Portabilidad y procesos | TX771/TX772 y contratos TX314–TX325 | Segundo Windows offline, cierre total de worker al cerrar Game.exe |
| Diagnóstico de instalación | TX710 JSONL/Windows y TX647 con panel; **TX776** nuevo historial acumulado y botón copiar | Compilación cifrada TX776 y prueba de la copia del informe en UI real |
| Resto de motores | Lectores/adaptadores de investigación y lotes históricos | Instaladores independientes, reversibles y probados por submotor |

## Diagnóstico TX776 diseñado a partir del panel solicitado

El cuadro grande «Estado de instalación» del instalador original ya existía, pero cada mensaje reemplazaba todo su contenido. El nuevo programa conserva una secuencia visible y un botón COPIAR DIAGNÓSTICO PARA ENVIAR. Los hitos registran selección, detector del motor, motor V95, verificación de pesos, carpeta portátil y propiedad, instalación atómica, diario/respaldo, activación de plugin y error/éxito. El mensaje de error muestra código y consejo, sin publicar rutas personales, credenciales, tokens del puente ni líneas del juego. No se escriben registros en un perfil global.

Comparación con [TX710 de Camacho](https://github.com/camachogomez791-byte/tenshixgame-tx20026/blob/e259a80801e0d3ef971c41d14db939b25730932b/docs/TX710_DIAGNOSTICS_RUNTIME_LOGGING.md): su estructura de eventos es recuperable, pero usa AppData y puede registrar rutas; TX776 usa un informe de GUI para copiar voluntariamente. Comparación con [TX567](https://github.com/eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build/blob/109fdc73a835e894b8804a27133e66360e4ba8c6/docs/TX567_RPG_WINDOWS_ACCESS_DENIED_DIRECTORY_RENAME_FIX.md): distinguir error de cambio de nombre por antivirus/permisos de un fallo auténtico de pesos, sin recomendar desactivar antivirus.

**Límite del nuevo panel:** los errores del descompresor/launcher anteriores a la apertura de esta ventana requieren su propio mecanismo de informe. TX776 no debe afirmar que ha capturado esa fase ni que traduce otros motores.

## Puertas de aceptación finales

Probar sobre una COPIA con el juego cerrado: escenas japonesas e inglesas, nombre NPC, opciones, F10, códigos variables, pantallas personalizadas, reinicio, restauración, juego offline, traslado a otro Windows, caché sin repetir inferencias, procesos cerrados y ningún registro persistente fuera del juego. En cada prueba registrar SHA y versión del adaptador. Un test sintético o verde en CI NO sustituye estas pruebas de usuario.
