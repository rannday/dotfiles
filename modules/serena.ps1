Set-StrictMode -Version Latest

function Get-UvExecutable
{
  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if ($uv)
  {
    return $uv.Source
  }

  $uvPath = Join-Path $HOME '.local\bin\uv.exe'
  if (Test-Path -LiteralPath $uvPath -PathType Leaf)
  {
    return $uvPath
  }

  return $null
}

function Test-SerenaAgentInstalled
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Uv
  )

  try
  {
    $listing = @(& $Uv tool list 2>&1)
  }
  catch
  {
    return $false
  }

  if ($LASTEXITCODE -ne 0)
  {
    return $false
  }

  foreach ($line in $listing)
  {
    if ("$line".Trim() -like 'serena-agent *')
    {
      return $true
    }
  }

  return $false
}

function Install-SerenaAgent
{
  $uv = Get-UvExecutable
  if (-not $uv)
  {
    if ($script:DRY_RUN)
    {
      Write-Log 'DRY RUN: uv tool install -p 3.13 serena-agent'
      return
    }

    Stop-Dotfiles 'Required command not found: uv'
  }

  if (Test-SerenaAgentInstalled -Uv $uv)
  {
    Write-Log 'Serena already installed' 'Success'
    return
  }

  Write-Log 'Installing Serena'

  if ($script:DRY_RUN)
  {
    Write-Log 'DRY RUN: uv tool install -p 3.13 serena-agent'
    return
  }

  Invoke-Checked {
    & $uv tool install -p 3.13 serena-agent
  } 'uv tool install -p 3.13 serena-agent'
}

function Get-SerenaHome
{
  if (-not [string]::IsNullOrWhiteSpace($env:SERENA_HOME))
  {
    return $env:SERENA_HOME
  }

  return (Join-Path $HOME '.serena')
}

function Get-SerenaProjectsBlock
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf))
  {
    return $null
  }

  $text = [System.IO.File]::ReadAllText($Path)
  $match = [regex]::Match($text, '(?m)^projects:(?:[ \t].*)?(?:\r?\n(?:[ \t].*|- .*))*')
  if (-not $match.Success)
  {
    return $null
  }

  return $match.Value.TrimEnd("`r", "`n")
}

function Install-SerenaConfig
{
  # serena init rewrites this file. The shipped YAML is the config.
  # serena setup grok runs `grok mcp add` and rewrites ~/.grok/config.toml.
  # The grok module already registers that server.
  $source = Join-Path $script:CONF_DIR 'serena\serena_config.windows.yml'
  $destination = Join-Path (Get-SerenaHome) 'serena_config.yml'
  Assert-File $source

  $projects = $null
  $sourceText = [System.IO.File]::ReadAllText($source)
  if ($sourceText -notmatch '(?m)^projects:')
  {
    $projects = Get-SerenaProjectsBlock -Path $destination
  }

  Install-UserFile -Source $source -Destination $destination

  if ($script:DRY_RUN)
  {
    if ($projects)
    {
      Write-Log "DRY RUN: keep registered projects in $destination"
    }
    return
  }

  if ($projects -and -not (Select-String -LiteralPath $destination -Pattern '^projects:' -Quiet))
  {
    $text = [System.IO.File]::ReadAllText($destination)
    if (-not $text.EndsWith("`n"))
    {
      $text += "`n"
    }

    $text += $projects + "`n"
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($destination, $text, $utf8)
    Write-Log "Kept registered Serena projects in $destination"
  }

  Write-Log "Serena config installed: $destination" 'Success'
}

function Invoke-serena
{
  Write-Log 'Setting up serena'

  Install-SerenaAgent
  Install-SerenaConfig

  Write-Log 'Serena setup complete' 'Success'
}
