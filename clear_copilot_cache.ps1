# Close VS Code first, then run this:
param(
    [string]$TargetPath = "C:\lada ai"
)

Write-Host "Clearing Copilot Edits cache..." -ForegroundColor Yellow
$copilotPath = "$env:APPDATA\Code\User\workspaceStorage"
if (Test-Path $copilotPath) {
  Get-ChildItem $copilotPath -Recurse -Filter "*copilot*" | Remove-Item -Force -ErrorAction SilentlyContinue
  Write-Host "Cleared!" -ForegroundColor Green
} else {
  Write-Host "Path not found" -ForegroundColor Red
}

Write-Host "
Now restart VS Code and open $TargetPath" -ForegroundColor Cyan
