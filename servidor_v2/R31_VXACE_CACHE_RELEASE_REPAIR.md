# R31 — cierre de SQLite y aceptación Windows

Evidencia: 45922575890 aprobó la matriz Ubuntu/Windows. 45922575830, job 140256468194, aprobó el arranque, la inferencia OPUS auténtica y los recorridos de instalación/restauración suelto y empaquetado; el fallo se produjo al salir de TemporaryDirectory por WinError 32 en translation-memory-v2.sqlite3.

El lector QA usaba "with sqlite3.connect": ese context manager no cierra la conexión. Se corrige con closing y apertura de solo lectura. También se separa la parada del transporte IPC del retiro del descriptor: el servicio VX Ace debe drenar los transportes y cerrar SQLite antes de retirar la sesión. Los hilos HTTP de VX Ace son joinables, con límite de lectura local.

La aceptación observa el handle del trabajador mientras Ruby sigue vivo, espera su salida limpia y comprueba la apertura exclusiva de SQLite y del archivo lock. El workspace se elimina normalmente, sin ignorar errores. La prueba de regresión mantiene referencias a las conexiones para impedir que el recolector oculte una fuga, y comprueba tanto éxito como excepción.

No se cambian los pesos, el protocolo de traducción, los plugins MV/MZ ni los archivos de juegos reales. El contrato Ruby de escritorio con fixtures no equivale a ejecutar RGSS301.dll en un juego real; se mantiene esa limitación en la etiqueta de entrega.
