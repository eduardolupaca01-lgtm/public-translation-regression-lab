# Etapas 6 y 7: diagnóstico de los dos bloqueos, 21-11-2026

**Único ámbito:** investigación de traducción japonés → español latinoamericano, [repositorio](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab), PR #4 en borrador. Documento de traspaso, no autorización de integración. Los JSON, textos japoneses, salidas originales del modelo y caché de las ejecuciones históricas NO se modificaron.

## Evidencia de las ejecuciones históricas

| Etapa | GitHub Actions | Rúbrica histórica | Persistencia | Resultado real |
|---|---|---|---|---|
| 6, variante uniforme v3 | [44924198938](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44924198938) | **15 aceptadas / 1 rechazada** | **PASS** tras reinicio frío | FAIL |
| 7, variante uniforme v3 | [44924682863](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44924682863) | **10 aceptadas / 2 rechazadas** | **PASS** tras reinicio frío | FAIL |

Los informes señalan `model_executed=true`, `target_repairs=false`, `human_approvals=false` y `professional_quality_approved=false`. Ambos usaron el mismo modelo `Qwen/Qwen3-8B-GGUF` (Q4_K_M), revisión `7c41481f57cb95916b40956ab2f0b139b296d974`, pesos SHA-256 `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`; `llama.cpp` `b12584`, semilla 42 y modo `think`. SHA-256 del prompt v3 `03ed810a734e2231c061c4ebeca839bb8ee4cf287da5dc6edf9a413450747090`.

Comprobantes originales archivados en GitHub:
- Etapa 6, artifact **14717167427**, ZIP SHA-256 `6799f73d0c871db79853d36745487b4eeba2630ea47322a95237a46e6654ddf4`, SHA del informe `3d2d4c6e623d879276d4cf75589d22f4fd207ef1c71aa4ed90e18559e8792f94`.
- Etapa 7, artifact **14716249154**, ZIP SHA-256 `f393d2311acb10847149b4154d97a5a06b4a967c83d084d6ca0052cbdf95b9ac`, SHA del informe `200311671a5c117af7f1a220fbe6f1dbcba3a40e7bd3255315b289c0fca23dee`.

## Causas exactas observadas

**Etapa 6 — `two_speakers_ask_sara`**: Fuente `\N[5]「サラが鍵を持っています。」\r\n\N[3]「では、トムではなくサラに聞きましょう。」`. Modelo, modo documento: «Sara tiene la llave. Entonces, pidámosle a Sara en lugar de Tom.» Rechazado por `ASK_ACTION_MISSING`: `pedirle` se aproxima a solicitar algo, pero el japonés `聞きましょう` especifica preguntar; con la llave en contexto, la paráfrasis necesita juicio bilingüe, NO homologación automática. En dos modos segmentados el modelo alternó entre «Sara» y «Sarah» y fue rechazado correctamente por inconsistencia.

**Etapa 7 — `torch_bridge_order`**: La primera propuesta reemplaza `たいまつ` (antorcha) por «vela», un cambio real de objeto. La segunda conserva «antorcha» pero termina «lo enciende», con pronombre masculino que no concuerda; el detector anterior además desconocía la forma irregular `enciende`, creando un rechazo por razón incompleta. La tercera propuesta pluralizó «antorchas» y también cambió el pronombre. Ninguna de esas salidas históricas se aprobó arbitrariamente.

**Etapa 7 — `nobody_saw_mika_depart`**: Las salidas «nadie la ha visto salir» y «nadie la vio salir» preservan el sentido. La rúbrica pedía aparte la palabra «no», ignorando que «nadie» como sujeto ya expresa la negación; rechazo falso claramente demostrado.

**Fallo nuevo descubierto entre los diez casos anteriormente aceptados en la etapa 7**: `medicine_variable_strict_gt` produjo «\V[2] es mayor que 1 solo si utilice un medicamento. De lo contrario, no lo utilice.» Esta formulación invierte la implicación. El japonés dice usar el medicamento **solamente cuando** se cumple la condición; la antigua rúbrica v1 no detectaba la inversión. Se añadió una prueba negativa que la reconoce. **Por esto, incluso el 10/12 histórico no prueba 10 traducciones lingüísticamente correctas**.

## Corrección real, sin manipular salidas

Commit [573835a6b68911461769d03e4b98a00fa9499622](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/commit/573835a6b68911461769d03e4b98a00fa9499622):
- Prompt general **v4 `uniform_dialogue_roles_condition_direction_v4`**: instruye distinguir preguntar de pedir, conservar objeto y concordancia, no invertir antecedente/consecuencia de condicionales, preservar sujeto negativo y nombres.
- Rúbrica etapa 7: detecta verbo irregular `enciende`, reconoce sujeto negativo `nadie`, bloquea pronombre masculino para una `antorcha` femenina y detecta la inversión `variable>1 solo si se usa el medicamento`.
- Se añadieron pruebas de regresión positivas y adversariales. Se conservan todas las fuentes japonesas congeladas y nunca se añade texto de respuesta a la inferencia.
- Pruebas de ingeniería [44931094531](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44931094531) y [44931101336](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44931101336): **SUCCESS** en Ubuntu y Windows.
- Nuevas inferencias originales en [etapa 6, 44931094612](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44931094612) y [etapa 7, 44931094546](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44931094546): en progreso al finalizar este documento; NO anunciar resultados hasta ver recibos finales y reinicio.

## Investigación posterior: etapa 8

El commit [b8be36ae949c3f74f0996d091bf5747a6e0a00d1](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/commit/b8be36ae949c3f74f0996d091bf5747a6e0a00d1) creó 12 nuevas fuentes japonesas, distintas de todos los corpus anteriores, únicamente con riesgos/source strings; no hay respuestas españolas suministradas al modelo. Runner, tests y workflow separados: `tools/stage8_dialogue_cases.py`, `tools/stage8_dialogue_neural_research.py`, `tests/test_stage8_dialogue_neural_research.py`, `.github/workflows/stage8-dialogue-neural-research.yml`.

- [Etapa 8, ejecución 44931420612](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44931420612): inferencia real en progreso; no atribuir puntuación.
- [CI 44931420549](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44931420549) y [44931425046](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44931425046): **SUCCESS** para el código en Ubuntu/Windows.
- **Es investigación sintética inédita, NO una evaluación verdaderamente ciega y externa**, y no tiene revisión humana acreditada. Los riesgos de la rúbrica automática deben auditarse aun si GitHub marca verde.

## Siguiente decisión obligatoria

1. Inspeccionar los reportes originales y el artefacto de las nuevas ejecuciones 6, 7 y 8; no inferir las puntuaciones desde el estado de CI.
2. Revisar por separado agente, destinatario, condicional, negación y gramática, y verificar hashes/manifest y persistencia SQLite tras reinicio. Si algún caso falla, conservar su rechazo y el modelo original sin alterarlo.
3. Exigir **revisión bilingüe independiente** antes de declarar calidad profesional o fusionar el PR. El checkpoint de etapa 5 `checkpoint/stage5-validated-20261121` sigue disponible. `main` no debe modificarse mientras los bloqueos persistan.
