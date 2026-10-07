starship init powershell | Invoke-Expression

# Save command history after each command
if (Get-Command Set-PSReadLineOption -ErrorAction SilentlyContinue)
{
  Set-PSReadLineOption -HistorySaveStyle SaveIncrementally
}

function Get-VSInstallRoot
{
  [CmdletBinding()]
  param()

  # This PC: C:\Program Files (x86)\Microsoft Visual Studio\2022 (Community/Enterprise).
  # Work PC: TBD (will adjust later). Simplify: check preferred first, then fallback.
  $preferredRoot = "C:\Program Files (x86)\Microsoft Visual Studio\2022"

  if (Test-Path -LiteralPath $preferredRoot -PathType Container)
  {
    $vsDevCmd = Join-Path $preferredRoot "Common7\Tools\VsDevCmd.bat"
    if (Test-Path -LiteralPath $vsDevCmd -PathType Leaf)
    {
      return $preferredRoot
    }
  }

  # Fallback: vswhere (if installed) for any VS with C++ tools.
  $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
  if (Test-Path -LiteralPath $vswhere -PathType Leaf)
  {
    $root = & $vswhere -latest -products * `
      -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
      -property installationPath 2>$null

    if ($root -and (Test-Path -LiteralPath (Join-Path $root "Common7\Tools\VsDevCmd.bat") -PathType Leaf))
    {
      return $root
    }

    $root = & $vswhere -latest -products * -property installationPath 2>$null
    if ($root -and (Test-Path -LiteralPath (Join-Path $root "Common7\Tools\VsDevCmd.bat") -PathType Leaf))
    {
      return $root
    }
  }

  return $null
}

function Import-VSDevEnvironment
{
  [CmdletBinding()]
  param(
    [string]$Arch = "x64",
    [string]$HostArch = "x64"
  )

  $VsRoot = Get-VSInstallRoot

  if (-not $VsRoot)
  {
    Write-Warning "No Visual Studio installation with VsDevCmd.bat found."
    return
  }

  $vsDevCmd = Join-Path $VsRoot "Common7\Tools\VsDevCmd.bat"

  if (-not (Test-Path -Path $vsDevCmd -PathType Leaf))
  {
    Write-Warning "VsDevCmd.bat not found: $vsDevCmd"
    return
  }

  $envDump = cmd.exe /s /c "`"$vsDevCmd`" -arch=$Arch -host_arch=$HostArch >nul && set"

  foreach ($line in $envDump)
  {
    if ($line -match '^(.*?)=(.*)$')
    {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
  }

  # Set MSBuild + VCTargetsPath *only* if they exist (skip gracefully on work PC until we know layout).
  # VsDevCmd usually puts MSBuild on PATH; append only if missing.
  $vsMsbuildBin = Join-Path $VsRoot "MSBuild\Current\Bin"
  if ((Test-Path "$vsMsbuildBin\MSBuild.exe") -and ($env:PATH -notlike "*$vsMsbuildBin*"))
  {
    $env:PATH = "$env:PATH;$vsMsbuildBin"
  }

  $vcTargets = Join-Path $VsRoot "MSBuild\Microsoft\VC\v170"
  if (Test-Path "$vcTargets\Microsoft.Cpp.Default.props")
  {
    $env:VCTargetsPath = "$vcTargets\"
  } else
  {
    $vcTargets = Join-Path $VsRoot "MSBuild\Microsoft\VC\v160"
    if (Test-Path "$vcTargets\Microsoft.Cpp.Default.props")
    {
      $env:VCTargetsPath = "$vcTargets\"
    }
  }
}

function Write-UpdateStatus
{
  param(
    [Parameter(Mandatory)]
    [string]$Message,

    [ValidateSet('Info', 'Success', 'Warning')]
    [string]$Level = 'Info'
  )

  switch ($Level)
  {
    'Success'
    {
      Write-Host "SUCCESS: $Message" -ForegroundColor Green
    }

    'Warning'
    {
      Write-Warning $Message
    }

    default
    {
      Write-Host "INFO: $Message" -ForegroundColor Cyan
    }
  }
}

function Invoke-WindowsSystemUpdate
{
  $hadWarnings = $false

  Write-UpdateStatus "Checking for Windows updates..."

  try
  {
    if (-not (Get-PackageProvider -Name NuGet -ErrorAction SilentlyContinue))
    {
      Write-UpdateStatus "Installing the NuGet package provider..."

      Install-PackageProvider `
        -Name NuGet `
        -MinimumVersion 2.8.5.201 `
        -Force `
        -Scope CurrentUser `
        -ErrorAction Stop |
        Out-Null
    }

    if (-not (Get-Module -ListAvailable -Name PSWindowsUpdate))
    {
      Write-UpdateStatus "Installing the PSWindowsUpdate module..."

      Install-Module `
        -Name PSWindowsUpdate `
        -Force `
        -Scope CurrentUser `
        -AllowClobber `
        -ErrorAction Stop
    }

    if ($IsCoreCLR)
    {
      Import-Module `
        PSWindowsUpdate `
        -UseWindowsPowerShell `
        -ErrorAction Stop
    }
    else
    {
      Import-Module `
        PSWindowsUpdate `
        -ErrorAction Stop
    }

    Get-WindowsUpdate `
      -AcceptAll `
      -Install `
      -IgnoreReboot `
      -ErrorAction Stop |
      Out-Null

    Write-UpdateStatus "Windows Update cycle completed." "Success"
  }
  catch
  {
    $hadWarnings = $true
    Write-UpdateStatus `
      "Windows Update failed: $($_.Exception.Message)" `
      "Warning"
  }

  if ($hadWarnings)
  {
    Write-UpdateStatus "Windows updates completed with warnings." "Warning"
  }
  else
  {
    Write-UpdateStatus "All Windows updates completed successfully." "Success"
  }
}

function update
{
  $hadWarnings = $false

  Write-UpdateStatus "Updating FFF MCP..."

  $installDir = Join-Path $env:LOCALAPPDATA 'fff-mcp\bin'
  $binary = Join-Path $installDir 'fff-mcp.exe'
  $installer = Join-Path $env:TEMP 'install-fff-mcp.ps1'

  $runningProcesses = @(
    Get-CimInstance `
      Win32_Process `
      -Filter "Name = 'fff-mcp.exe'" `
      -ErrorAction SilentlyContinue |
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
    $hadWarnings = $true
    $processIds = $runningProcesses.ProcessId -join ', '

    Write-UpdateStatus `
      "FFF MCP is currently in use (PID: $processIds). Close active Codex sessions and run update again." `
      "Warning"
  }
  else
  {
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

      Write-UpdateStatus "FFF MCP updated." "Success"
    }
    catch
    {
      $hadWarnings = $true

      Write-UpdateStatus `
        "FFF MCP update failed: $($_.Exception.Message)" `
        "Warning"
    }
    finally
    {
      Remove-Item `
        -LiteralPath $installer `
        -Force `
        -ErrorAction SilentlyContinue
    }
  }

  Write-UpdateStatus "Updating Codex..."

  codex update

  if ($LASTEXITCODE -ne 0)
  {
    $hadWarnings = $true
    Write-UpdateStatus `
      "Codex update exited with code $LASTEXITCODE." `
      "Warning"
  }

  Write-UpdateStatus "Updating Grok..."

  grok update

  if ($LASTEXITCODE -ne 0)
  {
    $hadWarnings = $true
    Write-UpdateStatus `
      "Grok update exited with code $LASTEXITCODE." `
      "Warning"
  }

  Write-UpdateStatus "Updating Caveman..."

  if (-not (Get-Command npx -ErrorAction SilentlyContinue))
  {
    $hadWarnings = $true
    Write-UpdateStatus "npx is not available; skipping Caveman update." "Warning"
  }
  else
  {
    npx -y github:JuliusBrussee/caveman -- --only grok --force

    if ($LASTEXITCODE -ne 0)
    {
      $hadWarnings = $true
      Write-UpdateStatus `
        "Caveman update exited with code $LASTEXITCODE." `
        "Warning"
    }
  }

  if (Get-Command winget -ErrorAction SilentlyContinue)
  {
    Write-UpdateStatus "Running bulk Winget upgrade..."

    winget upgrade `
      --all `
      --include-unknown `
      --accept-source-agreements `
      --accept-package-agreements `
      --silent `
      --disable-interactivity

    $wingetExitCode = $LASTEXITCODE

    if ($wingetExitCode -eq 0)
    {
      Write-UpdateStatus "Winget upgrade completed." "Success"
    }
    elseif ($wingetExitCode -eq -1978335189)
    {
      Write-UpdateStatus "All Winget packages are up to date."
    }
    else
    {
      $hadWarnings = $true
      Write-UpdateStatus `
        "Winget exited with code $wingetExitCode. Some packages may require manual updates." `
        "Warning"
    }
  }
  else
  {
    $hadWarnings = $true
    Write-UpdateStatus `
      "Winget is not available; skipping package upgrades." `
      "Warning"
  }

  $isAdmin = (
    [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
  )

  if (-not $isAdmin)
  {
    Write-UpdateStatus "Requesting administrative privileges for Windows Update..."

    $exe = (Get-Process -Id $PID).Path
    $escapedProfile = $PROFILE.Replace("'", "''")

    Start-Process $exe -Verb RunAs -ArgumentList @(
      '-NoProfile'
      '-NoExit'
      '-Command'
      ". '$escapedProfile'; Invoke-WindowsSystemUpdate"
    )

    return
  }

  if ($hadWarnings)
  {
    Write-UpdateStatus "Update process completed with warnings." "Warning"
  }
  else
  {
    Write-UpdateStatus "Updates completed successfully." "Success"
  }

  Invoke-WindowsSystemUpdate
}
