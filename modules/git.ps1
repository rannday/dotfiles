Set-StrictMode -Version Latest

function Invoke-git
{
  Write-Log 'Setting up git'

  Install-WingetPackage -Id 'Git.Git' -Name 'Git' -Command 'git'

  $gitDir = Join-Path $script:CONF_DIR 'git'
  Assert-Directory $gitDir

  foreach ($file in @('.gitconfig', '.gitconfig-varda'))
  {
    $source = Join-Path $gitDir $file
    $target = Join-Path $HOME $file

    Install-UserFile -Source $source -Destination $target
    Write-Log "Installed git config: $target" 'Success'
  }
}
