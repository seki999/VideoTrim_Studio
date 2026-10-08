param([string]$FFmpegDir = "", [switch]$SkipFFmpeg, [string]$PythonPath = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = if ($PythonPath) { $PythonPath } else { Join-Path $PSScriptRoot ".venv\Scripts\python.exe" }
if (!(Test-Path -LiteralPath $pythonExe)) { throw "请先创建 .venv 并安装 requirements-build.txt" }
$arguments = @("-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir", "--name", "VideoTrimStudio", "--copy-metadata", "PySide6", "--copy-metadata", "PySide6_Essentials", "--copy-metadata", "PySide6_Addons", "--copy-metadata", "shiboken6", "--copy-metadata", "psutil")
if (!$SkipFFmpeg) {
    if (!$FFmpegDir) { $FFmpegDir = Join-Path $PSScriptRoot "assets\ffmpeg" }
    foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
        $binaryPath = Join-Path $FFmpegDir $name
        if (!(Test-Path -LiteralPath $binaryPath)) { throw "缺少 $binaryPath；指定 -FFmpegDir 或 -SkipFFmpeg" }
        $arguments += @("--add-binary", "$binaryPath;assets\ffmpeg")
    }
    $licensePath = Join-Path $FFmpegDir "licenses"
    if (!(Test-Path -LiteralPath $licensePath)) { throw "打包 FFmpeg 前请准备 licenses 目录，含许可证、对应源码或合法源码提供说明、构建配置" }
    $arguments += @("--add-data", "$licensePath;licenses\ffmpeg")
}
$arguments += @("--add-data", "README.md;.", "main.py")
$originalSearchPath = $env:PATH
try {
    # Avoid collecting unrelated Qt/ICU DLLs from tools such as Poppler on PATH.
    # PyInstaller's Qt hooks add the selected PySide6 wheel's own DLL directories.
    $env:PATH = @((Split-Path -Parent (Resolve-Path -LiteralPath $pythonExe)), "$env:SystemRoot\System32", $env:SystemRoot) -join ';'
    & $pythonExe @arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }
} finally { $env:PATH = $originalSearchPath }
Write-Host "完成：dist\VideoTrimStudio\VideoTrimStudio.exe（请分发整个目录）"
