@echo off
setlocal
cd /d "%~dp0"
echo R43 - Diagnostico de RPG Maker XP real
echo Selecciona un Game.exe original y confiable de RPG Maker XP.
echo No se instalara nada en el juego elegido.
echo Se usara una copia temporal aislada con scripts de prueba.
set "GAME="
set /p "GAME=Ruta completa a Game.exe (arrastra el archivo aqui): "
set "GAME=%GAME:"=%"
if not defined GAME exit /b 1
if not exist "%GAME%" (
 echo No se encontro Game.exe.
 pause
 exit /b 1
)
start "" /wait "%~dp0Servidor.exe" --xp-native-probe --game "%GAME%" >"%~dp0R43-Diagnostico.txt" 2>&1
set "RC=%ERRORLEVEL%"
echo Codigo de salida: %RC%>>"%~dp0R43-Diagnostico.txt"
type "%~dp0R43-Diagnostico.txt"
echo Comparte solo R43-Diagnostico.txt, nunca los archivos del juego.
pause
exit /b %RC%
