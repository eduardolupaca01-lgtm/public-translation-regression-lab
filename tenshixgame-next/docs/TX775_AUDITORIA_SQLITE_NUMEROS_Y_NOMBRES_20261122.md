# TENSHIXGAME — inventario acumulado de calidad del caché histórico (22-11-2026)

**Fuente inspeccionada en modo solo lectura:** `embedded-v88-pending.sqlite3` extraída de la copia histórica TX203/V88 suministrada para análisis. SHA-256 del archivo de SQLite: `bb274ee612fee0dfba55387197fcad1d935c29780da79b8c6ccae67b348369e9`. No se subió la base privada ni ninguna línea de diálogo al repositorio.

## Conteos confirmados de la tabla `segments`

| Indicador | Registros | Método y alcance |
| --- | ---: | --- |
| Total de segmentos | 6.664 | Todas las filas de `segments` |
| Marcados `done` | 6.646 | `state='done'`; no equivale a pintado real |
| Marcados `retry` | 18 | `state='retry'` |
| `done` con algún carácter japonés en resultado | 3.883 | Hiragana, katakana, CJK |
| Japonés solo en un control de nombre `\\N<...>` intacto | 3.874 | Se retira SOLO el control para evaluar el texto visible |
| Japonés restante en diálogo visible | 9 | Texto fuera del control protegido |
| `done` con números visibles diferentes | 152 | Se excluyen etiquetas `\\N<...>` y parámetros de escapes RPG; se normalizan dígitos de ancho completo |
| De las 152, se omitieron todos los números visibles originales | 116 | Hay dígitos originales y ninguno en resultado |
| De las 152, cambia el número de cantidades | 28 | La cantidad de grupos numéricos es diferente |
| De las 152, cambian los valores, manteniendo la cantidad de grupos | 8 | Valores distintos con igual número de grupos |
| `done` con discrepancia en comandos RPG reconocibles | 0 | Inspección limitada a controles reconocidos por el patrón del complemento original |
| Candidatos `done` con al menos una de esas alertas | **161** | Unión deduplicada de discrepancia de números y japonés visible; no son todos los posibles errores |

**Reintentos:** 7 de los 18 tienen como motivo declarado `RPG_CONTROL_CODES_MISMATCH`; los otros 11 corresponden a errores de inferencia o validaciones del motor. Los números anteriores son registros de una base histórica concreta, no métricas universales ni un porcentaje de acierto del traductor.

## Método reproducible

Se recorren solo los registros `done`. Para calcular números visibles, se copian los textos a memoria, se retira temporalmente el bloque intacto del nombre `\\N<...>`, se retiran comandos `\\V[12]`, `\\C[6]`, `\\I[4]` y otros escapes identificables y luego se comparan las listas ordenadas de dígitos, tras convertir `０-９` a `0-9`. El archivo original nunca se modifica. El patrón numérico utilizado cubre dígitos arábigos y de ancho completo; **no demuestra que números expresados en palabras ni cifras kanji sean semánticamente correctos**.

Los 161 registros constituyen **alertas de calidad de contenido o estructura**, no 161 fallos visuales observados. Tampoco implica que las 6.485 filas restantes tengan calidad semántica adecuada. Un actor japonés legítimo no debe convertir automáticamente una traducción al estado `retry`, pero alterar números reales o códigos de control tampoco puede permitirse.

## Correcciones integradas en la reconstrucción

- La clave de caché ahora replica `SHA256(idioma_ja_o_en + NUL + texto_original)` del complemento V95 auténtico y mantiene separada la identificación del motor para diagnóstico.
- El validador de nombres compara literalmente todos los bloques originales `\\N<...>` sin escribir sobre el nombre del personaje.
- Los códigos RPG de variables, colores, iconos y esperas se comparan en su **orden y parámetros originales**.
- Se exige coincidencia de los valores de los dígitos visibles, tolerando el cambio entre `５` y `5` y la reordenación de cantidades, como hace el núcleo V95 original.
- El auditor `portable.AuditRoot` verifica los registros de caché compatibles en modo solo lectura y distingue los fallos estructurales de la posible presencia de traducción española en la ventana.

## Prueba que aún falta

Hay que verificar el EXE neuronal V95 completo, el empaquetado exacto y una escena real del juego: nombre original visible, solo el cuerpo del diálogo en español, variables y decisiones intactas, reinicio y funcionamiento sin Internet en otra computadora. Una ejecución de GitHub Actions aprobada no sustituye esa validación de juego.

**Fuentes de implementación:** el complemento V95 original del commit fijado `aeb9ff9326e418fbabe2d53dff7891f4fb340c37`, y la rama de reconstrucción aislada `rebuild/tenshixgame-unificado-deteccion-20261122`. No se incorpora código privado ni pesos del modelo al repositorio público.
