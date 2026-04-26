# WSL2 Service Keeper 🔧

**English** | [中文](README_CN.md)

> **Keep your WSL2 systemd services alive and auto-start them on Windows boot.**

A [WorkBuddy](https://www.codebuddy.cn/) skill born from real production debugging — every pitfall documented here was hit and solved in a live environment.

## The Problem

WSL2 has a critical flaw for long-running services: it **automatically stops idle distributions and VMs**, killing all systemd services. And configuring auto-start on Windows boot requires non-obvious Task Scheduler settings.

**Symptoms you might recognize:**

- Your WSL2 service dies after 1-2 minutes (SIGTERM → exit)
- `vmIdleTimeout=-1` is set but services still get killed
- Windows Scheduled Task runs `wsl.exe` but returns `-1`
- Your laptop kills WSL when you unplug the charger
- WSL2 suddenly stopped working after installing an Android emulator

## Quick Fix

### 1. Fix `.wslconfig` (prevent idle stops)

Create or edit `C:\Users\<username>\.wslconfig`:

```ini
[general]
# ⚠️ THIS IS THE CRITICAL ONE — prevents the distro from stopping
instanceIdleTimeout=-1

[wsl2]
# Keeps the VM process alive
vmIdleTimeout=-1
```

Then: `wsl --shutdown` and restart WSL.

> **Key insight**: Setting only `vmIdleTimeout=-1` is **NOT enough**. The VM stays alive but the distro stops → systemd `default.target` is deactivated → all user services receive SIGTERM. `instanceIdleTimeout=-1` is the critical setting.

### 2. Create a startup script

```bash
#!/bin/bash
if systemctl --user is-active --quiet your-service.service 2>/dev/null; then
    echo "Service already running"
else
    systemctl --user start your-service.service
fi
# KEEP WSL ALIVE — do not remove this!
exec sleep infinity
```

### 3. Register Windows Scheduled Task (S4U mode)

```powershell
$principal = New-ScheduledTaskPrincipal -UserId "HOSTNAME\username" -LogonType S4U -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 'PT0S' -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu-22.04 -- bash /home/user/start_service.sh"
$trigger = New-ScheduledTaskTrigger -AtLogon

Register-ScheduledTask -TaskName "WSL-AutoStart" -Principal $principal -Action $action -Trigger $trigger -Settings $settings -Force
```

> **Why S4U?** SYSTEM account **cannot** run `wsl.exe` — it silently returns `-1`.

## Android Emulator Conflict 🚨

VirtualBox/QEMU-based Android emulators (NoxPlayer, LDPlayer, Xiaoyao, BlueStacks 4-) **break WSL2 completely** by disabling Hyper-V and VirtualMachinePlatform. Uninstalling the emulator does **NOT** restore these settings.

**Quick fix** (run in elevated PowerShell, then restart):

```powershell
bcdedit /set hypervisorlaunchtype auto
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
```

| Emulator | Hyper-V Compatible |
|---|---|
| NoxPlayer (夜神) | ❌ Breaks WSL2 |
| LDPlayer (雷电) 旧版 | ❌ Breaks WSL2 |
| Xiaoyao (逍遥) | ❌ Breaks WSL2 |
| BlueStacks 4- | ❌ Breaks WSL2 |
| MuMu Pro | ✅ Coexists |
| LDPlayer 9 (Hyper-V) | ✅ Coexists |
| BlueStacks 5+ (Hyper-V) | ✅ Coexists |

## Install as WorkBuddy Skill

1. Download or clone this repo
2. Copy the `wsl2-service-keeper` folder to `~/.workbuddy/skills/`
3. Restart WorkBuddy — the skill will be auto-detected

```bash
# Quick install
git clone https://github.com/ruiyukirin/wsl2-service-keeper.git
cp -r wsl2-service-keeper ~/.workbuddy/skills/
```

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/create_startup_script.py` | Generate a WSL startup script with service check and keep-alive |
| `scripts/register_autostart.py` | Generate a PowerShell script to register a Scheduled Task |
| `scripts/diagnose.py` | Diagnose WSL2 service issues: virtualization status, .wslconfig, service status, CRLF, task config |

### Usage Examples

```bash
# Generate startup script
python scripts/create_startup_script.py --service my-api --output ./start_my_api.sh

# Generate Scheduled Task registration script
python scripts/register_autostart.py --task-name MyAPI-AutoStart --distro Ubuntu-22.04 --script-path /home/user/start_my_api.sh --user "DESKTOP\username"

# Diagnose issues
python scripts/diagnose.py --distro Ubuntu-22.04 --service my-api --task-name MyAPI-AutoStart
```

## Pitfalls Reference

Full list of [11 known pitfalls](references/pitfalls.md) with symptoms, root causes, and solutions.

| # | Pitfall | Key Lesson |
|---|---------|------------|
| 1 | WSL idle auto-stop | Set `instanceIdleTimeout=-1` |
| 2 | Only `vmIdleTimeout` not enough | Must set BOTH `instanceIdleTimeout` AND `vmIdleTimeout` |
| 3 | SYSTEM can't run `wsl.exe` | Use S4U mode with real user account |
| 4 | Battery mode kills task | Set `AllowStartIfOnBatteries` + `DontStopIfGoingOnBatteries` |
| 5 | CRLF in bash scripts | `sed -i 's/\r$//' script.sh` |
| 6 | `pkill -f` kills target | Use `systemctl --user is-active` instead |
| 7 | `--replace` flag conflicts | Remove from systemd service files |
| 8 | RunAs output lost | Use separate .ps1 file, not inline |
| 9 | Missing `sleep infinity` | WSL may stop even with idle timeout disabled |
| 10 | `[TimeSpan]::Zero` XML error | Use string `'PT0S'` instead |
| 11 | Android emulator breaks WSL2 | Fix `bcdedit` + re-enable VirtualMachinePlatform + WSL component |

## Compatibility

- ✅ Windows 10 / Windows 11
- ✅ WSL2 with systemd support (Ubuntu 22.04+, etc.)
- ✅ WorkBuddy (CodeBuddy) agent platform

## License

MIT
