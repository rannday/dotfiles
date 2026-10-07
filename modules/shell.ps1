Set-StrictMode -Version Latest

function Invoke-shell
{
  Write-Log 'Setting up shell'

  Install-WingetPackage -Id 'Microsoft.PowerShell' -Name 'PowerShell' -Command 'pwsh'
  Install-WingetPackage -Id 'Starship.Starship' -Name 'Starship' -Command 'starship'

  Install-PowerShellProfile
}

function Install-PowerShellProfile
{
  $sourceProfile = Join-Path $script:CONF_DIR 'Microsoft.PowerShell_profile.ps1'
  $profileDir = Join-Path $HOME 'Documents\PowerShell'
  $targetProfile = Join-Path $profileDir 'Microsoft.PowerShell_profile.ps1'

  Install-UserFile -Source $sourceProfile -Destination $targetProfile

  Write-Log "PowerShell profile installed: $targetProfile" 'Success'
}
