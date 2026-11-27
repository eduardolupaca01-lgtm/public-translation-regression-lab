# R31 — reparación del arranque VX Ace

Evidencia: ejecución 45920228512, trabajo 140248924159. La compilación del paquete, la carga real de OPUS, las regresiones MV/MZ/CTE/Halva y la verificación del script insertado pasaron. La aceptación VX Ace terminó con IA_VXACE_VERIFIED_WORKER_BOOT_TIMEOUT. El código anterior ocultaba las causas de arranque, por lo que el log no demuestra un fallo interno concreto de OPUS.

Reparación: el helper deriva la raíz del juego de su propia ruta instalada, mantiene rutas nativas Unicode para lanzar el hijo, valida hashes y recibo como antes, y comunica únicamente códigos de diagnóstico. Se utiliza un argv explícito en Ruby. Se conserva la espera limitada y la memoria SQLite. La preprueba nativa utiliza un hijo de laboratorio que verifica argumentos y cwd; no simula una traducción ni se incluye en el paquete. El build real exige esa preprueba, luego prueba VX Ace con OPUS auténtico antes de las demás aceptaciones, que siguen siendo obligatorias. No se amplió el plazo de 180 segundos de la prueba fallida.

La aceptación de escritorio Ruby sigue sin equivaler al uso de RGSS301.dll real. No publicar si cualquiera de las puertas falla.
