$utf8 = [System.Text.UTF8Encoding]::new($false)

[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$global:OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

try {
    chcp 65001 | Out-Null
} catch {
    Write-Warning "Could not switch console code page to UTF-8: $_"
}

Write-Host "UTF-8 console enabled. PYTHONUTF8=1, PYTHONIOENCODING=utf-8"
