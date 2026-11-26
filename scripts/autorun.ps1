<#
.SYNOPSIS
Work through docs/autonomous-plan.md with one fresh Claude Code session per task.

.DESCRIPTION
Each session starts with an empty context, reads the plan and docs/progress.md,
does one task (or resumes an unfinished one) and exits. Everything a session needs
to know is in those files, so no context carries over between tasks.

The run stops when a session replies "ALL DONE", after -MaxSessions sessions, or
when sessions keep failing (for example because the usage limit is reached).
Paid API calls stay off in every session: UNAPPLY_ALLOW_API_CALLS is forced to 0.

Each session's output is written to its own log file in -LogDir.

.EXAMPLE
pwsh scripts/autorun.ps1
pwsh scripts/autorun.ps1 -MaxSessions 10 -Effort xhigh
pwsh scripts/autorun.ps1 -WaitForReset   # keep waiting for the usage limit to reset
#>
param(
    [int]$MaxSessions = 40,
    [string]$Model = "opus",
    [string]$Effort = "high",
    # After a failed session: retry this many times, this many minutes apart.
    [int]$MaxRetries = 2,
    [int]$RetryMinutes = 10,
    # Keep retrying every 30 minutes instead, until the usage limit resets.
    [switch]$WaitForReset,
    [string]$LogDir = (Join-Path $env:USERPROFILE "unapply-autorun")
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Node.js is installed per user; sessions need it on PATH for the frontend.
$node = Join-Path $env:LOCALAPPDATA "Programs\node\node-v26.13.1-win-x64"
if (Test-Path $node) { $env:Path = "$node;$env:Path" }
# Paid API calls stay off, whatever .env says (the CLI doesn't override set variables).
$env:UNAPPLY_ALLOW_API_CALLS = "0"
New-Item -ItemType Directory -Force $LogDir | Out-Null

$prompt = @'
You are one session in an unattended run; the user is away and can't answer.
Read docs/autonomous-plan.md and follow its ground rules exactly, then read
docs/progress.md.

If an earlier session left an unfinished task (an unmerged branch, or work noted in
the progress log), finish that first. Otherwise take the first task in the plan that
isn't done or blocked; once every task is done or blocked, take the next piece of
work allowed under "After the plan".

Do that one task completely: implement it, test it, merge as the plan says, mark it
done in the plan, and add its line to docs/progress.md. Then stop: the next task
starts in a fresh session.

If nothing is left that the plan allows, reply with exactly: ALL DONE
'@

$failures = 0
$session = 0
while ($session -lt $MaxSessions) {
    $session++
    $stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $log = Join-Path $LogDir ("session_{0:d3}_{1}.log" -f $session, $stamp)
    Write-Host "[$(Get-Date -Format HH:mm)] session $session -> $log"

    claude -p $prompt --model $Model --effort $Effort `
        --permission-mode auto --permission-prompts none *> $log
    $exit = $LASTEXITCODE

    $tail = (Get-Content $log -Tail 30 -ErrorAction SilentlyContinue) -join "`n"
    if ($tail -match "ALL DONE") {
        Write-Host "Nothing left to do. Stopping."
        break
    }
    if ($exit -eq 0) {
        $failures = 0
        continue
    }

    # A failed session doesn't count towards -MaxSessions.
    $session--
    $failures++
    if ($WaitForReset) {
        Write-Host "Session failed (exit $exit). Waiting 30 minutes, then trying again."
        Start-Sleep -Seconds (30 * 60)
    }
    elseif ($failures -le $MaxRetries) {
        Write-Host "Session failed (exit $exit). Retry $failures of $MaxRetries in $RetryMinutes minutes."
        Start-Sleep -Seconds ($RetryMinutes * 60)
    }
    else {
        Write-Host "Session failed (exit $exit) $failures times in a row, probably the usage limit. Stopping."
        break
    }
}
Write-Host "Done. Logs: $LogDir. Progress: docs/progress.md."
