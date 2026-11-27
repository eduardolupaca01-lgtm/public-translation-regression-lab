param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = "Stop"
$Output=[IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path $Output | Out-Null
$project=Join-Path $PSScriptRoot "../webhost/Jugar-IA.csproj"
dotnet build $project -c Release -o $Output
if ($LASTEXITCODE -ne 0) { throw "IA_WEB_DESKTOP_BUILD_FAIL" }
$packages=$env:NUGET_PACKAGES
if ([string]::IsNullOrWhiteSpace($packages)) {$packages=Join-Path $env:USERPROFILE ".nuget/packages"}
$sdk=Join-Path $packages "microsoft.web.webview2/1.0.2903.40"
$loader=Join-Path $sdk "runtimes/win-x64/native/WebView2Loader.dll"
if (!(Test-Path -LiteralPath $loader -PathType Leaf)) {
  $loader=Join-Path $sdk "build/native/x64/WebView2Loader.dll"
}
if (!(Test-Path -LiteralPath $loader -PathType Leaf)) { throw "IA_WEB_DESKTOP_X64_LOADER_MISSING" }
Copy-Item -LiteralPath $loader -Destination (Join-Path $Output "WebView2Loader.dll") -Force
# Ship Microsoft's actual SDK license from the pinned NuGet package.
$license=Join-Path $sdk "LICENSE.txt"
if (!(Test-Path -LiteralPath $license -PathType Leaf)) {
  $spec=Get-ChildItem -LiteralPath $sdk -Filter "*.nuspec" -File | Select-Object -First 1
  if ($null -ne $spec) {
    [xml]$xml=Get-Content -LiteralPath $spec.FullName -Raw
    $node=$xml.SelectSingleNode("//*[local-name()='license' and @type='file']")
    if ($null -ne $node) {
      $license=Join-Path $sdk $node.InnerText
    }
  }
}
if (!(Test-Path -LiteralPath $license -PathType Leaf)) { throw "IA_WEB_DESKTOP_SDK_LICENSE_MISSING" }
Copy-Item -LiteralPath $license -Destination (Join-Path $Output "WebView2-LICENSE.txt") -Force
foreach ($name in @("Jugar-IA.exe","Jugar-IA.exe.config","Microsoft.Web.WebView2.Core.dll","Microsoft.Web.WebView2.WinForms.dll","WebView2Loader.dll","WebView2-LICENSE.txt")) {
  if (!(Test-Path -LiteralPath (Join-Path $Output $name) -PathType Leaf)) { throw "IA_WEB_DESKTOP_COMPONENT_MISSING_$name" }
}
Write-Host "IA_WEB_DESKTOP_HOST_COMPONENTS_READY"
