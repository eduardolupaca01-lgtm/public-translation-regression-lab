# SERVIDOR — Primer lote RPG Maker MV (Windows 10 x64)

**Un solo producto: Servidor.** Sección «RPG» activa; las demás hojas son marcadores
vacíos. No se presenta una selección de motor al usuario. En este primer lote la
única variante permitida por el instalador es **RPG Maker MV**. MZ, otros RPG,
SRPG y otras familias no se activan.

## Reutilización concreta

- Interfaz Win32 y flujo de arranque no modal de TX777, sin un nuevo motor.
- Instalador reversible, journal, verificaciones SHA y restauración originales
  de `reference/tx331-clean-product-host`.
- Complemento de diálogos y opciones nativos de RPG Maker, caché SQLite y V95
  original recuperados **solo en la copia temporal privada de CI**.
- Paquete portátil TX771–TX776 dentro de la carpeta del juego y continuidad de
  las 26 puertas de construcción originales. No se deshabilitan pruebas para publicar.
- Proveedor de código: cuenta de Eduardo. Otros repositorios son solo referencias.

## Seguridad y límites

El código público NO contiene modelos, juegos, tokens ni EXE privado descifrado.
`patch_servidor.py` solo adapta la interfaz y aplica una compuerta de firmas MV
a un checkout privado fijado por SHA; no modifica fuentes históricas. No se
importa código de motores ajenos a esta hoja.

La selección y el botón de instalar vuelven a verificar firmas de RPG Maker MV:
`rpg_core.js`, `rpg_managers.js`, `System.json` y `plugins.js`. Un layout mixto
MV/MZ, rutas enlazadas o una instalación de otro motor se rechazan antes de
preparar modelos. La rama de otras hojas permanece inactiva.

La nueva cadena de CI usa los controles heredados completos y entrega únicamente
un `Servidor.exe` **dentro de un .7z cifrado** cuando todos los controles pasan.
No se certifica una traducción en el juego comercial a partir de pruebas
sintéticas o del hecho de que se haya compilado.

## Validación

```bash
python tools/servidor/patch_servidor.py --self-test
```

En GitHub Actions, ejecutar `servidor-rpg-mv-win64.yml` en esta rama. No usar
el candidato si aparece `SERVIDOR-RPG-MV-HOLD` o si falta el artefacto cifrado
correcto.

**Criterio mínimo de aceptación real:** instalación de MV en copia cerrada,
el español reemplaza textos nativos y opciones sin una capa extra, F10 mantiene
su función, la segunda apertura reutiliza la caché, las partidas son intactas,
el motor termina al cerrar el juego y la restauración devuelve los bytes previos.

Fuente de estado y pruebas heredadas: [PR de integración TX777](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/pull/7).
