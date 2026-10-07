Set-StrictMode -Version Latest

function Invoke-gitkraken-cli
{
  Write-Log 'Setting up gitkraken-cli'

  Install-WingetPackage -Id 'GitKraken.cli' -Name 'GitKraken CLI' -Command 'gk'

  Write-Log 'GitKraken CLI setup complete' 'Success'
}
