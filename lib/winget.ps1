Set-StrictMode -Version Latest

function Assert-Winget
{
  if (-not (Get-Command winget -ErrorAction SilentlyContinue))
  {
    Stop-Dotfiles 'winget is not available. Install App Installer from Microsoft Store first.'
  }
}

function Update-WingetSources
{
  Write-Log 'Updating winget sources'

  Invoke-Checked {
    winget source update
  } 'winget source update'
}

function Install-WingetPackage
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Id,

    [string]$Name = $Id,

    [string]$Command
  )

  Assert-Winget

  if ($Command -and (Get-Command $Command -ErrorAction SilentlyContinue))
  {
    Write-Log "Package already installed: $Name" 'Success'
    return
  }

  Write-Log "Installing package: $Name"

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: winget install --id $Id"
    return
  }

  winget install `
    --id $Id `
    --exact `
    --accept-source-agreements `
    --accept-package-agreements `
    --silent `
    --disable-interactivity

  if ($LASTEXITCODE -ne 0)
  {
    throw "winget install failed for $Id with exit code $LASTEXITCODE"
  }

  Write-Log "Installed package: $Name" 'Success'
}

function Update-WingetPackage
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Id,

    [string]$Name = $Id
  )

  Assert-Winget

  Write-Log "Upgrading package: $Name"

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: winget upgrade --id $Id"
    return
  }

  winget upgrade `
    --id $Id `
    --exact `
    --accept-source-agreements `
    --accept-package-agreements `
    --silent `
    --disable-interactivity

  if ($LASTEXITCODE -ne 0)
  {
    Write-Log "winget upgrade finished with exit code $LASTEXITCODE for $Id" 'Warning'
  }
}
