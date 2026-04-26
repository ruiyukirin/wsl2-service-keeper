#!/usr/bin/env python3
"""
WSL2 Service Health Diagnostic Tool

Diagnoses common WSL2 service issues by checking:
1. .wslconfig settings (instanceIdleTimeout, vmIdleTimeout)
2. Service status via systemctl
3. Recent journal entries for SIGTERM signals
4. CRLF issues in bash scripts

Usage:
    python diagnose.py [--distro Ubuntu-22.04] [--service hermes-gateway]
"""

import argparse
import subprocess
import sys
import os


def run_cmd(cmd, check=False):
    """Run a command and return stdout."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]", -1
    except FileNotFoundError:
        return "[COMMAND NOT FOUND]", -1


def check_wslconfig():
    """Check .wslconfig for required settings."""
    print("=" * 60)
    print("📋 Checking .wslconfig")
    print("=" * 60)

    wslconfig_path = os.path.join(
        os.environ.get("USERPROFILE", os.path.expanduser("~")),
        ".wslconfig"
    )

    if not os.path.exists(wslconfig_path):
        print(f"❌ .wslconfig NOT FOUND at: {wslconfig_path}")
        print("   → Create it with instanceIdleTimeout=-1 and vmIdleTimeout=-1")
        return False

    print(f"✅ .wslconfig found at: {wslconfig_path}")
    with open(wslconfig_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Parse key settings
    has_instance_idle = "instanceIdleTimeout=-1" in content
    has_vm_idle = "vmIdleTimeout=-1" in content

    print(f"   instanceIdleTimeout=-1: {'✅' if has_instance_idle else '❌ MISSING'}")
    print(f"   vmIdleTimeout=-1:       {'✅' if has_vm_idle else '❌ MISSING'}")

    if not has_instance_idle:
        print()
        print("   ⚠️  CRITICAL: instanceIdleTimeout=-1 is missing!")
        print("   This is the #1 cause of WSL2 services dying after a few minutes.")
        print("   The distro will auto-stop on idle, killing all systemd services.")

    if not has_vm_idle:
        print()
        print("   ⚠️  vmIdleTimeout=-1 is missing.")
        print("   The WSL2 VM may shut down on idle.")

    return has_instance_idle and has_vm_idle


def check_service(distro, service):
    """Check systemd service status."""
    print()
    print("=" * 60)
    print(f"📋 Checking service: {service}")
    print("=" * 60)

    if not distro:
        print("⚠️  No distro specified, skipping service check.")
        return

    # Check if WSL is running
    wsl_check, code = run_cmd(["wsl.exe", "-d", distro, "--", "echo", "ok"])
    if code != 0 or "ok" not in wsl_check:
        print(f"❌ Cannot connect to WSL distro '{distro}'")
        print("   → Make sure WSL is installed and the distro name is correct")
        return

    # Service status
    status_out, status_code = run_cmd(
        ["wsl.exe", "-d", distro, "--", "systemctl", "--user", "status", f"{service}.service"]
    )
    print(f"   systemctl status exit code: {status_code}")
    if status_code == 0:
        print(f"   ✅ Service is ACTIVE")
    elif status_code == 3:
        print(f"   ❌ Service is INACTIVE")
    elif status_code == 1:
        print(f"   ⚠️  Service is FAILED or not found")

    # Show last 10 lines of status
    if status_out:
        for line in status_out.split("\n")[:10]:
            print(f"   {line}")

    # Check for SIGTERM in journal
    print()
    print("📋 Recent journal entries (last 20 lines):")
    journal_out, _ = run_cmd(
        ["wsl.exe", "-d", distro, "--", "journalctl", "--user",
         "-u", f"{service}.service", "--no-pager", "-n", "20"]
    )
    if journal_out:
        for line in journal_out.split("\n"):
            if "SIGTERM" in line or "Stopped" in line or "signal" in line.lower():
                print(f"   🔴 {line}")
            else:
                print(f"   {line}")


def check_script_crlf(distro, script_path):
    """Check for CRLF issues in bash scripts."""
    print()
    print("=" * 60)
    print("📋 Checking for CRLF issues")
    print("=" * 60)

    if not distro or not script_path:
        print("⚠️  No script path specified, skipping CRLF check.")
        return

    check_out, _ = run_cmd(
        ["wsl.exe", "-d", distro, "--", "bash", "-c",
         f"file {script_path} 2>/dev/null || echo 'NOT_FOUND'"]
    )
    print(f"   Script: {script_path}")
    print(f"   File type: {check_out}")

    if "CRLF" in check_out or "ASCII text" in check_out:
        if "CRLF" in check_out:
            print("   ❌ CRLF line endings detected! This will cause silent failures.")
            print(f"   → Fix with:  wsl -d {distro} -- sed -i 's/\\r$//' {script_path}")
        else:
            print("   ✅ LF line endings (OK)")

    # Check if script has sleep infinity
    sleep_check, _ = run_cmd(
        ["wsl.exe", "-d", distro, "--", "bash", "-c",
         f"grep -c 'sleep infinity' {script_path} 2>/dev/null || echo '0'"]
    )
    if sleep_check.strip() == "0":
        print(f"   ⚠️  Script does NOT contain 'sleep infinity'")
        print("   → Without it, WSL may consider itself idle and stop after the script exits")
    else:
        print(f"   ✅ Script contains 'sleep infinity' (OK)")


def check_scheduled_task(task_name):
    """Check if the scheduled task exists and is configured correctly."""
    print()
    print("=" * 60)
    print("📋 Checking Windows Scheduled Task")
    print("=" * 60)

    task_out, code = run_cmd(
        ["powershell.exe", "-NoProfile", "-Command",
         f"Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue | "
         f"Select-Object TaskName, State, @{N='User';E={{$_.Principal.UserId}}}, "
         f"@{N='LogonType';E={{$_.Principal.LogonType}}} | Format-List"]
    )

    if not task_out or "Microsoft.PowerShell" in task_out:
        print(f"   ❌ Scheduled task '{task_name}' NOT FOUND")
        print("   → Register one using the register_autostart.py script")
        return

    print(f"   Task: {task_name}")
    for line in task_out.split("\n"):
        line = line.strip()
        if line:
            print(f"   {line}")

    # Check for common misconfigurations
    task_xml, _ = run_cmd(
        ["powershell.exe", "-NoProfile", "-Command",
         f"(Get-ScheduledTask -TaskName '{task_name}').Actions[0] | "
         f"Select-Object Execute, Arguments | Format-List"]
    )
    if task_xml:
        for line in task_xml.split("\n"):
            line = line.strip()
            if line:
                print(f"   {line}")


def check_virtualization():
    """Check if Hyper-V and virtualization components are enabled."""
    print("=" * 60)
    print("📋 Checking Virtualization Status")
    print("=" * 60)

    issues = []

    # Check hypervisorlaunchtype via bcdedit (needs admin)
    bcdedit_out, bcdedit_code = run_cmd(
        ["powershell.exe", "-NoProfile", "-Command",
         "Start-Process cmd -ArgumentList '/c bcdedit /enum > $env:TEMP\\bcdedit_diag.txt 2>&1' "
         "-Verb RunAs -Wait; Get-Content $env:TEMP\\bcdedit_diag.txt -ErrorAction SilentlyContinue"]
    )
    if bcdedit_out and "hypervisorlaunchtype" in bcdedit_out.lower():
        for line in bcdedit_out.split("\n"):
            if "hypervisorlaunchtype" in line.lower():
                if "off" in line.lower():
                    print(f"   ❌ hypervisorlaunchtype = Off (should be Auto)")
                    print("   → This is usually caused by Android emulators (NoxPlayer, LDPlayer, etc.)")
                    issues.append("hypervisorlaunchtype=Off")
                elif "auto" in line.lower():
                    print(f"   ✅ hypervisorlaunchtype = Auto")
                else:
                    print(f"   ⚠️  hypervisorlaunchtype = {line.strip()}")
    else:
        print("   ⚠️  Cannot read bcdedit (may need admin privileges)")
        print("   → Try running manually: bcdedit /enum | findstr hypervisor")

    # Check WSL status for virtualization errors
    wsl_status, wsl_code = run_cmd(["wsl.exe", "--status"])
    if wsl_status:
        # Decode UTF-16-LE if needed
        try:
            if isinstance(wsl_status, bytes):
                wsl_status = wsl_status.decode("utf-16-le", errors="replace")
        except Exception:
            pass
        if "虚拟机平台" in wsl_status or "Virtual Machine Platform" in wsl_status.lower():
            print("   ❌ VirtualMachinePlatform is NOT enabled")
            print("   → Fix: dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart")
            issues.append("VirtualMachinePlatform disabled")
        if "Subsystem for Linux" in wsl_status:
            print("   ❌ Microsoft-Windows-Subsystem-Linux is NOT enabled")
            print("   → Fix: dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart")
            issues.append("WSL component disabled")

    # Quick test: can WSL actually run?
    wsl_test, test_code = run_cmd(["wsl.exe", "--", "echo", "ok"])
    if test_code != 0:
        print("   ❌ WSL2 is NOT functional (wsl.exe returns non-zero)")
        if not issues:
            print("   → Unknown cause, check Windows Event Viewer for details")
    else:
        print("   ✅ WSL2 is functional")

    if issues:
        print()
        print("   ⚠️  CRITICAL: Virtualization components are broken!")
        print("   This is likely caused by an Android emulator (NoxPlayer, LDPlayer, Xiaoyao, etc.)")
        print("   Fix all three issues and restart:")
        print("     1. bcdedit /set hypervisorlaunchtype auto")
        print("     2. dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart")
        print("     3. dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart")
        print("     4. Restart computer")

    return len(issues) == 0


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose WSL2 service issues"
    )
    parser.add_argument(
        "--distro", default=None,
        help="WSL distribution name (e.g., Ubuntu-22.04)"
    )
    parser.add_argument(
        "--service", default=None,
        help="systemd user service name (without .service suffix)"
    )
    parser.add_argument(
        "--script-path", default=None,
        help="Path to the startup script inside WSL (for CRLF check)"
    )
    parser.add_argument(
        "--task-name", default=None,
        help="Windows Scheduled Task name to check"
    )
    args = parser.parse_args()

    print("🔍 WSL2 Service Keeper — Diagnostic Report")
    print()

    # Phase 0: Virtualization check (most fundamental, do first)
    virt_ok = check_virtualization()

    # Phase 1: .wslconfig check (always relevant)
    config_ok = check_wslconfig()

    # Phase 2: Service check (if distro specified)
    if args.distro and args.service:
        check_service(args.distro, args.service)

    # Phase 3: CRLF check (if script path specified)
    if args.distro and args.script_path:
        check_script_crlf(args.distro, args.script_path)

    # Phase 4: Scheduled task check (if task name specified)
    if args.task_name:
        check_scheduled_task(args.task_name)

    # Summary
    print()
    print("=" * 60)
    print("📊 Summary")
    print("=" * 60)
    if not virt_ok:
        print("❌ Virtualization is BROKEN — fix this first (see Phase 1.5 in SKILL.md)")
        print("   This is usually caused by Android emulators disabling Hyper-V")
    if config_ok:
        print("✅ .wslconfig is correctly configured")
    else:
        print("❌ .wslconfig needs fixes — this is likely causing your service to die")


if __name__ == "__main__":
    main()
