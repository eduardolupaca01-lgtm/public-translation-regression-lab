# TENSHIXGAME RPG TX776 — Cómo copiar el diagnóstico de una instalación

Este manual se aplica al nuevo panel de la compilación TX776. Solo se recomienda probarlo sobre una **COPIA** del juego, con Game.exe cerrado y la instalación anterior preservada. El botón COPIAR DIAGNÓSTICO PARA ENVIAR es un control de la interfaz Windows y no instala otra IA.

## Qué verás

En la zona **Estado de instalación y diagnóstico acumulado** aparecerán la hora UTC de la sesión y líneas con código de la etapa: TX776_VERIFICANDO_JUEGO, TX776_DETECTANDO_MOTOR, TX776_VERIFICANDO_BINARIOS, TX776_VERIFICANDO_MODELOS, TX776_IA_EN_CARPETA, TX776_PREPARANDO_COPIA, TX776_COPIANDO_MODELO, TX776_PUBLICACION_ATOMICA, TX776_REVISANDO_RESPALDO, TX776_PUENTE_VERIFICADO y TX776_INSTALACION_VERIFICADA, según el recorrido. Si el instalador falla, debe aparecer un código TX... que identifica la causa y una recomendación para no destruir el respaldo.

Los mensajes **no se borran** cuando llega un aviso de actividad o un error. El panel sigue respondiendo mientras el motor prepara archivos. La zona puede desplazarse verticalmente.

## Qué enviarme después de una prueba

1. Abre el instalador TX776, elige una copia del juego y pulsa instalar. No cambies el EXE ni los archivos de la carpeta durante la operación.
2. Si la instalación falla, no borres ni muevas el diario, el plugin, el respaldo, los archivos de traducción ni los modelos.
3. Pulsa **COPIAR DIAGNÓSTICO PARA ENVIAR**, disponible también durante la operación. Pega aquí el contenido copiado e indica si se pudo volver a abrir Game.exe.
4. Si la pantalla del EXE falla **antes de que aparezca este panel**, envía una captura del mensaje inicial y el código de error. Ese arranque pertenece a otra fase y aún no se integra en el panel interior.
5. Si un mensaje contiene una ubicación, token o contraseña que tú mismo escribiste fuera del informe, ocúltalo antes de compartirlo. El nuevo informe de TX776 usa códigos seguros y no incluye rutas personales por diseño.

Ejemplo ficticio de un resultado:

    TENSHIXGAME RPG — DIAGNÓSTICO DE INSTALACIÓN
    [TX776_VERIFICANDO_JUEGO] Comprobando el juego cerrado.
    [TX776_DETECTANDO_MOTOR] Inspeccionando la variante RPG.
    [TX776_VERIFICANDO_MODELOS] Comprobando el V95 original.
    [TX771_PORTABLE_MODELS_INVALID] Los modelos no superaron la verificación. No fuerces la instalación.

El ejemplo **no es una ejecución real**. El código concreto que envíes permitirá distinguir si faltaron pesos del modelo, si había un diario antiguo incompatible, si Windows impidió copiar o renombrar archivos o si el motor del juego no estaba certificado.

## Seguridad

- La IA, sus modelos, caché y traducciones deben residir en el mismo directorio del juego. Este diagnóstico por defecto se mantiene en memoria/ventana y solo se copia al portapapeles cuando haces clic.
- Un código de error NO da permiso para borrar directorios desconocidos, modificar una partida ni sobreescribir plugins de otras personas.
- TX776 registra el instalador interior. El bootstrap del EXE único, anterior a que exista la ventana, conserva un canal de errores propio que necesitará unificar de forma segura.
- Que CI haya aprobado no demuestra que tu juego haya mostrado traducciones en la ventana nativa; esa aceptación depende de las pruebas que hagas con la copia.
