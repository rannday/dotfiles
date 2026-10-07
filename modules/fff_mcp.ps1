Set-StrictMode -Version Latest

function Invoke-fff_mcp
{
  Write-Log 'Setting up fff-mcp'

  $installDir = Join-Path $env:LOCALAPPDATA 'fff-mcp\bin'
  $binary = Join-Path $installDir 'fff-mcp.exe'
  $installer = Join-Path $env:TEMP 'install-fff-mcp.ps1'

  if (Test-Path -LiteralPath $binary -PathType Leaf)
  {
    Write-Log 'FFF MCP already installed' 'Success'
    return
  }

  $runningProcesses = @(
    Get-CimInstance Win32_Process -Filter "Name = 'fff-mcp.exe'" -ErrorAction SilentlyContinue |
      Where-Object {
        $_.ExecutablePath -and
        [string]::Equals(
          $_.ExecutablePath,
          $binary,
          [StringComparison]::OrdinalIgnoreCase
        )
      }
  )

  if ($runningProcesses.Count -gt 0)
  {
    $processIds = $runningProcesses.ProcessId -join ', '

    Write-Log "FFF MCP is currently being used by another process (PID: $processIds)." 'Warning'
    Write-Log 'Close active Codex sessions and run the update again.' 'Warning'
    return
  }

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: download FFF MCP installer to $installer"
    Write-Log 'DRY RUN: run FFF MCP installer'
    return
  }

  try
  {
    Invoke-WebRequest `
      -Uri 'https://raw.githubusercontent.com/dmtrKovalenko/fff.nvim/main/install-mcp.ps1' `
      -OutFile $installer `
      -ErrorAction Stop

    & $installer -PathScope User

    if ($LASTEXITCODE -ne 0)
    {
      throw "FFF MCP installer exited with code $LASTEXITCODE"
    }

    Write-Log 'FFF MCP installed' 'Success'
  }
  catch
  {
    Write-Log "FFF MCP installation failed: $($_.Exception.Message)" 'Warning'
    throw
  }
  finally
  {
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
  }
}
