Set-StrictMode -Version Latest

function Install-GoTool
{
  param(
    [string]$Name,
    [string]$Package
  )

  $tool = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $tool)
  {
    $toolPath = Join-Path $HOME "go\bin\$Name.exe"
    if (Test-Path -LiteralPath $toolPath -PathType Leaf)
    {
      $tool = $toolPath
    }
  }

  if ($tool)
  {
    Write-Log "$Name already installed" 'Success'
    return
  }

  Write-Log "Installing $Name"

  if ($script:DRY_RUN)
  {
    Write-Log "DRY RUN: go install $Package"
    return
  }

  $goCmd = Get-Command go -ErrorAction SilentlyContinue
  if ($goCmd)
  {
    $goExe = $goCmd.Source
  }
  else
  {
    $goExe = Join-Path ${env:ProgramFiles} 'Go\bin\go.exe'
    if (-not (Test-Path -LiteralPath $goExe -PathType Leaf))
    {
      Stop-Dotfiles 'Required command not found: go'
    }
  }

  Invoke-Checked {
    & $goExe install $Package
  } "go install $Package"
}

function Invoke-go
{
  Write-Log 'Setting up go'

  Install-WingetPackage -Id 'GoLang.Go' -Name 'Go' -Command 'go'

  $goEnv = @{
    GOTMPDIR   = Join-Path $HOME 'go\tmp'
    GOCACHE    = Join-Path $env:LOCALAPPDATA 'go-build'
    GOMODCACHE = Join-Path $HOME 'go\pkg\mod'
  }

  foreach ($name in $goEnv.Keys)
  {
    $value = $goEnv[$name]

    if (-not (Test-Path -LiteralPath $value -PathType Container))
    {
      if ($script:DRY_RUN)
      {
        Write-Log "DRY RUN: create directory $value"
      }
      else
      {
        New-Item `
          -ItemType Directory `
          -Path $value `
          -Force |
          Out-Null
      }
    }

    if ($script:DRY_RUN)
    {
      Write-Log "DRY RUN: set user environment variable $name=$value"
    }
    else
    {
      [Environment]::SetEnvironmentVariable(
        $name,
        $value,
        [EnvironmentVariableTarget]::User
      )

      Set-Item -Path "Env:$name" -Value $value
    }
  }

  Install-GoTool -Name 'gopls' -Package 'golang.org/x/tools/gopls@latest'
  Install-GoTool -Name 'govulncheck' -Package 'golang.org/x/vuln/cmd/govulncheck@latest'
  Install-GoTool -Name 'golangci-lint' -Package 'github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.14.0'

  Write-Log 'Go setup complete' 'Success'
}
