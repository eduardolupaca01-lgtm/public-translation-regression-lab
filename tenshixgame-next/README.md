# TENSHIXGAME: nueva base Windows

Código nuevo separado de TX200, TX203 y TX772. Primer entregable: identificación de familia, motor y versión SIN ejecutar juegos ni instalar IA. Esta primera etapa no traduce.

En Windows descargue el artifact TENSHIXGAME-NEXT-Deteccion-EXE-PRUEBA desde:
https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/workflows/rebuild-tenshixgame-detection.yml

Extraiga ZIP y ejecute TENSHIXGAME-Detector-Visual.exe. Escoja entre las 17 familias, seleccione el EXE o carpeta de una COPIA del juego y pulse ANALIZAR. RPG Maker se inspecciona por generación: 2000/2003, XP, VX, VX Ace, MV, MZ. Unite usa runtime Unity. Si la versión exacta no puede verificarse, la herramienta la deja indeterminada. Nunca instala un adaptador por suposiciones.

La herramienta CLI se usa así:
TENSHIXGAME-Detector-CLI.exe -catalogo
TENSHIXGAME-Detector-CLI.exe -familia rpg-maker -juego "D:\Juegos\Copia\Game.exe"

Desarrollo: Go 1.22 o superior; desde la carpeta ejecutar go test ./... -count=1 y go vet ./... . En Windows el workflow compila también la interfaz Win32 con indicador windowsgui.

Estudio de las 11 conexiones, evidencias y próximos gates: docs/RECUPERACION_11_CUENTAS.md . No se distribuyen en GitHub público ni textos privados ni modelos neuronales. La instalación futura de IA original se hará solo tras certificar el adaptador para esa versión.
