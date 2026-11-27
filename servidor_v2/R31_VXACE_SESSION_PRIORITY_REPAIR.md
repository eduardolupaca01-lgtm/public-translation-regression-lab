# R31 — corrección de prioridad entre sesión y arranque

Las ejecuciones 45921893792 (Ubuntu y Windows) y 45921893838 fallaron en el contrato Ruby con "Japanese first paint unchanged". Los registros verifican que Go, MV/MZ, Python y Rust habían aprobado en la matriz de integración. No se alcanzó el nuevo preflight de arranque nativo ni la inferencia real.

Causa de esta regresión: la comprobación launch_failed? se ejecutaba antes de comprobar una sesión válida o recibir su respuesta. El fixture de contrato ya dispone de una sesión ligada al PID actual, pero no contiene un helper real; el intento redundante de lanzamiento registró un error y la puerta de primer dibujo entregó el original.

La revisión E acepta la sesión existente antes de lanzar un proceso adicional, consume las respuestas antes de evaluar errores históricos y conserva el original cuando realmente no hay una sesión válida. Mantiene el plazo de espera y no altera OPUS, los controles de calidad ni MV/MZ. Las regresiones prueban el error de arranque obsoleto, un PID ajeno y el vencimiento idempotente. El contrato Ruby se ejecuta antes de las regresiones largas. La aceptación con OPUS y el cifrado siguen siendo obligatorios.

La reparación del timeout de la ejecución 45920228512 todavía depende del preflight de arranque real y de la aceptación de la nueva compilación; no se presenta como certificada por el contrato sintético.
