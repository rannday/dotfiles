Set-StrictMode -Version Latest

function Invoke-ssh
{
  Write-Log 'Setting up ssh'

  Assert-Command ssh-keygen

  $script:SSH_HOME = Join-Path $HOME '.ssh'
  $script:SSH_CONF = Join-Path $script:CONF_DIR 'sshconfig'
  $script:SSH_CONFIG_DST = Join-Path $script:SSH_HOME 'config'
  $script:NOC_CONFIG = Join-Path $script:SSH_HOME 'noc-config'

  Assert-File $script:SSH_CONF

  if (-not (Test-Path -LiteralPath $script:SSH_HOME))
  {
    if ($script:DRY_RUN)
    {
      Write-Log "DRY RUN: create directory $script:SSH_HOME"
    } else
    {
      New-Item -ItemType Directory -Path $script:SSH_HOME -Force | Out-Null
    }
  }

  New-SshKeyIfMissing -Path (Join-Path $script:SSH_HOME 'id_ed25519') -Label 'default'
  New-SshKeyIfMissing -Path (Join-Path $script:SSH_HOME 'id_ed25519_github') -Label 'github'
  New-SshKeyIfMissing -Path (Join-Path $script:SSH_HOME 'id_ed25519_varda') -Label 'varda'
  New-SshKeyIfMissing -Path (Join-Path $script:SSH_HOME 'id_ed25519_noc') -Label 'noc'
  New-SshKeyIfMissing -Path (Join-Path $script:SSH_HOME 'id_ed25519_noc_github') -Label 'noc-github'

  Install-SshConfig

  if (-not $script:DRY_RUN)
  {
    Write-MissingSshIdentities
    Set-SshPermissions
  }

  Write-Log 'SSH setup complete' 'Success'
}

function New-SshKeyIfMissing
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [string]$Label
  )

  Assert-Command ssh-keygen

  if (Test-Path -LiteralPath $Path -PathType Leaf)
  {
    Write-Log "SSH key already exists: $Path" 'Success'
    return
  }

  if (Test-Path -LiteralPath "$Path.pub" -PathType Leaf)
  {
    Write-Log "Public key exists without private key: $Path.pub" 'Warning'
    return
  }

  $comment = "$env:USERNAME@$env:COMPUTERNAME-$Label"

  Write-Log "Generating SSH key: $Path"

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: ssh-keygen -t ed25519 -f $Path -C $comment -N empty"
    return
  }

  ssh-keygen -t ed25519 -f $Path -C $comment -N ''

  if ($LASTEXITCODE -ne 0)
  {
    throw "ssh-keygen failed for $Path with exit code $LASTEXITCODE"
  }
}

function Install-SshConfig
{
  Write-Log 'Installing SSH config'

  $stagedConfig = Join-Path $script:SSH_HOME 'sshconfig'

  if (-not $script:DRY_RUN)
  {
    Remove-Item -LiteralPath $script:SSH_CONFIG_DST -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stagedConfig -Force -ErrorAction SilentlyContinue
  } else
  {
    Write-Log "DRY RUN: remove $script:SSH_CONFIG_DST and $stagedConfig"
  }

  Install-UserFile -Source $script:SSH_CONF -Destination $stagedConfig

  if (Test-Path -LiteralPath $script:NOC_CONFIG -PathType Leaf)
  {
    Write-Log 'Merging noc-config into SSH config'

    if ($script:DRY_RUN)
    {
      Write-Log "DRY RUN: merge $script:NOC_CONFIG + $stagedConfig -> $script:SSH_CONFIG_DST"
      return
    }

    $nocContent = Get-Content -LiteralPath $script:NOC_CONFIG -Raw
    $baseContent = Get-Content -LiteralPath $stagedConfig -Raw

    if ($nocContent -notmatch "(`r?`n)\s*$")
    {
      $nocContent += "`n"
    }

    Set-Content -LiteralPath $script:SSH_CONFIG_DST -Value ($nocContent + $baseContent) -NoNewline -Force
    Remove-Item -LiteralPath $stagedConfig -Force

    Write-Log 'SSH config merged' 'Success'
  } else
  {
    Write-Log 'noc-config not found; using base SSH config only' 'Warning'

    if (-not $script:DRY_RUN)
    {
      Move-Item -LiteralPath $stagedConfig -Destination $script:SSH_CONFIG_DST -Force
    }
  }
}

function Write-MissingSshIdentities
{
  if (-not (Test-Path -LiteralPath $script:SSH_CONFIG_DST -PathType Leaf))
  {
    return
  }

  $missing = @()

  Get-Content -LiteralPath $script:SSH_CONFIG_DST | ForEach-Object {
    $line = $_.Trim()

    if ($line -match '^(?i)IdentityFile\s+(.+)$')
    {
      $identity = $Matches[1].Trim('"')

      if ($identity.StartsWith('~'))
      {
        $identity = Join-Path $HOME $identity.Substring(2)
      }

      if (-not (Test-Path -LiteralPath $identity -PathType Leaf))
      {
        $missing += $identity
      }
    }
  }

  if ($missing.Count -gt 0)
  {
    Write-Log 'SSH config references missing identity files:' 'Warning'
    $missing | Sort-Object -Unique | ForEach-Object {
      Write-Warning "  $_"
    }
  }
}

function Set-SshPermissions
{
  Write-Log 'Fixing SSH permissions'

  if (-not (Test-Path -LiteralPath $script:SSH_HOME))
  {
    return
  }

  $userAccount = if ($env:USERDOMAIN)
  {
    "$env:USERDOMAIN\$env:USERNAME"
  } else
  {
    $env:USERNAME
  }

  $directoryGrants = @("${userAccount}:(OI)(CI)F")
  $fileGrants = @("${userAccount}:F")

  icacls $script:SSH_HOME /inheritance:r | Out-Null
  icacls $script:SSH_HOME /grant:r $directoryGrants | Out-Null

  Get-ChildItem -LiteralPath $script:SSH_HOME -Recurse -Force | ForEach-Object {
    icacls $_.FullName /inheritance:r | Out-Null

    if ($_.PSIsContainer)
    {
      icacls $_.FullName /grant:r $directoryGrants | Out-Null
    } else
    {
      icacls $_.FullName /grant:r $fileGrants | Out-Null
    }
  }
}
