Set-StrictMode -Version Latest

function Install-Caveman
{
  param(
    [ValidateSet('grok', 'codex')]
    [string]$Agent = 'grok'
  )

  $skill = if ($Agent -eq 'codex')
  {
    Join-Path $HOME '.agents\skills\caveman\SKILL.md'
  } else
  {
    Join-Path $HOME '.grok\skills\caveman\SKILL.md'
  }

  if (Test-Path -LiteralPath $skill -PathType Leaf)
  {
    Write-Log "Caveman already installed for $Agent" 'Success'
    return
  }

  Write-Log "Installing Caveman for $Agent"

  $installArgs = if ($Agent -eq 'codex')
  {
    @('--allow-git=all', '-y', 'skills', 'add', 'JuliusBrussee/caveman', '--skill', '*', '-a', 'codex', '--yes', '-g')
  } else
  {
    @('-y', 'github:JuliusBrussee/caveman', '--', '--only', 'grok')
  }
  $description = 'npx ' + ($installArgs -join ' ')

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: $description"
    return
  }

  $npx = Get-Command npx -ErrorAction SilentlyContinue
  if ($npx)
  {
    $npxExe = $npx.Source
  }
  else
  {
    $npxExe = Join-Path ${env:ProgramFiles} 'nodejs\npx.cmd'
    if (-not (Test-Path -LiteralPath $npxExe -PathType Leaf))
    {
      Stop-Dotfiles 'Required command not found: npx'
    }
  }

  Invoke-Checked {
    & $npxExe @installArgs
  } $description
}

function Invoke-caveman
{
  Write-Log 'Setting up caveman'

  Install-Caveman -Agent grok
  Install-Caveman -Agent codex

  Write-Log 'Caveman setup complete' 'Success'
}
