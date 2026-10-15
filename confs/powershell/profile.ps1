# Save command history after each command
if (Get-Command Set-PSReadLineOption -ErrorAction SilentlyContinue)
{
  Set-PSReadLineOption -HistorySaveStyle SaveIncrementally
}

Remove-Alias -Name history -ErrorAction SilentlyContinue

function history
{
  Get-Content -LiteralPath (Get-PSReadLineOption).HistorySavePath
}
