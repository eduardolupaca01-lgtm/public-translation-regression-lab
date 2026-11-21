# Etapas 8, 9 y 10 — revisión de traducción JA → ES-419

Investigación exclusiva en eduardolupaca01-lgtm/public-translation-regression-lab, PR #4, rama experimental. La rama main no debe modificarse hasta que la evidencia cumpla los criterios. Fecha del diagnóstico: 21 de noviembre de 2026.

## Comprobantes originales (sin modificaciones)

- Etapa 6, run 44931094612: 16/16 por rúbrica; caché SQLite y reinicio en PASS; revisión humana pendiente.
- Etapa 7, run 44931094546: 12/12 por rúbrica; caché SQLite y reinicio en PASS, pero una traducción del medicamento expresa que la variable es mayor que uno solo si se usa la medicina; invierte la lógica japonesa. El control posterior debe rechazarla.
- Etapa 8, run 44931420612: 9/12 por rúbrica, tres rechazadas; caché y reinicio en PASS. El plural «domingos» y los límites «4 o menos» y «5 o más» son traducciones válidas rechazadas por reglas rígidas. El nombre Hana fue cambiado por Han o Hanako: error real de traducción que exige una nueva inferencia.

Los artefactos originales conservan fuente japonesa, traducciones españolas, modos, resultados y su manifiesto. No se crean traducciones españolas de referencia para influir la nueva generación y no se reescriben salidas fallidas para aprobar.

## Corrección focalizada

Commit fb4b331c4ce9ccc863816d785bcf76a2cea36575:
- Etapa 7 reconoce nuevas conjugaciones para detectar «solo si se usa» con antecedente y consecuente invertidos.
- Etapa 8 reconoce «domingos», límites inclusivos naturales y permiso «está bien abrir», pero rechaza intercambios entre prohibición y permiso.
- Etapa 8 usa una instrucción adicional uniforme de fidelidad de nombres propios, agentes y perspectiva temporal, sin ejemplos de respuestas ni correcciones posteriores a la inferencia.
- Se agregan pruebas positivas y adversariales.

Estos cambios constituyen correcciones de código, no una aprobación de los textos ni un resultado final de la nueva inferencia. Debido a que se ajustó la generación después de observar el fallo, este corpus es ya un conjunto de desarrollo calibrado, no una prueba ciega nueva.

## Etapa 9 — Paquete preparado; revisión humana independiente aún pendiente

El módulo tools/stage9_bilingual_review.py lee los tres artefactos originales y produce 40 fichas con las fuentes, traducciones, intentos, hashes, etiquetas de revisión actuales y criterios individuales para fidelidad, gramática, naturalidad del español latinoamericano y códigos de control. En todas las fichas human_decision queda en pending y reviewer queda vacío. Un detector no equivale a una persona bilingüe.

Puntos que requieren atención especial: inversión de medicamento en etapa 7; nombres y tiempos en etapa 8; expresiones «Todos están buscando a él» y «en lugar de el jueves» de etapa 6; matiz de permiso pasado frente a posibilidad contrafactual. Es obligatoria la revisión humana de los 40 casos y un segundo conjunto externo realmente ciego antes de afirmar calidad generalizable.

## Etapa 10 — Validación e integración condicionada

El módulo tools/stage10_release_gate.py comprueba inferencia verdadera, puntuación exigida en cada etapa, persistencia y reinicio, ausencia de correcciones de destino, huellas SHA-256 originales, nueva revisión semántica y las decisiones de revisión humana. La nueva revisión detecta si una aceptación histórica ya no pasa la rúbrica corregida; no da por buena una traducción solo por el estado success de GitHub.

El workflow .github/workflows/stage9-stage10-quality-gate.yml descarga recibos originales, ejecuta el guard de publicación y las pruebas en Ubuntu, genera las 40 fichas y ejecuta una puerta de integración estricta. Produce documentos incluso si la etapa 10 queda bloqueada, y nunca ejecuta merge o publicación.

Los inputs stage6_run, stage7_run y stage8_run permiten repetir la auditoría con IDs de nuevas ejecuciones. Los defaults apuntan a las tres ejecuciones históricas, de modo que la puerta final debe indicar HOLD inicialmente.

## Pendientes que impiden declarar finalizado

1. Obtener una inferencia de etapa 7 que pase la rúbrica corregida, sin inversión de condiciones, y auditarla lingüísticamente.
2. Obtener una inferencia de etapa 8 aceptable por la rúbrica corregida, sin cambiar nombres, agentes, condiciones ni cantidades.
3. Ejecutar y registrar revisión bilingüe humana real e independiente de los 40 casos y evaluación nueva externa/ciega.
4. Repetir comprobaciones técnicas de seguridad, regresión, caché, reinicio y verificar la rama principal antes de considerar la fusión manual del PR #4.

Estado: ingeniería de revisión y gate implementada; integración bloqueada por criterios de calidad pendientes. Ninguna nota de esta investigación constituye autorización de publicación.
