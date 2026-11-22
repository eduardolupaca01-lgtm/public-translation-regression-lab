# TENSHIXGAME RPG: owner-only, disposable Windows TX772-to-TX775 upgrade acceptance.
# Never upload decrypted applications, V95 weights, game content or secrets.
# This tests the EXACT previous encrypted EXE against the newly rebuilt EXE,
# not two copies of the same source or a simulated installer.
param(
    [Parameter(Mandatory=$true)][long]$PreviousRun,
    [Parameter(Mandatory=$true)][long]$UpdatedRun
)
$ErrorActionPreference="Stop"
$repository="eduardolupaca01-lgtm/public-translation-regression-lab"
$prevName="Eduardo-Tenshixgame-RPG-ORIGINAL-TX772-PORTABLE-V95-Windows-TEST-ENCRYPTED"
$newName="Eduardo-TENSHIXGAME-TX775-V95-NOMBRES-PORTABLE-Windows-ENCRYPTED"
$root=Join-Path $env:RUNNER_TEMP "tx775-owner-upgrade-qa"
$oldDir=Join-Path $root "old"
$newDir=Join-Path $root "new"
$oldExtract=Join-Path $root "old-decoded"
$newExtract=Join-Path $root "new-decoded"
foreach($dir in @($root,$oldDir,$newDir,$oldExtract,$newExtract)){
  New-Item -Path $dir -ItemType Directory -Force | Out-Null
}
if(-not $env:GH_TOKEN){throw "TX775_ACTIONS_READ_TOKEN_REQUIRED"}
if(-not $env:EDUARDO_RPG_ARCHIVE_PASSWORD -or $env:EDUARDO_RPG_ARCHIVE_PASSWORD.Length -lt 20){
  throw "TX775_ARCHIVE_OWNER_PASSWORD_REQUIRED"
}
gh run download $PreviousRun --repo $repository --name $prevName --dir $oldDir 1>$null
if($LASTEXITCODE -ne 0){throw "TX775_PREVIOUS_SIGNED_ARTIFACT_UNAVAILABLE"}
gh run download $UpdatedRun --repo $repository --name $newName --dir $newDir 1>$null
if($LASTEXITCODE -ne 0){throw "TX775_UPDATED_SIGNED_ARTIFACT_UNAVAILABLE"}
$seven=Get-Command 7z.exe -ErrorAction SilentlyContinue
if($null -ne $seven){$sevenExe=$seven.Source}
elseif(Test-Path "C:\Program Files\7-Zip\7z.exe"){$sevenExe="C:\Program Files\7-Zip\7z.exe"}
else{throw "TX775_SEVEN_ZIP_NOT_AVAILABLE"}
$oldEncrypted=Join-Path $oldDir "Tenshixgame-RPG-TX772-PORTATIL-V95-PRUEBA.7z"
$newEncrypted=Join-Path $newDir "Tenshixgame-RPG-TX775-NOMBRES-V95-PRUEBA.7z"
foreach($file in @($oldEncrypted,$newEncrypted)){
  if(-not (Test-Path -LiteralPath $file -PathType Leaf)){throw "TX775_EXPECTED_AES_ARCHIVE_NOT_FOUND"}
}
# Check the exact SHA receipts before opening an owner-protected archive.
# No decrypted EXE, source, token or game text reaches public CI artifacts.
foreach($pair in @(
    @{ file=$oldEncrypted; dir=$oldDir },
    @{ file=$newEncrypted; dir=$newDir }
)){
  $receiptPath=Join-Path $pair.dir "SHA256.txt"
  if(-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
    throw "TX775_SOURCE_SHA256_RECEIPT_MISSING"
  }
  $digestLine=(Get-Content -LiteralPath $receiptPath -TotalCount 1).Trim()
  if($digestLine -notmatch '^([a-f0-9]{64})\\s+') {
    throw "TX775_SOURCE_SHA256_RECEIPT_INVALID"
  }
  $expected=$Matches[1]
  $actual=(Get-FileHash -LiteralPath $pair.file -Algorithm SHA256).Hash.ToLowerInvariant()
  if($actual -ne $expected) {throw "TX775_ENCRYPTED_ARCHIVE_SHA256_MISMATCH"}
}
Write-Host "TX775_BOTH_OWNER_ARCHIVES_MATCH_BUILD_RECEIPTS"
$pass="-p"+$env:EDUARDO_RPG_ARCHIVE_PASSWORD
& $sevenExe x "-o$oldExtract" -y $pass $oldEncrypted 1>$null
if($LASTEXITCODE -ne 0){throw "TX775_PREVIOUS_ARCHIVE_INTEGRITY_FAILED"}
& $sevenExe x "-o$newExtract" -y $pass $newEncrypted 1>$null
if($LASTEXITCODE -ne 0){throw "TX775_UPDATED_ARCHIVE_INTEGRITY_FAILED"}
$oldExe=Join-Path $oldExtract "Tenshixgame-RPG.exe"
$newExe=Join-Path $newExtract "Tenshixgame-RPG.exe"
foreach($exe in @($oldExe,$newExe)){
  if(-not (Test-Path -LiteralPath $exe -PathType Leaf) -or (Get-Item $exe).Length -lt 600000000){
    throw "TX775_ORIGINAL_MODEL_ONEFILE_REQUIRED"
  }
}
if((Get-FileHash -LiteralPath $oldExe -Algorithm SHA256).Hash -eq
   (Get-FileHash -LiteralPath $newExe -Algorithm SHA256).Hash){
  throw "TX775_NEW_EXE_SAME_BINARY_AS_PREVIOUS"
}
Write-Host "TX775_OWNER_TWO_DISTINCT_REAL_WINDOWS_EXES_VERIFIED"
$globalProfile=Join-Path $root "unrelated-profile"
New-Item -Path $globalProfile -ItemType Directory -Force | Out-Null
$env:LOCALAPPDATA=$globalProfile
$game=Join-Path $root "GameCopy"
$gameData=Join-Path $game "www\data"
$gameJS=Join-Path $game "www\js"
New-Item -Path $gameData,$gameJS -ItemType Directory -Force | Out-Null
$gameEXE=Join-Path $game "Game.exe"
[System.IO.File]::WriteAllBytes($gameEXE,[byte[]]@(77,90,0,0))
[System.IO.File]::WriteAllText((Join-Path $gameData "System.json"),"{}",[System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText((Join-Path $gameJS "plugins.js"),'var $plugins = [];',[System.Text.Encoding]::UTF8)
$originalGameSHA=(Get-FileHash -LiteralPath $gameEXE -Algorithm SHA256).Hash
$originalRegistrySHA=(Get-FileHash -LiteralPath (Join-Path $gameJS "plugins.js") -Algorithm SHA256).Hash
function Invoke-PortableSmoke($file,$selection,$name) {
  $env:TX771_PORTABLE_GAME_EXE=$selection
  $env:TX541_RPG_DIAGNOSTIC_FILE=Join-Path $root ($name+".diagnostics.txt")
  $stdout=Join-Path $root ($name+".stdout.txt")
  $stderr=Join-Path $root ($name+".stderr.txt")
  $process=Start-Process -FilePath $file -ArgumentList "--rpg-onefile-portable-smoke" -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr -ErrorAction Stop
  if($null -eq $process -or $process.ExitCode -ne 0){
    # Logs remain on the ephemeral Windows runner; never disclose paths or text.
    throw ("TX775_"+$name.ToUpperInvariant()+"_ONEFILE_EXIT_NONZERO")
  }
}
Invoke-PortableSmoke $oldExe $gameEXE "original"
$sidecar=Join-Path $game "Tenshixgame-IA"
$oldMarker=Join-Path $sidecar "portable-owner-v1.json"
$oldWorker=Join-Path $sidecar ".local\TENSHIXGAME-RPG\engine\engine\TenshixgameAI.exe"
if(-not (Test-Path -LiteralPath $oldMarker) -or -not (Test-Path -LiteralPath $oldWorker)){
  throw "TX775_PREVIOUS_ORIGINAL_SIDECAR_NOT_PREPARED"
}
$oldInfo=Get-Content -LiteralPath $oldMarker -Raw | ConvertFrom-Json
$oldWorkerSHA=(Get-FileHash -LiteralPath $oldWorker -Algorithm SHA256).Hash.ToLowerInvariant()
if($oldInfo.worker_sha256 -ne $oldWorkerSHA){throw "TX775_PREVIOUS_WORKER_MARKER_NOT_VERIFIED"}
$apps=Join-Path $sidecar "App"
if(-not (Test-Path -LiteralPath $apps -PathType Container)) {
  throw "TX775_PREVIOUS_APP_DIRECTORY_MISSING"
}
$priorApps=@(Get-ChildItem -LiteralPath $apps -Directory -ErrorAction Stop | ForEach-Object {$_.Name})
if($priorApps.Count -lt 1){throw "TX775_PREVIOUS_VERIFIED_APP_MISSING"}
$cache=Join-Path $sidecar ".local\TENSHIXGAME-RPG\live-cache"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$sentinel=Join-Path $cache "owner-test-cache.keep"
[System.IO.File]::WriteAllText($sentinel,"TX775_UNMODIFIED_TRANSLATION_CACHE",[System.Text.Encoding]::UTF8)
Invoke-PortableSmoke $newExe $gameEXE "upgraded"
$newInfo=Get-Content -LiteralPath $oldMarker -Raw | ConvertFrom-Json
$newWorkerSHA=(Get-FileHash -LiteralPath $oldWorker -Algorithm SHA256).Hash.ToLowerInvariant()
if($newInfo.worker_sha256 -ne $newWorkerSHA){throw "TX775_UPDATED_MODEL_MARKER_MISMATCH"}
foreach($app in $priorApps){
  if(-not (Test-Path -LiteralPath (Join-Path $apps $app) -PathType Container)){
    throw "TX775_PREVIOUS_APP_REMOVED_DURING_UPGRADE"
  }
}
if((Get-Content -LiteralPath $sentinel -Raw) -ne "TX775_UNMODIFIED_TRANSLATION_CACHE"){
  throw "TX775_GAME_CACHE_DID_NOT_SURVIVE_UPGRADE"
}
if((Get-FileHash -LiteralPath $gameEXE -Algorithm SHA256).Hash -ne $originalGameSHA){
  throw "TX775_GAME_EXE_WAS_MODIFIED"
}
if((Get-FileHash -LiteralPath (Join-Path $gameJS "plugins.js") -Algorithm SHA256).Hash -ne $originalRegistrySHA){
  throw "TX775_GAME_PLUGIN_REGISTRY_WAS_MODIFIED"
}
if(Test-Path -LiteralPath (Join-Path $globalProfile "TENSHIXGAME-RPG")){
  throw "TX775_GLOBAL_WINDOWS_PROFILE_RECEIVED_PORTABLE_ENGINE"
}
# Prove restart after update without rewriting the accepted cache.
Invoke-PortableSmoke $newExe $gameEXE "restart"
if((Get-Content -LiteralPath $sentinel -Raw) -ne "TX775_UNMODIFIED_TRANSLATION_CACHE"){
  throw "TX775_GAME_CACHE_LOST_ON_RESTART"
}
# Same-volume folder move after the two EXEs exit. Windows refuses this if a
# lingering worker or GUI retains open handles to the game's files.
$relocated=Join-Path $root "GameCopy-relocated"
Move-Item -LiteralPath $game -Destination $relocated -ErrorAction Stop
$relocatedEXE=Join-Path $relocated "Game.exe"
Invoke-PortableSmoke $newExe $relocatedEXE "relocated"
$relocatedWorker=Join-Path $relocated "Tenshixgame-IA\.local\TENSHIXGAME-RPG\engine\engine\TenshixgameAI.exe"
$relocatedMarker=Join-Path $relocated "Tenshixgame-IA\portable-owner-v1.json"
$relocatedInfo=Get-Content -LiteralPath $relocatedMarker -Raw | ConvertFrom-Json
if($relocatedInfo.worker_sha256 -ne (Get-FileHash -LiteralPath $relocatedWorker -Algorithm SHA256).Hash.ToLowerInvariant()){
  throw "TX775_PORTABLE_WORKER_DRIFT_AFTER_GAME_MOVE"
}
if((Get-Content -LiteralPath (Join-Path $relocated "Tenshixgame-IA\.local\TENSHIXGAME-RPG\live-cache\owner-test-cache.keep") -Raw) -ne "TX775_UNMODIFIED_TRANSLATION_CACHE"){
  throw "TX775_CACHE_NOT_RELOCATABLE_WITH_GAME"
}
if(Test-Path -LiteralPath (Join-Path $globalProfile "TENSHIXGAME-RPG")){
  throw "TX775_RELOCATED_GAME_CREATED_GLOBAL_ENGINE"
}
Write-Host "TX775_REAL_TX775_TO_TX775_UPGRADE_RESTART_RELOCATION_CACHE_AND_LOCAL_DISK_PASS"

