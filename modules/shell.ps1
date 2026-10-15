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
  $sourceProfile = Join-Path $script:CONF_DIR 'powershell/profile.ps1'
  $targetProfile = $PROFILE.CurrentUserAllHosts

  Install-UserFile -Source $sourceProfile -Destination $targetProfile

  Write-Log "PowerShell profile installed: $targetProfile" 'Success'

  $sourceProfile = Join-Path $script:CONF_DIR 'powershell/Microsoft.PowerShell_profile.ps1'
  $targetProfile = $PROFILE.CurrentUserCurrentHost

  Install-UserFile -Source $sourceProfile -Destination $targetProfile

  Write-Log "PowerShell profile installed: $targetProfile" 'Success'
}
