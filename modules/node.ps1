Set-StrictMode -Version Latest

function Invoke-node
{
  Write-Log 'Setting up node'

  Install-WingetPackage -Id 'OpenJS.NodeJS' -Name 'Node.js' -Command 'node'

  Write-Log 'Node setup complete' 'Success'
}
