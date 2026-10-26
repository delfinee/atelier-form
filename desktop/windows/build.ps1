param(
    [Parameter(Mandatory=$true)][string]$WebViewPackage,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$DemoOrigin = 'https://demo.maijiax.cn'
)
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$output = [IO.Path]::GetFullPath($OutputDirectory)
$package = [IO.Path]::GetFullPath($WebViewPackage)
$portable = Join-Path $output 'AtelierSeller-Windows-x64'
New-Item -ItemType Directory -Force $portable | Out-Null
$core = Join-Path $package 'lib\net462\Microsoft.Web.WebView2.Core.dll'
$forms = Join-Path $package 'lib\net462\Microsoft.Web.WebView2.WinForms.dll'
$iconArgument = @()
if (Test-Path (Join-Path $source 'seller.ico')) { $iconArgument = @('/win32icon:' + (Join-Path $source 'seller.ico')) }
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$portable\AtelierSeller.exe" `
    "/win32manifest:$source\app.manifest" @iconArgument /r:System.Windows.Forms.dll /r:System.Drawing.dll `
    /r:System.Web.Extensions.dll "/r:$core" "/r:$forms" "$source\SellerApp.cs"
if ($LASTEXITCODE -ne 0) { throw 'Client compilation failed.' }
Copy-Item -LiteralPath $core,$forms -Destination $portable -Force
Copy-Item -LiteralPath (Join-Path $package 'runtimes\win-x64\native\WebView2Loader.dll') -Destination $portable -Force
Copy-Item -LiteralPath (Join-Path $source 'AtelierSeller.exe.config') -Destination $portable -Force
Copy-Item -LiteralPath (Join-Path $source 'README.txt') -Destination $portable -Force
Copy-Item -LiteralPath (Join-Path $package 'LICENSE.txt') -Destination (Join-Path $portable 'WebView2-LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $package 'NOTICE.txt') -Destination (Join-Path $portable 'WebView2-NOTICE.txt') -Force
@{demoOrigin=$DemoOrigin.TrimEnd('/')} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $portable 'app-settings.json') -Encoding UTF8
'AtelierSeller 1.2.0 coursework en-US' | Set-Content -LiteralPath (Join-Path $portable '.atelier-seller')
& $compiler /nologo /target:exe /platform:x64 "/out:$portable\DesktopPolicyTests.exe" `
    "/r:$portable\AtelierSeller.exe" "$source\PolicyTests.cs"
if ($LASTEXITCODE -ne 0) { throw 'Policy test compilation failed.' }
& "$portable\DesktopPolicyTests.exe"
if ($LASTEXITCODE -ne 0) { throw 'Desktop policy checks failed.' }
Remove-Item -LiteralPath (Join-Path $portable 'DesktopPolicyTests.exe')
$zip = Join-Path $output 'AtelierSeller-Windows-x64.zip'
Compress-Archive -Path "$portable\*" -DestinationPath $zip -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Update)
try {
    if (-not $archive.GetEntry('.atelier-seller')) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, (Join-Path $portable '.atelier-seller'), '.atelier-seller') | Out-Null
    }
} finally { $archive.Dispose() }
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$output\AtelierSeller-Setup.exe" `
    "/win32manifest:$source\app.manifest" @iconArgument /r:System.Windows.Forms.dll /r:System.Drawing.dll `
    /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll "/resource:$zip,seller-payload.zip" "$source\Setup.cs"
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Get-Item -LiteralPath $zip,(Join-Path $output 'AtelierSeller-Setup.exe') | Select-Object Name,Length
