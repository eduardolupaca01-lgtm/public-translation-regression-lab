# Servidor R31 candidato: integración VX Ace con OPUS

Base de integración: 9d439424, CI 45919128778 aprobado en Windows y Ubuntu. No se modifica la rama R30 estable.

## Transporte
RGSS3 embebido no puede depender de socket/json/digest del Ruby de escritorio. El helper Rust verifica manifiesto, recibo y hashes del trabajador, complemento y recurso instalado y lanza el trabajador existente sin consola. La comunicación por archivos usa una sesión ligada al PID padre, identificadores acotados, token de sesión y publicación atómica. Se mantiene la misma memoria SQLite, modelos OPUS, deduplicación y política de calidad. MV/MZ conservan HTTP.

## Presentación
El punto de integración es la ventana nativa de mensajes y elecciones. La espera se realiza en su fibra, no con sleep en el hilo de dibujo. Las elecciones que llegan mediante push no necesitan un setter. Se conserva el callback e índice. Los controles y datos originales se conservan. Los textos desplazables tienen una puerta independiente; F10 usa la tecla Win32 sólo con foco en el juego. No se dibujan subtítulos superpuestos.

## Evidencia
- Pruebas de protocolo con respuestas controladas, rechazo de token, deduplicación, rechazo de calidad y persistencia.
- Ruby de escritorio simula exclusivamente el contrato de ventanas; no es ejecución del motor RGSS3.
- Candidato Windows usa los pesos OPUS y la procedencia ya verificada por R30, instala recursos sintéticos sueltos y empaquetados, inspecciona el script insertado, prueba solicitudes reales, reapertura, partidas y restauración SHA-256. No ejecuta los PE de fixture.
- El artefacto, si pasa, se cifra con el mecanismo existente. No se publica un binario sin cifrar ni un release definitivo.
- Pendiente de aceptación RGSS301.dll real: instalación y arranque de un juego autorizado, APIs Win32 embebidas, F10 y visualización nativa. Menús y superficies personalizadas adicionales no quedan certificados por las pruebas de diálogos.
