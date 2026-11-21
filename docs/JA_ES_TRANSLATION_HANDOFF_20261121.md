# Continuidad técnica — traducción japonés → español latinoamericano
**Corte de evidencia: 21 de noviembre de 2026.** Documento de recuperación para una IA o un mantenedor que no conoce los chats anteriores. **Solo investigación pública del repositorio** `eduardolupaca01-lgtm/public-translation-regression-lab`.

## Cómo retomar sin contexto previo
1. Abrir [PR #4](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/pull/4) (**borrador, no fusionado**) y la rama de trabajo `experiment/qwen3-ja-es-candidate-20261120`.
2. Para recuperar el punto anterior a experimentos posteriores, usar la rama **inmutable por convención** `checkpoint/stage5-validated-20261121` que apunta a `f93646239e0c03829e801999a4bfe2302a8c99bc`. No desplazar ese checkpoint.
3. Revisar los GitHub Actions enumerados y sus *artifacts originales*. Las capturas y resultados automáticos no sustituyen una revisión bilingüe; los artifacts de Actions pueden caducar. Se entrega también una copia descargable del ZIP original de etapa 5 al usuario.
4. No fusionar automáticamente a `main` ni declarar calidad profesional. No usar respuestas españolas históricas para generar ni mejorar una evaluación supuestamente ciega.
5. Hacer cambios solo en la rama experimental, con pruebas de Windows y Ubuntu, controles de proveniencia, controles RPG y reinicio frío de SQLite.

## Resultados reales, diferenciados por alcance

| Etapa | Run GitHub Actions | Resultado confirmado | Alcance |
|---|---:|---|---|
| Desarrollo Qwen3-8B thinking | [44855395959](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44855395959) | 20/20 y persistencia PASS | Conjunto de desarrollo **público**, no ciego |
| Diálogos separados (etapa 3) | [44893774138](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44893774138) | 10/10 automático y reinicio PASS | Fallos lingüísticos detectados luego |
| Calibración uniforme (etapa 4) | [44908793937](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44908793937) | 10/10 automático y reinicio PASS, **workflow FAIL** | Auditoría semántica detectó error de concordancia; no promover |
| Diálogos RPG (etapa 4) | [44908983065](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44908983065) | 12/12 estructura y reinicio PASS | Auditoría posterior detectó inversión de papeles y género |
| Auditoría semántica RPG | [44912614307](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44912614307) | **BLOCKED** correctamente | Traducciones antiguas conservadas, no editadas |
| Auditoría cruzada 10+12 | [44912843721](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44912843721) | **SEMANTIC_BLOCKED** correctamente | El 10/10 y 12/12 no prueban calidad |
| Diálogos nuevos (etapa 5) | [44912933868](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44912933868) | **16/16 rúbrica automática; reinicio PASS** | Aún requiere revisión lingüística independiente |
| CI rama etapa 5 | [44912933864](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44912933864), [44912937912](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44912937912) | **SUCCESS** en Windows y Ubuntu | Pruebas del código, no calidad del modelo |

Los resultados más recientes de la etapa 5 provienen del commit `f93646239e0c03829e801999a4bfe2302a8c99bc` y artifact GitHub `14711492119` (`stage5-dialogue-sixteen-research-receipts`). En el informe: `rubric_accepted=16`, `rejected=0`, `professional_quality_approved=false`, `bilingual_review_required=true`; en la prueba de reinicio: `rubric_status=PASS`, `persistence_status=PASS`, `models_loaded_during_restart=false`. **No reinterpretar 16/16 como 16/16 de calidad profesional.**

### Evidencia reproducible etapa 5
- SHA-256 `stage5-neural-report.json`: `36eecad45ad63b63b2bc0c5274b95c39b836bbf056fe197538fa4ea6f9d5e267`.
- SHA-256 `stage5-source-manifest.json`: `0f9f603b045ddcd44c33757082d5e8e08ca4cb27270fa720062c3bc4075c4765`.
- SHA-256 `stage5-cold-restart-proof.json`: `fe50128d3c03776e76e30472ea7244d081c96f4cdd83490ea5b3a3a95444c191`.
- ZIP descargado desde GitHub, SHA-256 `d9474d348f59ac3490119e6b3d69c8aa813398ebff6521c02a225595453775cf`. El ZIP contiene salida sin editar, fuentes, SQLite, prueba y logs; el archivo local descargable no está almacenado automáticamente en GitHub fuera del artifact.

### Modelo y configuración fijada
`Qwen/Qwen3-8B-GGUF`, revisión `7c41481f57cb95916b40956ab2f0b139b296d974`, archivo `Qwen3-8B-Q4_K_M.gguf`, SHA-256 del peso `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`. Runtime llama.cpp `b12584`; `reasoning_mode=think`, `temperature=0.6`, `top_p=0.95`, `top_k=20`, `presence_penalty=1.5`, `seed=42`, `max_tokens=2048`, timeout HTTP CPU 720 s. Prompt uniforme v1: `uniform_spatial_agent_agreement_calibration_v1`, SHA-256 `4ca3d0f48f0a665f9f29ce831dfd028fb67e71a69dd016031572b7730accb67a`. Sin intervenciones caso por caso, sin reparaciones de salida, sin referencias españolas suministradas al generador.

## Errores comprobados que impiden promover a producción
- Etapa 3: se perdió `駅の前` (*frente a la estación*) en una salida; la calibración nueva ya resuelve esa frase concreta.
- Etapa 4 calibración: «pienso ir al parque juntos» persiste (concordancia singular/plural).
- Etapa 4 RPG: «devuélvelo» aplicado a «espada» (género) e inversión «no ha visto a nadie» frente a japonés «nadie lo ha visto» (agente y objeto).
- Etapa 5: la respuesta para `reception_code_zero` fue «La recepción se abrirá a las 8 de la mañana mañana.\r\n\\V[4] es 0 no podrá entrar.»: **falta una cláusula condicional explícita «Si ...»** y hay repetición antinatural de «mañana». Pasó la rúbrica automática v1, lo que evidencia una laguna del evaluador; los registros originales NO deben corregirse a mano.
- Etapa 5: `friday_to_monday` produjo «No es martes», entendible pero poco idiomático respecto de la reserva. `aoi_apple_explicit_green` conserva el color azul y luego dice que parece verde: requiere contexto narrativo, no corrección unilateral.

Estos hallazgos **no alteran** los resultados originales de tests de ingeniería. Son evidencia de que falta una revisión bilingüe real. La siguiente iteración debe abordar condicionales con códigos RPG, papeles gramaticales, omisión de sujetos, y naturalidad sin falsificar puntuaciones.

## Siguiente trabajo autorizado
1. Auditar las traducciones **reales** de etapa 5, añadir pruebas del evaluador contra traducciones aparentemente completas pero no fieles, conservando IDs y hashes de recibos originales.
2. Ejecutar etapa 6 con fuentes japonesas nuevas y distintas de los 20+10+12+16 anteriores; considerar diálogos de varios turnos, variables RPG, condicionales, pronombres y coherencia temporal. Las frases nuevas han de quedar congeladas antes de inferencia y sin referencias españolas dentro del prompt.
3. Guardar informes JSON, originales de inferencia, cola de revisión y comprobación de reinicio frío. Separar `structural`, `semantic-rubric` y `bilingual-human`.
4. Si falla un caso, conservar el rechazo y diagnosticar si fue modelo o validador; no reducir las exigencias para forzar 100 %.
5. **No hacer merge de PR #4 a main** hasta completar revisión de calidad, aprobación humana pertinente y CI sin fallos. La sugerencia de fusionar se atiende por ahora mediante checkpoint duradero y este documento; no confundir ahorro de avances con aprobación para uso general.

## Archivos y rutas principales
`tools/qwen3_8b_thinking_ja_es_candidate.py`, `tools/stage4_source_complete_candidate.py`, `tools/stage5_dialogue_cases.py`, `tools/stage5_dialogue_neural_research.py`, `tools/stage4_bilingual_audit.py`, `tools/stage4_rpg_semantic_audit.py`, `tests/test_stage5_dialogue_neural_research.py`, `.github/workflows/stage5-dialogue-neural-research.yml`. Los commits y comentarios previos de PR #4 conservan el historial de decisiones.

**Handoff:** una futura IA debe comenzar por ESTE documento, comprobar que los links todavía resuelven, confirmar el HEAD actual de la rama experimental y del PR y seguir solo a partir de datos comprobados. Los resultados publicados son investigación y no certificación.

## Actualización posterior al punto de corte: etapa 6 en ejecución

Se iniciaron **16 casos sintéticos japoneses totalmente nuevos**, distintos de los 20+10+12+16 anteriores, y una variante **uniforme v2** del mismo modelo fijado. El prompt general añade controles sobre condiciones `なら/たら/ば`, variables numéricas, género gramatical, papeles de agente/objeto y fechas relativas, **sin** suministrar respuestas españolas ni sustituir salidas. La rúbrica semántica v1 de la etapa 6 exige, entre otras cosas, condiciones explícitas al contrastar dos valores de variables, pronombres y objetos correctos, cronología, negaciones, precios y códigos RPG.

- Commit que lanzó la ejecución: `7b03df385ed33bee07bc284691103ff25e3c5eb6`.
- Ejecución de inferencia real: [44916744155](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44916744155).
- Archivos: `tools/stage6_dialogue_cases.py`, `tools/stage6_discourse_model.py`, `tools/stage6_dialogue_neural_research.py`, `tests/test_stage6_dialogue_neural_research.py`, `.github/workflows/stage6-dialogue-neural-research.yml`.
- Pruebas de regresión: [44916744061](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44916744061) y [44916750509](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44916750509), ejecución final a comprobar por quien retome.
- Al escribir esta entrada, la etapa 6 **estaba en curso**. No afirmar `16/16` ni `PASS` hasta verificar los registros finales, el `stage6-neural-report.json`, las salidas originales y el `stage6-cold-restart-proof.json`. Si fallan casos, preservar su `review_queue` y sus salidas sin editarlas. El resultado más reciente probado sigue siendo 16/16 de la etapa 5, pero solo bajo su rúbrica automática.

**Regla de integración:** el respaldo de etapa 5 y este documento ya permiten continuidad sin chat. NO hay aprobación profesional ni autorización técnica segura para fusionar el candidato completo a `main` mientras persistan errores semánticos comprobados. Integrar **solo después** de evidencia lingüística más rigurosa y revisión humana.
