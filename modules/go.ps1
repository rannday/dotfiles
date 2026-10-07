Set-StrictMode -Version Latest

function Install-Gopls
{
  $gopls = Get-Command gopls -ErrorAction SilentlyContinue
  if (-not $gopls)
  {
    $goplsPath = Join-Path $HOME 'go\bin\gopls.exe'
    if (Test-Path -LiteralPath $goplsPath -PathType Leaf)
    {
      $gopls = $goplsPath
    }
  }

  if ($gopls)
  {
    Write-Log 'gopls already installed' 'Success'
    return
  }

  Write-Log 'Installing gopls'

  if ($script:DRY_RUN)
  {
    Write-Log 'DRY RUN: go install golang.org/x/tools/gopls@latest'
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
    & $goExe install golang.org/x/tools/gopls@latest
  } 'go install golang.org/x/tools/gopls@latest'
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

  Install-Gopls

  Write-Log 'Go setup complete' 'Success'
}
