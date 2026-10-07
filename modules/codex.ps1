Set-StrictMode -Version Latest

function Install-CodexCli
{
  if (Get-Command codex -ErrorAction SilentlyContinue)
  {
    Write-Log 'Codex CLI already installed' 'Success'
    return
  }

  Write-Log 'Installing Codex CLI'

  if ($script:DRY_RUN)
  {
    Write-Log 'DRY RUN: powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"'
    return
  }

  & powershell.exe -ExecutionPolicy ByPass -c 'irm https://chatgpt.com/codex/install.ps1 | iex'

  if ($LASTEXITCODE -ne 0)
  {
    throw "Codex CLI install failed with exit code $LASTEXITCODE"
  }
}

function Invoke-codex
{
  Write-Log 'Setting up codex'

  Install-CodexCli

  $codexSource = Join-Path $script:CONF_DIR 'codex'
  $agentsSource = Join-Path $codexSource 'AGENTS.md'
  $workflowSource = Join-Path $codexSource 'workflow.md'
  $configSource = Join-Path $codexSource 'windows.config.toml'
  $serenaContext = Join-Path $codexSource 'serena-context.yml'
  $rulesSource = Join-Path $codexSource 'rules'
  $crewSource = Join-Path $codexSource 'agents'
  $hookJson = Join-Path $codexSource 'windows.hooks.json'
  $sharedHooks = Join-Path (Split-Path $script:CONF_DIR -Parent) 'agents\hooks'

  $codexTarget = Join-Path $HOME '.codex'
  $sharedTarget = Join-Path $HOME '.agents\hooks\bin'
  $rulesTarget = Join-Path $codexTarget 'rules'

  Assert-File $agentsSource
  Assert-File $workflowSource
  Assert-File $configSource
  Assert-File $serenaContext
  Assert-Directory $rulesSource
  Assert-Directory $crewSource
  Assert-File $hookJson
  foreach ($name in @('tool_gate.py', 'turn_end.py', 'codex_hooks.py'))
  {
    Assert-File (Join-Path $sharedHooks $name)
  }

  New-CodexDirectory $codexTarget
  New-CodexDirectory $rulesTarget

  Install-UserFile -Source $agentsSource -Destination (Join-Path $codexTarget 'AGENTS.md')
  Install-UserFile -Source $workflowSource -Destination (Join-Path $codexTarget 'workflow.md')
  Install-UserFile -Source $configSource -Destination (Join-Path $codexTarget 'config.toml')
  Install-UserFile -Source $serenaContext -Destination (Join-Path $codexTarget 'serena-context.yml')
  Install-UserFile -Source $hookJson -Destination (Join-Path $codexTarget 'hooks.json')
  foreach ($name in @('tool_gate.py', 'turn_end.py', 'codex_hooks.py'))
  {
    Install-UserFile -Source (Join-Path $sharedHooks $name) -Destination (Join-Path $sharedTarget $name)
  }
  Get-ChildItem -LiteralPath $crewSource -Filter '*.toml' -File | ForEach-Object {
    Install-UserFile -Source $_.FullName -Destination (Join-Path $codexTarget "agents\$($_.Name)")
  }

  Get-ChildItem -LiteralPath $rulesSource -Filter '*.rules' -File |
    Where-Object { $_.Name -ne 'linux.rules' } |
    ForEach-Object {
      Install-UserFile -Source $_.FullName -Destination (Join-Path $rulesTarget $_.Name)
    }

  Write-Log "Codex config installed: $codexTarget" 'Success'
}

function New-CodexDirectory
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  if (Test-Path -LiteralPath $Path -PathType Container)
  {
    return
  }

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: create directory $Path"
  } else
  {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}
