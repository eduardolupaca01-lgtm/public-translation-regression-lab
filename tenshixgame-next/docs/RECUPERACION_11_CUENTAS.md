# TENSHIXGAME: reconstrucción unificada desde 11 conexiones GitHub

Fecha: 22 noviembre 2026. Rama pública aislada: rebuild/tenshixgame-unificado-deteccion-20261122. Base: main del laboratorio público de Eduardo, no la versión antigua TX772. Este documento conserva fuentes sin mezclar repositorios ni modificar cuentas externas.

## Requisitos aclarados por el propietario

La imagen TX200 era un EJEMPLO de organización por familias, no una referencia visual obligatoria ni un contrato de compatibilidad. Seleccionar «RPG Maker» solo fija la familia de búsqueda: el detector debe inspeccionar el EXE/carpeta e identificar 2000/2003, XP, VX, VX Ace, MV o MZ mediante firmas objetivas. Unite es un proyecto Unity y se analiza como tal si hay evidencia; U2U todavía no tiene detector probado. No asumir que RPG significa solo MV/MZ.

El flujo meta es seleccionar familia, seleccionar Game.exe o carpeta de una COPIA cerrada, analizar la versión sin escrituras, comprobar adaptador certificado, e instalar IA original V95 con modelos/caché/textos DENTRO del juego. La carpeta completa debe funcionar cuando se mueva a otra computadora Windows compatible; el jugador inicia su Game.exe sin tener que volver a ejecutar el instalador, sin API y sin un worker global. Los nombres de personajes, ventanas, elecciones, códigos del autor y partidas se preservan. Cuando el juego se cierra, deben terminar sus procesos.

El primer hito de reconstrucción solo inspecciona. NO traduce ni instala IA. No describir un SUCCESS de CI como una escena japonesa traducida.

## Inventario razonado de las once conexiones consultadas

| Cuenta conectada | Hallazgo pertinente | Decisión |
|---|---|---|
| ronal-huaman | Repositorios ajenos al traductor | Excluir, sin escribir |
| traductPoll | Investigaciones antiguas Ren'Py y versiones | Referencia documental sin certificación Windows |
| eduardolupaca01-lgtm | Código de traducción V95 y plugins TX765–TX771; compilador público y TX772 | Fuente principal, respetar procedencia/privacidad del motor |
| mario1999lupaca-hue | Trabajo de versiones Ren'Py y pruebas de laboratorio | No trasladar sus pruebas de otra plataforma a Windows |
| camachomauricio961-del | Estudios de versiones y seguridad de partidas | Solo ideas aplicables a formatos, sin modificar |
| lupacaeduardo0-gif | Laboratorio de varias revisiones Ren'Py | Consultar hipótesis; no certifica este programa Windows |
| blogsloprz-ship-it | TX200, matriz de 17 familias y ramas divergentes | Recuperar evidencia y fuentes verificadas |
| mauriciocamacho98765-byte | Material temprano V95 y perfiles, documentado en auditoría TX200 | Referencia histórica indirecta, sin modificaciones |
| drimt902-netizen | Código y entregable TX203 con 13 grupos de pruebas | Preservar pruebas y hechos, no sus errores de instalación |
| camachogomez791-byte | Sonda TX207, contratos de 17 perfiles, supervisor de sesiones | Recuperar controles de seguridad y detección |
| pandascanlation-art | Seis subfamilias RPG, texto nativo, menús F10 y pruebas posteriores | Recuperar contratos visuales seguros y migración |

Se revisaron las conexiones, inventarios, ramas relevantes y documentos clave. No se han revisado literalmente miles de veces ni cada commit de cientos de ramas: sería falso afirmar una auditoría total. Los README duplicados y las pruebas repetidas no se contabilizan como avances diferentes.

Fuentes primarias: 
- Auditoría cruzada de 8 cuentas: https://github.com/drimt902-netizen/tenshixgame-tx200/blob/1b48cc68815411b6be6dc75bdfc6ae3dfa0feac2/docs/TENSHIXGAME_DIAGNOSTICO_8_CUENTAS_17_FAMILIAS_20261110.md
- TX203 13 grupos de aceptación: https://github.com/drimt902-netizen/tenshixgame-tx200/blob/ad77dccc763424428003377a53848ed311bd1e21/docs/TX203_ENTREGA_VERIFICADA_20261110.md
- TX207 detección: https://github.com/camachogomez791-byte/tenshixgame-tx20026/blob/e259a80801e0d3ef971c41d14db939b25730932b/docs/TX207_FLASH_UNIVERSAL_VERSION_PROBE_20261110.md
- Camacho TX354: https://github.com/camachogomez791-byte/tenshixgame-tx20026/blob/e259a80801e0d3ef971c41d14db939b25730932b/audit/TX354_SEVENTEEN_FAMILIES_CONTRACT.json
- Panda 6 familias: https://github.com/pandascanlation-art/tenshixgame-tx/blob/9ddbc298741a803db7a9346e3e6e2a5edb8a69f3/docs/TENSHIXGAME_RPG_SIX_FAMILIES_INTEGRATION.md
- TX769 frente a TX203 y Ultra: https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/blob/a7b4788b434237b81912ac8ed7d88bfb358ccfd9/docs/TX769_AUDITORIA_TX203_RC_ULTRA_RENPY_Y_RPG.md

## Matriz de 17 familias: evidencia y límites

17 familias de interfaz NO son 17 perfiles de recurso ni 17 motores certificados. El registro TX354 identifica 17 familias, 17 perfiles en 14 grupos, cinco variantes de launcher y 0 de 52 escenarios de aceptación física en Windows 10 superados en su corte de fecha.

| Grupo | Avances recuperados | Bloqueo para certificar |
|---|---|---|
| RPG Maker | MV/MZ, RGSS XP/VX/VX Ace, LCF 2000/2003 | Diálogo visible y adaptadores diferenciados por generación |
| Ren'Py | SDK oficiales 7.8.7 y 8.3.7 con escenas de prueba | Versiones/juegos distintos, transferencia |
| Godot | Motor oficial 4.3 en escena de prueba | Juego real, ventana nativa |
| TyranoScript | Ensayos Chromium | Macros propias y partidas reales |
| KiriKiri/KAG | Archivos KS/TJS/codificaciones | Runtime de juego y eventos |
| HTML5/NW.js | NW.js oficial 0.119.2, páginas de prueba | WebViews y plugins de títulos reales |
| Light.vn | Guiones y GUI de pruebas | Runtime de autor, diálogos |
| Flash/SWF | Perfiles textuales acotados | Sin escritor universal ni proyector certificado |
| SRPG Studio | Catálogos/exportaciones | Hooks de ventana real |
| Visual Novel Maker | JSON y Chromium de prueba | Export real y persistencia |
| WOLF RPG | MPS/Data.wolf acotados | WOLF Pro y texto visible |
| Unity | Recursos Mono/IL2CPP de prueba | ABI/versión/juego y UI reales |
| Unreal Engine | LOCRES/PAK de prueba | IoStore y firmas, runtime real |
| GameMaker | FORM/GEN8/STRG y GML | Validación de data.win real por versión |
| Java/JVM | Swing, ResourceBundle y JAR de prueba | Aplicaciones reales y firmas |
| RPG Developer Bakin | Recursos/editor y diccionarios | Comprobar consumo en runtime |
| Node/i18next | Biblioteca i18next 23 de prueba | Namespaces y apps reales |

## Qué funcionó y qué sigue mal

TX203 probó 13 grupos con un mismo EXE en ensayos propios, pero no 17 juegos comerciales. Panda TX657-667 implementó sustitución en ventanas nativas en fixtures, sin duplicar el japonés con un overlay; no equivale a una aceptación del juego concreto. TX769 identificó claves de caché divergentes y guardas que impiden repintar una ventana después de recibir una traducción tardía. TX771/TX772 aprobaron 26 controles y la prueba de actualización portátil dentro de una carpeta de ensayo, sin demostrar una partida comercial completa ni otro Windows limpio.

Prioridades: (P0) cadena desde fuente real hasta píxeles en español con la misma identidad de frase; (P0) adaptador seleccionado por submotor; (P0) todo el motor y la caché dentro del juego; (P1) proceso hijo ligado al juego; (P1) instalación/restauración por SHA y backup; (P1) portabilidad y reuso de traducciones entre rutas; (P2) certificar una versión por vez para expandir cobertura.

## Nueva arquitectura y pruebas implementadas en esta rama

- internal/engine: 17 grupos de selección y detección acotada de firmas dentro de la carpeta seleccionada. Conflicto/ambigüedad bloquea instalaciones.
- internal/translation: clave SHA256 exacta fuente+idioma+familia+motor SIN ruta absoluta, independiente del cambio de disco. Preserva whitespace y códigos.
- cmd/tenshixgame-gui: ventana Win32 de selección y análisis. No es un instalador del modelo aún.
- cmd/tenshixgame: línea de comandos JSON para inspección técnica.
- .github/workflows/rebuild-tenshixgame-detection.yml: tests Windows/Linux y compilación de EXE de solo lectura.
- Ninguna cuenta histórica, juego ni repositorio original fue modificado.

Para poder publicar el verdadero EXE traductor se exigirán: pruebas de cada detector, V95 genuino firmado, instalación transaccional local, render in-place español de diálogos y opciones, restauración sin daño, cierre de workers y traslado de carpeta a otro Windows compatible. Compilar sin esos gates NO valida la traducción.
