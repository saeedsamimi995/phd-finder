# Registers a daily 08:00 task. Run once from PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1

$script = "D:\Projects\phd finder\scripts\run_daily.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName "PhDFinderDaily" -Action $action -Trigger $trigger -Settings $settings -Description "Discover and package open PhD positions. Does not send email." -Force
Write-Host "Registered scheduled task PhDFinderDaily at 08:00."
