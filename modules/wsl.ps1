Set-StrictMode -Version Latest

function Invoke-WslCommand
{
  param([Parameter(Mandatory = $true)][string[]]$Arguments)

  $output = & wsl.exe @Arguments
  if ($LASTEXITCODE -ne 0)
  {
    throw "wsl.exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
  # Older Windows PowerShell receives WSL's UTF-16 output with embedded NULs.
  ($output -join "`n").Replace("`0", '')
}

function Invoke-wsl
{
  Write-Log 'Installing WSL configuration to Windows home'
  Install-UserFile -Source (Join-Path $script:CONF_DIR 'wsl\.wslconfig') -Destination (Join-Path $HOME '.wslconfig')

  Assert-Command wsl.exe
  Write-Log 'Checking WSL status'
  Write-Host (Invoke-WslCommand -Arguments @('--status'))

  $distros = Invoke-WslCommand -Arguments @('--list', '--verbose')
  if ($distros -notmatch '(?m)^\s*\*\s+Debian\s+.+\s+2\s*$')
  {
    throw 'Debian must be installed as WSL 2 and be the default distro. Check wsl --list --verbose; use wsl --set-default Debian if needed.'
  }

  $linuxPath = (Invoke-WslCommand -Arguments @('--distribution', 'Debian', '--exec', 'wslpath', '-u', $script:BASE_DIR)).Trim()
  if (-not $linuxPath.StartsWith('/'))
  {
    throw 'Could not resolve the repository path inside Debian.'
  }

  $wslArguments = @('--distribution', 'Debian', '--cd', $linuxPath, '--exec', '/bin/sh', './install.sh', '--profile', 'wsl')
  if ($script:DRY_RUN)
  {
    $wslArguments += '--dry-run'
  }

  # Stream setup output and keep stdin attached for Debian sudo prompts.
  & wsl.exe @wslArguments
  if ($LASTEXITCODE -ne 0)
  {
    throw "Debian setup failed with exit code $LASTEXITCODE"
  }
}
