Set-StrictMode -Version Latest

$script:DRY_RUN = $false

function Show-Usage
{
  @'
Usage: .\install.ps1 [options]

Options:
  --dry-run            Print intended actions without making changes
  -h, --help           Show this help
'@
}

function Write-Log
{
  param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Message,

    [Parameter(Position = 1)]
    [ValidateSet('Info', 'Success', 'Warning', 'Error', 'Verbose')]
    [string]$Level = 'Info'
  )

  switch ($Level)
  {
    'Error'
    { Write-Error $Message 
    }
    'Warning'
    { Write-Warning $Message 
    }
    'Verbose'
    { Write-Verbose $Message 
    }
    'Success'
    { Write-Host "SUCCESS: $Message" -ForegroundColor Green 
    }
    'Info'
    { Write-Host "INFO: $Message" -ForegroundColor Cyan 
    }
  }
}

function Stop-Dotfiles
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Log $Message 'Error'
  exit 1
}

function Initialize-Dotfiles
{
  param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  if ($null -eq $Arguments)
  {
    $Arguments = @()
  }

  for ($i = 0; $i -lt $Arguments.Count; $i++)
  {
    switch -Regex ($Arguments[$i])
    {
      '^--dry-run$'
      {
        $script:DRY_RUN = $true
        continue
      }

      '^-h$|^--help$'
      {
        Show-Usage
        exit 0
      }

      default
      {
        Stop-Dotfiles "Unknown option: $($Arguments[$i])"
      }
    }
  }
}

function Assert-Command
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue))
  {
    Stop-Dotfiles "Required command not found: $Name"
  }
}

function Assert-File
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf))
  {
    Stop-Dotfiles "Missing file: $Path"
  }
}

function Assert-Directory
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  if (-not (Test-Path -LiteralPath $Path -PathType Container))
  {
    Stop-Dotfiles "Missing directory: $Path"
  }
}

function Invoke-Checked
{
  param(
    [Parameter(Mandatory = $true)]
    [scriptblock]$ScriptBlock,

    [string]$Description = 'command'
  )

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: $Description"
    return
  }

  & $ScriptBlock

  if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE)
  {
    throw "$Description failed with exit code $LASTEXITCODE"
  }
}

function Install-UserFile
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Destination
  )

  Assert-File $Source

  $destinationDir = Split-Path -Parent $Destination

  if (-not (Test-Path -LiteralPath $destinationDir))
  {
    if ($script:DRY_RUN)
    {
      Write-Log "DRY RUN: create directory $destinationDir"
    } else
    {
      New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    }
  }

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: copy $Source -> $Destination"
    return
  }

  Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Invoke-DotfilesModule
{
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  $moduleFile = Join-Path $script:MODULE_DIR "$Name.ps1"
  Assert-File $moduleFile

  . $moduleFile

  $functionName = "Invoke-$Name"
  if (-not (Get-Command $functionName -ErrorAction SilentlyContinue))
  {
    Stop-Dotfiles "Module '$Name' does not define $functionName"
  }

  & $functionName
}
