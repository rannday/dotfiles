Set-StrictMode -Version Latest

function Install-GrokCli
{
  if (Get-Command grok -ErrorAction SilentlyContinue)
  {
    Write-Log 'Grok CLI already installed' 'Success'
    return
  }

  Write-Log 'Installing Grok CLI'

  if ($script:DRY_RUN)
  {
    Write-Log 'DRY RUN: irm https://x.ai/cli/install.ps1 | iex'
    return
  }

  Invoke-RestMethod https://x.ai/cli/install.ps1 | Invoke-Expression
}

function Invoke-grok
{
  Write-Log 'Setting up grok'

  Install-GrokCli

  $grokSource = Join-Path $script:CONF_DIR 'grok'
  $agentsSource = Join-Path $grokSource 'AGENTS.md'
  $configSource = Join-Path $grokSource 'config.toml'
  $sandboxSource = Join-Path $grokSource 'windows.sandbox.toml'
  $crewSource = Join-Path $grokSource 'agents'

  $grokTarget = Join-Path $HOME '.grok'
  $crewTarget = Join-Path $grokTarget 'agents'

  Assert-File $agentsSource
  Assert-File $configSource
  Assert-File $sandboxSource
  Assert-Directory $crewSource

  New-GrokDirectory $grokTarget
  New-GrokDirectory $crewTarget

  Install-UserFile -Source $agentsSource -Destination (Join-Path $grokTarget 'AGENTS.md')
  Install-UserFile -Source $configSource -Destination (Join-Path $grokTarget 'config.toml')
  Install-UserFile -Source $sandboxSource -Destination (Join-Path $grokTarget 'sandbox.toml')

  Get-ChildItem -LiteralPath $crewSource -Filter '*.md' -File | ForEach-Object {
    Install-UserFile -Source $_.FullName -Destination (Join-Path $crewTarget $_.Name)
  }

  Install-GrokHooks

  Write-Log "Grok config installed: $grokTarget" 'Success'
}

function Install-GrokHooks
{
  $sourceRoot = Join-Path $script:CONF_DIR 'grok'
  $hookJson = Join-Path $sourceRoot 'windows.hooks.json'
  $sharedHooks = Join-Path (Split-Path $script:CONF_DIR -Parent) 'agents\hooks'
  $turnEnd = Join-Path $sharedHooks 'turn_end.py'
  $toolGate = Join-Path $sharedHooks 'tool_gate.py'
  $voice = Join-Path $sourceRoot 'rules\voice.md'
  $grokHooks = Join-Path $HOME '.grok\hooks'
  $sharedTarget = Join-Path $HOME '.agents\hooks\bin'
  $grokRules = Join-Path $HOME '.grok\rules'

  Assert-File $hookJson
  Assert-File $turnEnd
  Assert-File $toolGate
  Assert-File $voice

  if (-not (Get-Command py -ErrorAction SilentlyContinue))
  {
    Write-Log 'py launcher not found; grok hooks need py -3' 'Warning'
  }

  # Grok loads ~/.grok/hooks/*.json. Drop the old name so hooks do not run twice.
  Write-Log 'Installing Grok hooks'
  Install-UserFile -Source $turnEnd -Destination (Join-Path $sharedTarget 'turn_end.py')
  Install-UserFile -Source $toolGate -Destination (Join-Path $sharedTarget 'tool_gate.py')
  Install-UserFile -Source $hookJson -Destination (Join-Path $grokHooks 'hooks.json')
  Install-UserFile -Source $voice -Destination (Join-Path $grokRules 'voice.md')
  $staleHookJson = Join-Path $grokHooks 'turn_end.json'
  if (Test-Path -LiteralPath $staleHookJson)
  {
    if ($script:DRY_RUN)
    {
      Write-Log "DRY RUN: remove $staleHookJson"
    } else
    {
      Remove-Item -LiteralPath $staleHookJson -Force
    }
  }
  Write-Log "Grok hooks installed: $grokHooks" 'Success'
}

function New-GrokDirectory
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
