# Diagnóstico verificable etapa 6 — investigación JA → ES-419

Corte: 2026-11-21. Repositorio exclusivo de investigación `eduardolupaca01-lgtm/public-translation-regression-lab`. No modificar pesos, entradas japonesas, traducciones originales, ni el historial de resultados.

## Fallo original: confirmado, no de infraestructura

- [GitHub Actions run 44916896907](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44916896907), commit inmutable `1696e51501e706f8b72a534d9063628104b129f1`, conclusión **FAIL**.
- Artefacto original `14714567203` (`stage6-dialogue-sixteen-research-receipts`), dentro `stage6-neural-report.json`, `stage6-source-manifest.json`, `stage6-cold-restart-proof.json`, `stage6-review-queue.json`, SQLite y logs.
- **13/16** superaron la rúbrica automática v1, **3/16 rechazados**; `model_executed=true`, `cache_rows=13`, `review_queue_total=3`. Proceso frío: `persistence_status=PASS`, `rubric_status=FAIL`, `models_loaded_during_restart=false`.
- Los **16 textos japoneses originales permanecen inalterados**. El corpus es de investigación sintético y publicado, nunca una prueba ciega externa.

## Los tres rechazos en sus propias palabras (NO reescribir)

1. `search_not_found_roles` (みんなは彼を探していますが、まだ誰も彼を見つけていません): modelo modo `document_context`: «Todos están buscándolo, pero aún no lo han encontrado.» La rúbrica exigía «nadie», ignorando una paráfrasis colectiva contextual comprensible. `line_context` devolvió «Todo el mundo lo busca, pero aún no lo han encontrado.» Rechazos por `NO_ONE_MISSING`/`SEARCHERS_MISSING`.
2. `permission_changed_today` (昨日は中に入ってもよかったですが、今日は入ってはいけません): modelo «Ayer podría haber entrado, pero hoy no se debe entrar.» Rechazo `PAST_PERMISSION_LOST` porque el detector solo reconocía `pod[ie]`, no `podr`. **Advertencia de matiz**: «podría haber entrado» puede ser posibilidad contrafactual en vez de permiso pasado; debe quedar para revisión bilingüe, no eliminarlo de la evaluación.
3. `files_delete_only_old` (古いファイルは消してもいいですが、新しいファイルは絶対に消さないでください): modelo «Puedes eliminar los archivos antiguos, pero por favor, no borres los archivos nuevos.» Rechazo `OLD_FILE_LOST|NEW_FILE_LOST|FILE_LOST` por expresiones regulares que no reconocían plurales españoles. Esta es una traducción semánticamente correcta bajo la intención original.

## Errores descubiertos entre los 13 casos antes aceptados

- `two_item_cost_total`: «El espada cuesta 1500 yenes» viola concordancia gramatical; debe detectar `el/un espada`, no tratar esta frase como éxito lingüístico.
- `two_speakers_ask_sara`: en la misma respuesta aparece «Sara» y «Sarah» para el mismo personaje. El código de evaluador ahora bloquea **inconsistencia intradocumental**, no prohíbe una transliteración alternativa uniforme.
- `green_appearance_apple`: «Hay una manzana azul. La apariencia es verde» necesita aclarar el contexto de 青いリンゴ; no alterar automáticamente un color japonés ambiguo.
- `sword_companion_return`: «Después de meterla en la bolsa, devuélvala» deja implícito el referente de «a ella». Requiere revisión humana aunque preserve objeto y pronombre correctos.
- `shop_tomorrow_day_after`: «a las 8 de la noche de mañana» comprensible pero poco idiomático; tampoco es aprobación profesional.

## Corrección realizada: v2 (rúbrica) + v3 (generación uniforme)

Commit: [2ac4819ab4ddf676e7dc65dd001b10326ec38f0b](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/commit/2ac4819ab4ddf676e7dc65dd001b10326ec38f0b).

- `tools/stage6_dialogue_cases.py`: acepta flexión plural legítima, formas de poder en condicional, y paráfrasis colectiva con objeto explícito. **Aumenta** rigor respecto al género `el/un espada`, la inversión de agente y la escritura inconsistente del mismo nombre entre intervenciones. El permiso pasado condicional conserva una **bandera de revisión**, aunque pase el detector de vocabulario.
- `tools/stage6_discourse_model.py`: variante **uniforme** `uniform_discourse_conditions_grammar_v3` con verificación de permiso pasado, concordancia de artículos/objetos, nombres consistentes, negaciones y relación de sujeto/objeto. Mantiene el **mismo** peso Qwen3-8B Q4_K_M fijado, seed 42, configuración de muestreo, runtime y timeout; no hay prompt por caso, ni referencias de destino dadas al generador.
- `tools/stage6_dialogue_neural_research.py`: registra rúbrica versionada `stage6_conditions_roles_grammar_rubric_v2` y flags de revisión sin dar por aprobada la calidad humana.
- `tests/test_stage6_dialogue_neural_research.py`: nuevas pruebas de paráfrasis válidas, plural, permiso pasado ambiguo, género incorrecto, cambio de nombre y errores de papeles. Se conserva el manifest de japoneses y las respuestas originales como recibos distintos.

## Nueva ejecución real y condiciones para avanzar

[Stage6 Qwen3 v3 nueva inferencia: run 44924198938](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44924198938), en progreso al escribir este documento. Las regresiones Ubuntu/Windows son [44924198984](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44924198984) y [44924203901](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44924203901), comprobar final.

- Solo declarar 16/16 bajo rúbrica **v2** si los 16 informes fuente y respuestas realmente resultan aceptados, la revisión de caché en nuevo proceso termina PASS y ninguna salida fue corregida a mano.
- Si aparece cualquier error, registrar número y motivo exactos y **no** debilitar el criterio para forzar la nota.
- La siguiente etapa es investigación diferenciada: preparar fuentes japonesas nuevas no solapadas y exigir la puerta de calidad anterior; no integrar al software ni fusionar a `main` hasta disponer de revisión bilingüe independiente.

## Continuidad
Leer también `docs/JA_ES_TRANSLATION_HANDOFF_20261121.md`; código en `experiment/qwen3-ja-es-candidate-20261120`, PR #4 permanece `draft`. Respaldo etapa 5: `checkpoint/stage5-validated-20261121`. La evaluación histórica v1 conserva **13/16**, no se sobrescribe.
