Set-StrictMode -Version Latest

function Invoke-zellij
{
  Write-Log 'Setting up zellij'

  Install-WingetPackage -Id 'Zellij.Zellij' -Name 'Zellij' -Command 'zellij'

  $configSource = Join-Path $script:CONF_DIR 'zellij\windows.config.kdl'
  $configTarget = Join-Path $env:APPDATA 'Zellij\config\config.kdl'
  $layoutSource = Join-Path $script:CONF_DIR 'zellij\layouts'
  $layoutTarget = Join-Path $env:APPDATA 'Zellij\config\layouts'

  Assert-File $configSource
  Assert-Directory $layoutSource

  Install-UserFile -Source $configSource -Destination $configTarget

  Get-ChildItem -LiteralPath $layoutSource -Filter '*.kdl' -File | ForEach-Object {
    Install-UserFile -Source $_.FullName -Destination (Join-Path $layoutTarget $_.Name)
  }

  Write-Log "Zellij config installed: $configTarget" 'Success'
  Write-Log "Zellij layouts installed: $layoutTarget" 'Success'
}
