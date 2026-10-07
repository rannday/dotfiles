Set-StrictMode -Version Latest

function Install-Uv
{
  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if (-not $uv)
  {
    $uvPath = Join-Path $HOME '.local\bin\uv.exe'
    if (Test-Path -LiteralPath $uvPath -PathType Leaf)
    {
      $uv = $uvPath
    }
  }

  if ($uv)
  {
    Write-Log 'uv already installed' 'Success'
    return
  }

  Write-Log 'Installing uv'

  $command = 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: $command"
    return
  }

  Invoke-Checked {
    & powershell.exe -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
  } $command
}

function Invoke-uv
{
  Write-Log 'Setting up uv'

  Install-Uv

  Write-Log 'uv setup complete' 'Success'
}
