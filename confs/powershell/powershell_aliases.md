# PowerShell Aliases
```powershell
function ..
{
  Set-Location ..
}

function ...
{
  Set-Location ../..
}

function home
{
  Set-Location $HOME
}

function c
{
  Clear-Host
}

function la
{
  Get-ChildItem -Force
}

function lt
{
  Get-ChildItem -Force -Recurse
}

function lsize
{
  $sum = (Get-ChildItem -File -Recurse | Measure-Object -Property Length -Sum).Sum
  "{0} MB" -f ([math]::Round($sum / 1MB, 2))
}

function grep
{
  param(
    [string]$Pattern,
    [string[]]$Path = "*"
  )

  Select-String -Pattern $Pattern -Path $Path
}

function grepr($pattern)
{
  Get-ChildItem -Recurse | Select-String -Pattern $pattern
}

function h
{
  Get-History
}

function hgrep($pattern)
{
  Get-History | Where-Object CommandLine -match $pattern
}

function histfile
{
  Get-Content (Get-PSReadLineOption).HistorySavePath
}

function histgrep($pattern)
{
  Select-String -Path (Get-PSReadLineOption).HistorySavePath -Pattern $pattern
}

function ports
{
  Get-NetTCPConnection | Where-Object State -eq "Listen"
}

function myip
{
  Invoke-RestMethod "https://ifconfig.me/ip"
}

function flushdns
{
  Clear-DnsClientCache
}

function iprenew
{
  ipconfig /release > $null
  ipconfig /renew > $null
}

function psgrep($name)
{
  Get-Process | Where-Object Name -match $name
}

function killp($name)
{
  Get-Process -Name $name | Stop-Process
}

function tempclean
{
  Remove-Item -Path "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue
}

function wintemp
{
  Remove-Item -Path "C:\Windows\Temp\*" -Recurse -Force -ErrorAction SilentlyContinue
}

function wucache
{
  Stop-Service -Name wuauserv, bits -Force -ErrorAction SilentlyContinue
  Remove-Item -Path "C:\Windows\SoftwareDistribution\*" -Recurse -Force -ErrorAction SilentlyContinue
  Start-Service -Name wuauserv, bits -ErrorAction SilentlyContinue
}

function evclear
{
  wevtutil el | ForEach-Object { wevtutil cl "$_" } 2>$null
}

function rbclear
{
  Clear-RecycleBin -Force -ErrorAction SilentlyContinue
}

function sysfix
{
  sfc /scannow
  DISM /Online /Cleanup-Image /RestoreHealth
}

function dismfix
{
  DISM /Online /Cleanup-Image /RestoreHealth
}

function sfcfix
{
  sfc /scannow
}

function chkdsknext
{
  Write-Output y | chkdsk C: /f /r > $null
}
```
