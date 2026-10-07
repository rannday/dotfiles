Set-StrictMode -Version Latest

function Invoke-zed
{
  Write-Log 'Setting up zed'

  Install-WingetPackage -Id 'ZedIndustries.Zed' -Name 'Zed' -Command 'zed'

  $settingsSource = Join-Path $script:CONF_DIR 'zed\settings.windows.json'
  $zedConfigDir = Join-Path $env:APPDATA 'Zed'
  $settingsTarget = Join-Path $zedConfigDir 'settings.json'

  Assert-File $settingsSource

  Install-UserFile -Source $settingsSource -Destination $settingsTarget

  Write-Log "Zed settings installed: $settingsTarget" 'Success'
}
