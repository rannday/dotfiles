Set-StrictMode -Version Latest

function Sync-AlacrittyThemes
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$ThemeDir
  )

  $themeRepo = 'https://github.com/alacritty/alacritty-theme'
  $parentDir = Split-Path -Parent $ThemeDir

  Assert-Command git

  if (-not (Test-Path -LiteralPath $parentDir))
  {
    if ($script:DRY_RUN)
    {
      Write-Log "DRY RUN: create directory $parentDir"
    } else
    {
      New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
  }

  if (-not (Test-Path -LiteralPath $ThemeDir))
  {
    Invoke-Checked {
      git clone --depth 1 $themeRepo $ThemeDir
    } "clone Alacritty themes into $ThemeDir"
    return
  }

  Write-Log "Alacritty themes already present: $ThemeDir" 'Success'
}

function Invoke-alacritty
{
  Write-Log 'Setting up alacritty'

  Install-WingetPackage -Id 'Alacritty.Alacritty' -Name 'Alacritty' -Command 'alacritty'

  $configSource = Join-Path $script:CONF_DIR 'alacritty\windows.alacritty.toml'
  $configTarget = Join-Path $env:APPDATA 'alacritty\alacritty.toml'

  Assert-File $configSource

  Install-UserFile -Source $configSource -Destination $configTarget

  Write-Log "Alacritty config installed: $configTarget" 'Success'

  $themeDir = Join-Path $env:APPDATA 'alacritty\themes'
  Sync-AlacrittyThemes -ThemeDir $themeDir
  Write-Log "Alacritty themes ready: $themeDir" 'Success'
}
