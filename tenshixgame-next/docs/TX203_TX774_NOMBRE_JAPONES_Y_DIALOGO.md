# TX203 → TX774 — texto japonés de nombres no es diálogo sin traducir

Auditoría read-only de la base SQLite extraída de las DOS partes del archivo RAR suministrado por el propietario. Fecha 22 de noviembre de 2026. No se publica la base ni las frases originales. Este informe solo contiene agregados.

## Conteos exactos del archivo analizado

- Tabla de segmentos: 6.664 registros.
- Estado done: 6.646 (6.645 JA→ES y 1 EN→ES).
- Estado retry: 18.
- Traducciones done con algún carácter japonés: 3.883.
- De esas 3.883, **3.874** contienen japonés únicamente en un control de nombre RPG inalterado de la forma barra-inversa-N<...>, no en el cuerpo que el jugador debe leer en español.
- **9** conservan japonés fuera de ese control; deben seguir rechazándose o revisándose.
- Todos los 4.450 resultados que contienen un control de nombre conservan exactamente sus etiquetas originales en esta base.
- Otros 2.763 resultados done no contienen caracteres japoneses.

**No** implica que los 3.874 registros hayan aparecido en pantalla. Solo evidencia que el filtro anterior que rechazaba cualquier japonés podía descartar traducciones con nombre japonés preservado. Las traducciones pueden además sufrir otros defectos semánticos, rotura de códigos, clave de caché o problemas de repintado.

## Causa y reparación propuesta

En el complemento original del V95 bajo el commit aeb9ff9326e418fbabe2d53dff7891f4fb340c37, la función de descarte hasUntranslatedJapanese se basaba en detectar japoneses simultáneamente en fuente y resultado. No diferenciaba nombres de control RPG conservados de diálogo sin traducir.

Herramienta pública **tools/tx774_name_control_quality.py**:
- Inspección de SQLite solo lectura, salida de conteos, sin mostrar frases.
- Comprueba controles de nombre idénticos en fuente y traducción; oculta SOLO ese control a efectos del filtro de calidad. No modifica ni retira etiquetas del texto final.
- Rechaza japonés restante fuera de las etiquetas, nombres alterados, nombres sin cuerpo y traducción japonesa sin convertir.
- Realiza pruebas de código Python y ejecuta el filtro JavaScript nuevo con Node.
- Solo puede aplicar el cambio a una copia temporal del código original si el commit de Git coincide exactamente con el SHA aprobado. No modifica el repositorio privado original.

## Lo que falta validar para usar en videojuego

1. Comprobar que TX774 pasa todos los controles originales del V95 y el adaptador MV/MZ.
2. Verificar que la caché y el modelo mantienen igual la identidad nativa de clave que TX757–TX771.
3. Probar un diálogo real con nombre japonés conservado y cuerpo español en la ventana nativa (sin superposición).
4. Verificar decisiones, elección activa, variables, segundo inicio y restauración.
5. Probar que una traducción parcialmente japonesa en el CUERPO sigue siendo rechazada y no provoca texto doble.

Esta evidencia corresponde a una base de prueba histórica; no extrapolar porcentajes a todos los juegos.
