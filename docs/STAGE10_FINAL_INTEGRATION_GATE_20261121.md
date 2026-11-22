# Etapa 10 — control técnico final de integración y revisión independiente

## Recibos originales inmutables

- Etapa 6: run 44931094612, 16/16 de rúbrica automática y SQLite PASS.
- Etapa 7: run 44942504944, 12/12 de rúbrica automática y SQLite PASS.
- Etapa 8: run 44961618206, 12/12 de rúbrica automática v4 y SQLite PASS.
- Etapa 9: run 44965198361, 40 expedientes preparados, 10 alertas de redacción, cero dictámenes humanos aprobados.
- Artefacto de etapa 9: https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44965198361/artifacts/14730957025

Estas pruebas usan textos japoneses sintéticos públicos; no equivalen a una evaluación ciega externa ni a una validación profesional de español latinoamericano.

## Trabajo técnico de la etapa 10

El flujo Stage10 final integration technical preflight descarga los cuatro artefactos originales desde GitHub, verifica recuentos, semántica, SQLite después del reinicio y la correspondencia exacta de 40 pares JA/ES-419 con el material de entrada. Una sustitución del japonés, de la traducción, de los intentos originales, de la rúbrica, de un hash o de un identificador produce HOLD y fallo de preflight. El informe se adjunta a la ejecución.

Esta prevalidación puede acabar correctamente mientras su dictamen interno sea HOLD: así distingue una preparación técnica satisfactoria de la falta real de aprobación humana. Nunca se realiza merge ni publicación automática.

La puerta estricta manual se ejecuta desde .github/workflows/stage9-stage10-quality-gate.yml. Si existe reviews/stage9-independent-reviewed-packet.json, utiliza ese archivo redactado por la persona revisora; si no existe, toma la copia pendiente original de la etapa 9. Además obtiene el estado real de las revisiones de GitHub. Con --require-ready devuelve error si cualquiera de los criterios permanece sin satisfacer. Solo READY_FOR_MANUAL_PR_REVIEW habilita la consideración de una revisión manual adicional; no realiza merge.

## Procedimiento de aprobación bilingüe externa

1. Descargue stage9-bilingual-review-packet.json desde el artefacto de la etapa 9. Revise las 40 parejas japonés/español. No altere los campos que describen la fuente, traducción o procedencia del modelo.
2. Para cada pareja, anote su nombre público de GitHub en reviewer. Solo tras comprobar la fidelidad, gramática, naturalidad ES-419 y códigos RPG, marque human_fidelity, human_grammar, human_naturalness_es_419, human_rpg_codes y human_decision como approved. Documente en notes la evaluación de todos los casos alertados. No firme una traducción que considere incorrecta.
3. Si detecta errores reales, proponga una corrección en la generación y una nueva evaluación. No cambie los recibos históricos, no reemplace una salida antes de computar la rúbrica y no firme el conjunto como completo.
4. Una vez comprobados legítimamente todos los casos, indique human_review_completed=true y human_review_approved=true y agregue reviewer_attestation como objeto que contenga reviewer_github_login, reviewed_at_utc (ISO 8601 con zona horaria), independent_bilingual_review_confirmed=true, source_run_ids_by_stage y evidence_report_sha256_by_stage. Copie los dos últimos mapas idénticos a los del paquete original.
5. Guarde el JSON sin cambios de evidencia como reviews/stage9-independent-reviewed-packet.json en la rama experimental. La persona revisora independiente del propietario deberá aprobar el último SHA de PR #4 en GitHub. Una aprobación de otro commit no sirve.
6. Ejecute manualmente la puerta estricta de Stage10 en la rama experimental. Si todas las verificaciones pasan, el resultado es READY_FOR_MANUAL_PR_REVIEW; un responsable deberá decidir por separado si fusiona el PR.

## Estado de seguridad

El PR #4 sigue en borrador. La rama main no se modifica. La ausencia de un revisor bilingüe humano independiente y de su aprobación verificable mantiene el estado HOLD.
