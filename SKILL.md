---
name: wsl2-service-keeper
description: >
  WSL2 服务保活与开机自启动配置专家。This skill should be used when the user needs to:
  (1) keep WSL2 services (systemd user services) alive without being killed by idle timeout,
  (2) configure Windows Scheduled Task to auto-start WSL2 services on boot,
  (3) troubleshoot WSL2 service crashes caused by SIGTERM, systemd target stops, or distribution idle stops,
  (4) configure .wslconfig for persistent WSL2 instances,
  (5) debug "wsl.exe returns -1" or "SYSTEM account cannot run wsl.exe" errors in Task Scheduler,
  (6) set up S4U (Service for User) scheduled tasks for WSL2 auto-start,
  (7) fix WSL2 broken by Android emulators (NoxPlayer, LDPlayer, etc.) that disable Hyper-V and VirtualMachinePlatform,
  (8) diagnose "WSL2 not supported" errors after installing VirtualBox-based software.
  Trigger phrases: WSL保活, WSL自启动, WSL服务崩溃, systemd SIGTERM, WSL空闲停止,
  wsl.exe -1, 任务计划WSL, instanceIdleTimeout, vmIdleTimeout, WSL2开机启动,
  WSL keep alive, WSL auto start, WSL service crash, WSL idle stop,
  安卓模拟器冲突, 夜神模拟器, NoxPlayer, Hyper-V被关闭, 虚拟机平台未启用,
  WSL2突然不能用, bcdedit hypervisorlaunchtype.
---

# WSL2 Service Keeper

Configure WSL2 to keep systemd services alive and auto-start them on Windows boot.

## Overview

WSL2 has a critical flaw for long-running services: it automatically stops idle distributions and the entire VM, killing all systemd services. Additionally, configuring auto-start on Windows boot requires specific Task Scheduler settings that are non-obvious. This skill provides battle-tested solutions for both problems.

## When to Use This Skill

- User reports WSL2 services dying after a few minutes (SIGTERM → exit)
- User wants WSL2 services to survive idle periods
- User wants WSL2 services to auto-start when Windows boots
- User encounters `wsl.exe` returning `-1` from Scheduled Tasks
- User needs to configure `.wslconfig` for persistent WSL2 instances
- User asks about `instanceIdleTimeout` vs `vmIdleTimeout`
- User reports WSL2 suddenly stopped working after installing Android emulator (NoxPlayer, LDPlayer, etc.)
- User sees "当前计算机配置不支持 WSL2" or "Virtual Machine Platform is not enabled"
- User's `bcdedit hypervisorlaunchtype` shows `Off` and they don't know why

## Core Knowledge: The Two-Layer Timeout Problem

WSL2 has **two independent** idle timeout mechanisms. **Both must be disabled** for services to survive:

| Config Key | Scope | Location | What it does |
|---|---|---|---|
| `vmIdleTimeout` | WSL2 VM (hypervisor) | `[wsl2]` section | Keeps the VM process alive |
| `instanceIdleTimeout` | Distribution (Linux) | `[general]` section | Keeps the distro running inside the VM |

**Critical**: Setting only `vmIdleTimeout=-1` is **NOT sufficient**. The VM stays alive but the distribution stops → systemd default.target is deactivated → all user services receive SIGTERM and exit. `instanceIdleTimeout=-1` is the key config that prevents the distribution from stopping.

## Workflow

### Phase 1: Diagnose the Problem

1. **Check if WSL2 itself is functional** (do this FIRST):
   - Run `wsl -d <distro> -- echo "test"` — if this fails, WSL2 is broken at the platform level
   - Run `wsl --status` — look for "Virtual Machine Platform is not enabled" or similar errors
   - Run `bcdedit /enum | findstr hypervisor` (needs admin) — if `hypervisorlaunchtype` is `Off`, Hyper-V was disabled
   - **Common cause**: Android emulators (NoxPlayer, LDPlayer, MuMu, etc.) disable Hyper-V and VirtualMachinePlatform on install
   - If WSL2 platform is broken, skip to **Phase 1.5: Fix Virtualization** below

2. Check if the user's WSL2 service is dying due to idle timeout:
   - Run `wsl -d <distro> -- systemctl --user status <service>` to see if service is inactive
   - Check `wsl -d <distro> -- journalctl --user -u <service> --no-pager -n 50` for SIGTERM signals
   - If SIGTERM appears and `default.target` is stopped, this is the idle timeout problem

3. Check current `.wslconfig`:
   - Read `C:\Users\<username>\.wslconfig` (or the equivalent path)
   - Verify both `instanceIdleTimeout=-1` and `vmIdleTimeout=-1` are present

### Phase 1.5: Fix Virtualization (Android Emulator Conflict)

If Phase 1 step 1 reveals that WSL2 itself is broken (hypervisorlaunchtype=Off, VirtualMachinePlatform disabled):

**Root cause**: VirtualBox/QEMU-based Android emulators (NoxPlayer, LDPlayer, Xiaoyao, BlueStacks 4-) disable Hyper-V and virtualization components on install. Uninstalling the emulator does NOT restore these settings.

**Fix** (all commands require admin/elevated PowerShell):

```powershell
# 1. Restore Hyper-V launch type
bcdedit /set hypervisorlaunchtype auto

# 2. Re-enable Virtual Machine Platform
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 3. Re-enable WSL
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
```

**Then restart the computer.** After restart, WSL2 should work again. Continue with Phase 2.

**Quick diagnostic shortcut**: If the user mentions recently installing an Android emulator, go directly to the three fix commands above.

**Emulator compatibility reference**:

| Emulator | Hyper-V Compatible | Impact on WSL2 |
|---|---|---|
| NoxPlayer (夜神) | ❌ No | Breaks WSL2 completely |
| LDPlayer (雷电) 旧版 | ❌ No | Breaks WSL2 completely |
| Xiaoyao (逍遥) | ❌ No | Breaks WSL2 completely |
| BlueStacks 4- | ❌ No | Breaks WSL2 completely |
| MuMu Pro | ✅ Yes | Coexists with WSL2 |
| LDPlayer 9 (Hyper-V) | ✅ Yes | Coexists with WSL2 |
| BlueStacks 5+ (Hyper-V) | ✅ Yes | Coexists with WSL2 |
| Windows Subsystem for Android | ✅ Yes | Coexists with WSL2 |

### Phase 2: Fix Idle Timeout (Keep Services Alive)

1. Write or update `.wslconfig` at `C:\Users\<username>\.wslconfig`:

```ini
[general]
instanceIdleTimeout=-1

[wsl2]
vmIdleTimeout=-1
```

2. Add any other WSL2 settings the user needs (e.g., `guiApplications=false`, memory limits)

3. Apply the config:
   - Run `wsl --shutdown` to stop all WSL instances
   - The next WSL launch will use the new config

4. Verify: start WSL, launch the service, wait 5+ minutes, check if it's still running

### Phase 3: Configure Auto-Start on Boot

1. Create a startup script in WSL. Use `scripts/create_startup_script.py` to generate one, or create manually:

```bash
#!/bin/bash
# Check if service is already running
if systemctl --user is-active --quiet <service-name>.service 2>/dev/null; then
    echo "<service-name> already running, skipping."
else
    echo "Starting <service-name>..."
    systemctl --user start <service-name>.service
fi
# Keep WSL alive - DO NOT REMOVE
exec sleep infinity
```

**Important**: The `exec sleep infinity` at the end is **mandatory**. Without it, the script exits, WSL considers itself idle, and may stop even with `instanceIdleTimeout=-1` set.

2. Fix CRLF line endings (scripts created/edited on Windows will have `\r`):
   ```bash
   sed -i 's/\r$//' /path/to/startup_script.sh
   chmod +x /path/to/startup_script.sh
   ```

3. Register a Windows Scheduled Task using `scripts/register_autostart.py` or manually:

```powershell
$taskName = "WSL-AutoStart-<service>"
$distro = "Ubuntu-22.04"  # adjust to user's distro
$scriptPath = "/home/<user>/start_<service>.sh"
$user = "<hostname>\<windows-username>"

$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit 'PT0S' `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d $distro -- bash $scriptPath"
$trigger = New-ScheduledTaskTrigger -AtLogon

Register-ScheduledTask -TaskName $taskName -Principal $principal -Action $action -Trigger $trigger -Settings $settings -Force
```

**Key points for the Scheduled Task**:
- **Must use S4U (Service for User) logon type** — SYSTEM account cannot run `wsl.exe` (returns -1)
- **Must set `AllowStartIfOnBatteries`** — otherwise the task won't run on laptops
- **Must set `DontStopIfGoingOnBatteries`** — otherwise the task stops when switching to battery
- **`ExecutionTimeLimit` should use string `'PT0S'`** — `[TimeSpan]::Zero` causes XML format errors in some Windows versions
- **`RestartCount` and `RestartInterval`** — auto-retry on transient failures

4. Verify the task: `Start-ScheduledTask -TaskName $taskName` then check WSL and the service

### Phase 4: Validate End-to-End

1. Restart the computer
2. Wait 1-2 minutes after login
3. Check: `wsl -d <distro> -- systemctl --user status <service>`
4. Check: the service is responding (e.g., bot responds to messages, web server serves requests)

## Scripts

### `scripts/create_startup_script.py`
Generate a WSL startup script with service check and keep-alive. Run with:
```bash
python scripts/create_startup_script.py --service <name> [--distro <distro>] [--output <path>]
```

### `scripts/register_autostart.py`
Register a Windows Scheduled Task for WSL2 auto-start. Run with PowerShell:
```powershell
python scripts/register_autostart.py --task-name <name> --distro <distro> --script-path <path> --user <domain\username>
```

### `scripts/diagnose.py`
Diagnose WSL2 service issues: check .wslconfig, service status, recent journal entries. Run with:
```bash
python scripts/diagnose.py [--distro <distro>] [--service <name>]
```

## References

- `references/pitfalls.md` — Complete list of 11 known pitfalls with WSL2 services, symptoms, and solutions
- `references/wslconfig-reference.md` — Full `.wslconfig` configuration reference with explanations

## Anti-Patterns to Avoid

1. **Using `pkill -f` to check service status** — race conditions can kill the target process; use `systemctl --user is-active` instead
2. **Using `--replace` flag in systemd services** — causes new instances to kill old ones, conflicting with systemd's process management
3. **Using SYSTEM account for Scheduled Tasks** — `wsl.exe` returns -1; must use S4U with a real user account
4. **Omitting `exec sleep infinity` from startup scripts** — WSL may consider itself idle and stop
5. **Only setting `vmIdleTimeout`** — this keeps the VM alive but the distro still stops; `instanceIdleTimeout` is the critical setting
6. **Using `loginctl enable-linger` alone** — insufficient in WSL2; the distro stop event overrides linger
7. **Ignoring CRLF in bash scripts** — scripts edited on Windows silently fail due to `\r` characters
8. **Installing VirtualBox-based Android emulators alongside WSL2** — NoxPlayer, LDPlayer, Xiaoyao, etc. disable Hyper-V and VirtualMachinePlatform; uninstalling the emulator does NOT restore these settings; use Hyper-V compatible alternatives instead
