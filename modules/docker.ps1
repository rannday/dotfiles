Set-StrictMode -Version Latest

function Test-DockerCliInstalled
{
  $roots = @(
    (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages')
    (Join-Path ${env:ProgramFiles} 'WinGet\Packages')
  )

  foreach ($root in $roots)
  {
    if (-not (Test-Path -LiteralPath $root -PathType Container))
    {
      continue
    }

    $packageDirs = @(
      Get-ChildItem `
        -LiteralPath $root `
        -Directory `
        -Filter 'Docker.DockerCLI*' `
        -ErrorAction SilentlyContinue
    )

    if ($packageDirs.Count -gt 0)
    {
      return $true
    }
  }

  return $false
}

function Invoke-docker
{
  Write-Log 'Setting up docker'

  $desktop = Join-Path ${env:ProgramFiles} 'Docker\Docker\Docker Desktop.exe'
  if (Test-Path -LiteralPath $desktop -PathType Leaf)
  {
    Write-Log 'Docker Desktop already installed' 'Success'
  }
  else
  {
    Install-WingetPackage -Id 'Docker.DockerDesktop' -Name 'Docker Desktop'
  }

  if (Test-DockerCliInstalled)
  {
    Write-Log 'Docker CLI already installed' 'Success'
  }
  else
  {
    Install-WingetPackage -Id 'Docker.DockerCLI' -Name 'Docker CLI'
  }

  Write-Log 'Docker setup complete' 'Success'
}
