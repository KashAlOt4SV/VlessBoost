# Extract official binaries locally; does not install or start a VPN.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'bin\amneziawg'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
$url = "https://github.com/amnezia-vpn/amneziawg-windows-client/releases/download/3.1.0/amneziawg-$arch-3.1.0.msi"
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ('veil-runtime-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir | Out-Null
$msi = Join-Path $tempDir 'amneziawg.msi'
Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $msi
$signature = Get-AuthenticodeSignature -LiteralPath $msi
if ($signature.Status -ne 'Valid') { throw 'Official AmneziaWG MSI signature verification failed' }
$extract = Join-Path $tempDir 'extracted'
$arguments = "/a `"$msi`" /qn TARGETDIR=`"$extract`""
$process = Start-Process msiexec.exe -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
if ($process.ExitCode -ne 0) { throw "MSI extraction failed: $($process.ExitCode)" }
$exe = Get-ChildItem -LiteralPath $extract -Recurse -Filter amneziawg.exe | Select-Object -First 1
if (-not $exe) { throw 'amneziawg.exe missing in MSI' }
Copy-Item -Path (Join-Path $exe.Directory.FullName '*') -Destination $runtime -Recurse -Force
Write-Host 'AmneziaWG 3.1 portable runtime ready in bin\amneziawg'
