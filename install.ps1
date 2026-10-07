Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Main
{
  $script:BASE_DIR = $PSScriptRoot
  $script:LIB_DIR = Join-Path $script:BASE_DIR 'lib'
  $script:MODULE_DIR = Join-Path $script:BASE_DIR 'modules'
  $script:CONF_DIR = Join-Path $script:BASE_DIR 'confs'

  . (Join-Path $script:LIB_DIR 'core.ps1')
  . (Join-Path $script:LIB_DIR 'winget.ps1')

  Initialize-Dotfiles @args

  Assert-Winget
  #Update-WingetSources

  Invoke-DotfilesModule shell
  Invoke-DotfilesModule git
  Invoke-DotfilesModule ssh
  Invoke-DotfilesModule go
  Invoke-DotfilesModule node
  Invoke-DotfilesModule uv
  Invoke-DotfilesModule docker
  Invoke-DotfilesModule codex
  Invoke-DotfilesModule grok
  #Invoke-DotfilesModule antigravity
  Invoke-DotfilesModule caveman
  Invoke-DotfilesModule gitkraken-cli
  Invoke-DotfilesModule fff_mcp
  Invoke-DotfilesModule serena
  Invoke-DotfilesModule zed
  #Invoke-DotfilesModule alacritty
  #Invoke-DotfilesModule zellij

  Write-Log 'All done' 'Success'
}

if ($MyInvocation.InvocationName -eq '.')
{
  throw 'Run install.ps1 directly; do not dot-source it.'
}

Main @args
