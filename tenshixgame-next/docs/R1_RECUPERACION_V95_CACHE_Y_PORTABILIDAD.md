# TENSHIXGAME R1 — integración de hallazgos y controles V95

Corte: 22 de noviembre de 2026. Trabajo en rama pública de reconstrucción de Eduardo. No se editan juegos, repositorios históricos ni pesos originales. Este hito es diagnóstico y compatibilidad de datos, no traducción de juegos.

## Causa técnica recuperada

R0 introdujo inicialmente una clave SHA256 con esquema, familia, motor, idioma y texto, incompatible con el complemento auténtico para RPG Maker. En TX757–TX771 el complemento usa SHA-256 de UTF-8(idioma_fuente + NUL + texto_original), donde idioma_fuente es ja/en resuelto y nunca auto. La letra de disco y ruta del juego no forman parte de esa clave.

R1 corrigió translation.Key para igualar el complemento V95 real. translation.ScopedKey queda separado y sirve exclusivamente para inventarios; NO debe insertarse en el caché consumido por el complemento. Match exige también el contexto de motor y familia en pantalla. Los tests incluyen SHA esperados para japonés, inglés, texto con color y códigos de RPG, variantes de espacios y cambio de disco.

Fuente exacta consultada en la conexión privada de Eduardo: commit aeb9ff9326e418fbabe2d53dff7891f4fb340c37, archivo reference/tx331-clean-product-host/rpg_live_plugin/versions/tx757-patched-template.js. Esta anotación de procedencia no publica el código privado.

## Línea de recuperación y limitaciones

| Etapa | Salvar | Pendiente / descartar |
|---|---|---|
| TX200–TX203 | 17 familias como catálogo, QA de 13 grupos con el EXE histórico, adaptadores y restauración | No copiar interfaz antigua ni contar 17 motores certificados |
| TX314–TX325 | Contrato de proceso padre, sesión, PIDs y cierre acotado | Prueba real de no dejar procesos huérfanos |
| TX657–TX667 | Sustitución nativa en ventanas de mensajes y elecciones, F10, sin subtítulo superpuesto | Validar juegos con ventanas personalizadas |
| TX757–TX770 | Claves originales, JSON/SQLite, caché por entrada y prioridad del texto activo | Medir traducido, persistido y realmente dibujado por separado |
| TX771 | Sidecar autocontenido en el mismo disco con worker/modelos V95 | Comprobar Game.exe en una segunda PC |
| TX772 | Actualización protegida por SHA y conservación de caché y paquetes anteriores | En varios App antiguos se usa más espacio dentro del juego |
| R0–R1 | Detector de submotor, compatibilidad de clave, auditor de portabilidad y pruebas | Aún no instala ni invoca el V95 original |

Fuentes de contraste:
- TX203: https://github.com/drimt902-netizen/tenshixgame-tx200/blob/ad77dccc763424428003377a53848ed311bd1e21/docs/TX203_ENTREGA_VERIFICADA_20261110.md
- Panda TX657–667: https://github.com/pandascanlation-art/tenshixgame-tx/blob/bbbd2c306539a3afde8f8f97da168f116137a864/docs/TX657_667_RPG_REAL_TX203_NATIVE_DIALOGUE_CHOICE_F10.md
- TX772: https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/blob/541d6a10187ad77c9139343da8b5f3322ee509e7/docs/TX772_PUBLIC_OWNER_PORTABLE_UPGRADE.md

## Rutas EXACTAS recuperadas del complemento original

Juego/
  Game.exe
  www/js/plugins/TenshixgameRPGLive.js
  Tenshixgame-IA/
    portable-owner-v1.json
    App/<sha_del_paquete>/
    .local/TENSHIXGAME-RPG/
      engine/engine/TenshixgameAI.exe
      engine/engine/bundle_manifest.json
      live-cache/
        game-portable-<sha24_del_idioma>.json
        game-portable-<sha24_del_idioma>.live.json
        game-portable-<sha24_del_idioma>.live.json.entries/
          <primeros_dos_hex>/<sha256_del_texto>.json

Los nombres de archivos contienen el hash de auto, ja o en (24 primeros caracteres). Los registros de caché usan ja/en real, nunca auto. Los esquemas originales son tx394-live-cache-v1 (snapshot) y tx394-live-cache-entry-v1 (registro).

## Auditoría sin escrituras nueva

El paquete Go internal/portable/audit.go verifica sin arrancar ningún juego:

- Si el directorio Tenshixgame-IA existe y contiene el marcador propio con esquema y producto exactos. Si se encuentra una carpeta de otro propietario, no se toca.
- Si el SHA256 del worker de tamaño original coincide con el marcador local. La coincidencia no demuestra licencia, origen externo, modelos completos ni inferencia de IA.
- Presencia de manifiesto del modelo y complemento JS, sin decir que el juego lo haya ejecutado.
- Cuenta registros de caché con fuente y hash verificables, los archivos sin origen comprobable y registros rechazados.
- Cuenta los paquetes App de versiones anteriores conservados dentro del juego; no los elimina.
- Reconoce directorios de instalación temporal con ambos prefijos TX771, sin borrarlos. El onefile TX771 original ya hace limpieza diferida ante errores ordinarios; los directorios podrían provenir de interrupciones bruscas.
- Publica solo códigos y contadores; no muestra conversaciones del juego, claves, tokens ni rutas personales.

Los tests Go usan carpetas sintéticas, trabajadores de tamaño controlado, archivos JSON con claves reales, errores deliberados, symlinks y traslado de carpeta. No prueban calidad del español, juego comercial, Internet desconectado ni otro PC.

## Condiciones faltantes para la entrega completa

P0: conectar al nuevo selector el instalador auténtico del V95 original y solamente adaptadores cuya versión tenga prueba.
P0: comprobar del mensaje en el juego (incluidos nombres, opciones y menús) hasta los píxeles españoles; sin japonés duplicado ni reiniciar eventos.
P0: verificar todos los 22 recursos del modelo con el host original, no solo el hash del trabajador.
P1: mantener caché, SQLite y modelos dentro de cada juego, copiar a otra PC Windows y arrancar Game.exe directamente sin reinstalar.
P1: controlar el proceso trabajador con la identidad del proceso del juego y demostrar cierre completo.
P1: instalación y restauración exactas con backups, journal y SHA, sin tocar partidas.
P2: ampliar por familias/versiones solo tras aceptación. El catálogo de 17 familias es navegación, no 17 motores certificados.

No distribuir pesos V95, juegos privados o ejecutables sin cifrar en el repositorio público. No llamar al auditor R1 un traductor terminado.
