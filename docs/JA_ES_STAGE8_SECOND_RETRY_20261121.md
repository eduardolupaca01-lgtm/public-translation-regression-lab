# Etapa 8 — diagnóstico y corrección v6 (21-11-2026)

Ámbito: investigación pública de traducción japonés a español latinoamericano, PR experimental #4. No modificar main ni fusionar sin los criterios de cierre.

## Comparación de ejecuciones neuronales originales

- Etapa 7, [run 44942504944](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44942504944): Qwen3-8B, 12 de 12 aceptadas por la rúbrica automática v2; reinicio SQLite PASS. Documento histórico: artifact 14723605383. Revisión humana independiente sigue pendiente. Traducción de medicamento: «Solo si \V[2] es mayor que 1, utilice un medicamento. De lo contrario, no lo use.» (sin inversión lógica del antecedente).
- Etapa 8, [run 44942328483](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44942328483): 10 de 12 aceptadas por la rúbrica v2; reinicio SQLite PASS. Documento histórico: artifact 14723449714. Se rechazaron dos fuentes; no modificar sus traducciones originales ni recalificar el recibo histórico.

## Dos causas del fallo de la etapa 8

1. Testigo y nombres. Japonés: 「ハナが駅を出たのを太郎は見ましたが、ミカは見ていません。」. Salida del modelo: «Taro vio cuando Hanako salió de la estación, pero Mika no lo ha visto». Error real: «Hanako» añade caracteres al nombre original «Hana», y la referencia del objeto visto es ambigua. Los dos modos segmentados omitieron la estación y la salida. El rechazo debe permanecer.
2. Condición RPG. Japonés: 「\V[5]が4以下なら、この扉を開けないでください。5以上なら開けてもかまいません。」. Salida: «\V[5] que sea 4 o menos, no abra esta puerta. Si es 5 o más, está bien que la abra». «Está bien que la abra» conserva el permiso, pero la rúbrica no reconocía el subjuntivo con pronombre femenino; rechazo parcialmente falso. Además, «\V[5] que sea» no es un comienzo idiomático: aunque se repare el detector de permisos, es necesaria una nueva generación para mejorar la gramática. En el modo de líneas se mezcló texto japonés y español, rechazo estructural correcto.

## Reparaciones aplicadas sin falsificar aprobaciones

- Commit [eaa492f](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/commit/eaa492f841c861d8f4105dab97c2ab79117088ce): herramienta general de lectura fonética de katakana derivada exclusivamente del japonés. Produce pistas de romanización, no traducciones españolas preparadas ni sustituciones de salida. Se usa la misma regla para todas las fuentes; no hay nombres privilegiados por caso.
- Commit [be77431](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/commit/be7743107c2aeb2a70b081e218567401157f9ead): prompt uniforme v6 que refuerza nombres, observador y observado, condiciones numéricas, gramática y pronombres. La rúbrica v3 reconoce las construcciones afirmativas «está bien que la abra» y sigue rechazando «no está bien que la abra» o límites invertidos. Tests adversariales añadidos. Fuente japonesa original, códigos RPG y las salidas de las corridas anteriores sin cambios.
- Nueva inferencia real iniciada: [run 44949496509](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44949496509). No atribuir puntuación hasta que finalicen la inferencia y la comprobación de reinicio.

## Bloqueos pendientes

La etapa 8 se encuentra en corrección, no aprobada. Un eventual 12/12 por rúbrica no constituye validación lingüística profesional: faltan la revisión bilingüe independiente de etapa 9 y una prueba externa verdaderamente ciega para justificar calidad generalizable. La etapa 10 debe permanecer en HOLD mientras falten aprobaciones o haya cualquier fallo semántico. El PR #4 continúa en borrador y main no se modifica.
