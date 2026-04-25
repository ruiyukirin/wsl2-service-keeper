# WSL2 Service Keeper 🔧

[English](README.md) | **中文**

> **让 WSL2 中的 systemd 服务不再崩溃，开机自动启动。**

这是一个诞生于真实生产环境排障的 [WorkBuddy](https://www.codebuddy.cn/) Skill——这里记录的每一个坑，都是在实际运行中踩到并解决的。

## 问题是什么？

WSL2 对长期运行的服务有一个致命缺陷：**空闲时自动停止发行版和虚拟机**，杀死所有 systemd 服务。而配置 Windows 开机自启动也有不少隐蔽的坑。

**你可能遇到过的症状：**

- WSL2 服务运行 1-2 分钟后被 SIGTERM 杀掉
- 明明设了 `vmIdleTimeout=-1`，服务还是被杀
- Windows 任务计划执行 `wsl.exe` 返回 `-1`
- 笔记本拔电源后 WSL 服务就挂了

## 快速修复

### 1. 修改 `.wslconfig`（防止空闲停止）

创建或编辑 `C:\Users\<用户名>\.wslconfig`：

```ini
[general]
# ⚠️ 这是最关键的配置 — 阻止发行版空闲停止
instanceIdleTimeout=-1

[wsl2]
# 保持虚拟机进程存活
vmIdleTimeout=-1
```

然后执行：`wsl --shutdown` 并重启 WSL。

> **核心要点**：只设 `vmIdleTimeout=-1` **不够**！虚拟机虽然活着，但发行版仍会停止 → systemd 的 `default.target` 被停掉 → 所有 user service 收到 SIGTERM。`instanceIdleTimeout=-1` 才是阻止发行版停止的关键配置。

### 2. 创建启动脚本

```bash
#!/bin/bash
if systemctl --user is-active --quiet your-service.service 2>/dev/null; then
    echo "Service already running"
else
    systemctl --user start your-service.service
fi
# 保持 WSL 存活 — 不能删这行！
exec sleep infinity
```

### 3. 注册 Windows 任务计划（S4U 模式）

```powershell
$principal = New-ScheduledTaskPrincipal -UserId "主机名\用户名" -LogonType S4U -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 'PT0S' -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu-22.04 -- bash /home/user/start_service.sh"
$trigger = New-ScheduledTaskTrigger -AtLogon

Register-ScheduledTask -TaskName "WSL-AutoStart" -Principal $principal -Action $action -Trigger $trigger -Settings $settings -Force
```

> **为什么用 S4U？** SYSTEM 账户**无法**运行 `wsl.exe`，会静默返回 `-1`。

## 作为 WorkBuddy Skill 安装

1. 下载或克隆本仓库
2. 将 `wsl2-service-keeper` 文件夹复制到 `~/.workbuddy/skills/`
3. 重启 WorkBuddy — Skill 会自动识别

```bash
# 快速安装
git clone https://github.com/ruiyukirin/wsl2-service-keeper.git
cp -r wsl2-service-keeper ~/.workbuddy/skills/
```

## 脚本工具

| 脚本 | 说明 |
|------|------|
| `scripts/create_startup_script.py` | 生成 WSL 启动脚本（含服务检查和保活） |
| `scripts/register_autostart.py` | 生成 PowerShell 任务计划注册脚本 |
| `scripts/diagnose.py` | 诊断 WSL2 服务问题：.wslconfig、服务状态、CRLF、任务配置 |

### 使用示例

```bash
# 生成启动脚本
python scripts/create_startup_script.py --service my-api --output ./start_my_api.sh

# 生成任务计划注册脚本
python scripts/register_autostart.py --task-name MyAPI-AutoStart --distro Ubuntu-22.04 --script-path /home/user/start_my_api.sh --user "DESKTOP\username"

# 诊断问题
python scripts/diagnose.py --distro Ubuntu-22.04 --service my-api --task-name MyAPI-AutoStart
```

## 踩坑清单

完整版见 [10 个已知坑点](references/pitfalls.md)，包含症状、根因和解决方案。

| # | 坑点 | 核心教训 |
|---|------|----------|
| 1 | WSL 空闲自动停止 | 设置 `instanceIdleTimeout=-1` |
| 2 | 只设 vmIdleTimeout 不够 | 必须同时设 `instanceIdleTimeout` 和 `vmIdleTimeout` |
| 3 | SYSTEM 账户无法运行 wsl.exe | 用 S4U 模式以实际用户运行 |
| 4 | 电池模式杀死任务 | 设置 `AllowStartIfOnBatteries` + `DontStopIfGoingOnBatteries` |
| 5 | bash 脚本 CRLF 换行符 | `sed -i 's/\r$//' script.sh` |
| 6 | `pkill -f` 误杀目标进程 | 改用 `systemctl --user is-active` |
| 7 | `--replace` 参数冲突 | 从 systemd 服务文件中移除 |
| 8 | RunAs 输出丢失 | 用独立 .ps1 文件而非内联脚本 |
| 9 | 缺少 `sleep infinity` | WSL 即使设了空闲超时也可能停止 |
| 10 | `[TimeSpan]::Zero` 报 XML 错误 | 用字符串 `'PT0S'` 代替 |

## 兼容性

- ✅ Windows 10 / Windows 11
- ✅ 启用 systemd 的 WSL2（Ubuntu 22.04+ 等）
- ✅ WorkBuddy（腾讯云 CodeBuddy）智能体平台

## 许可证

MIT
