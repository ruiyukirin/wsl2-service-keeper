# WSL2 服务保活 — 完整排坑清单

> 基于真实生产环境排障经验整理，每个坑都经过至少 2 次以上尝试才确认。

---

## 坑 1：WSL 空闲自动停止（最常见）

### 症状
- WSL2 中运行的 systemd 服务每隔 1-2 分钟收到 SIGTERM 后退出
- `journalctl --user -u <service>` 显示 `Received SIGTERM`
- 手动重启后，几分钟后再次死掉

### 根因
WSL2 在发行版空闲时自动停止，导致 systemd 的 `default.target` 被停掉，所有 `WantedBy=default.target` 的 user service 都会被 SIGTERM。

### 解决
在 `C:\Users\<username>\.wslconfig` 中添加：
```ini
[general]
instanceIdleTimeout=-1
```
然后 `wsl --shutdown` 重启 WSL。

### 验证
启动服务后等待 5+ 分钟，检查服务是否仍在运行。

---

## 坑 2：只设 vmIdleTimeout 不够

### 症状
已经设置了 `vmIdleTimeout=-1`，但服务仍然被 SIGTERM 杀掉。

### 根因
WSL2 有两层独立的空闲超时：

| 配置项 | 作用域 | 所在段落 | 功能 |
|--------|--------|----------|------|
| `vmIdleTimeout` | WSL2 虚拟机 | `[wsl2]` | 保持 VM 进程存活 |
| `instanceIdleTimeout` | 发行版 | `[general]` | 阻止发行版停止 |

**只设 `vmIdleTimeout=-1` 只保持虚拟机存活，发行版仍然会被停止**。必须同时设置 `instanceIdleTimeout=-1`。

### 解决
```ini
[general]
instanceIdleTimeout=-1

[wsl2]
vmIdleTimeout=-1
```

### 判断方法
- 如果 `wsl -l -v` 显示 distro 状态为 `Stopped` 但之前没有手动停止 → `instanceIdleTimeout` 没设
- 如果 `wsl -l -v` 显示 distro 状态为 `Running` 但服务已死 → 检查其他原因

---

## 坑 3：SYSTEM 账户无法运行 wsl.exe

### 症状
- Windows 任务计划执行 `wsl.exe` 返回码 `-1`
- 任务计划历史显示"操作成功完成"但 WSL 没有启动

### 根因
Windows Scheduled Task 默认以 SYSTEM 账户运行。SYSTEM 账户**无法调用 `wsl.exe`**，会静默返回 -1。

### 解决
使用 S4U（Service for User）模式，以实际用户身份运行：
```powershell
$principal = New-ScheduledTaskPrincipal -UserId "HOSTNAME\username" -LogonType S4U -RunLevel Highest
```

### 验证
```powershell
# 检查任务的运行账户
(Get-ScheduledTask -TaskName "YourTask").Principal | Format-List
# 应显示 LogonType: S4U，UserId: 实际用户名
```

---

## 坑 4：电池模式阻止任务运行

### 症状
- 笔记本电脑拔掉电源后，任务计划不执行
- 或切换到电池后，正在运行的任务被停止

### 根因
Windows 任务计划默认在电池模式下：
- 不启动新任务
- 切换到电池时停止正在运行的任务

### 解决
```powershell
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
```

---

## 坑 5：CRLF 换行符导致 bash 脚本静默失败

### 症状
- 在 Windows 上创建/编辑的 bash 脚本，在 WSL 中执行不报错但功能异常
- 典型表现：条件判断不生效、变量赋值异常

### 根因
Windows 文本编辑器保存文件时使用 CRLF（`\r\n`）换行符。bash 将 `\r` 视为行尾的一部分，导致字符串比较和命令解析异常。

### 解决
```bash
# 修复单个文件
sed -i 's/\r$//' /path/to/script.sh

# 修复目录下所有 .sh 文件
find /path/to/dir -name "*.sh" -exec sed -i 's/\r$//' {} +
```

### 预防
- VS Code 右下角切换为 LF 换行
- Git 设置：`git config --global core.autocrlf false`

---

## 坑 6：pkill -f 误杀自身进程

### 症状
- 启动脚本中用 `pkill -f 'service_name'` 检查进程，结果杀掉了正在运行的目标进程

### 根因
`pkill -f` 匹配命令行中的字符串，存在时序竞态：
1. 新脚本启动，执行 `pkill -f 'hermes_cli.main'`
2. 此时旧进程仍在运行 → 旧进程被杀
3. 新进程启动后，下一个检查周期可能杀掉自己

### 解决
用 `systemctl --user is-active` 替代 `pkill -f`：
```bash
if systemctl --user is-active --quiet my-service.service 2>/dev/null; then
    echo "Service already running"
else
    systemctl --user start my-service.service
fi
```

---

## 坑 7：systemd 服务中使用 --replace 参数

### 症状
- 服务看似启动成功，但很快退出
- `journalctl` 显示旧实例被新实例终止

### 根因
`--replace` 参数让新实例主动杀死旧实例。在 systemd 管理下，这会导致：
1. systemd 启动新进程
2. 新进程用 `--replace` 杀掉自己（因为自己就是"旧实例"）
3. systemd 检测到进程退出，触发 Restart

### 解决
从 `.service` 文件中移除 `--replace` 参数，让 systemd 自己管理进程生命周期。

---

## 坑 8：PowerShell RunAs 输出丢失

### 症状
- 使用 `Start-Process -Verb RunAs` 启动管理员脚本，但无法获取输出
- 在 `-Verb RunAs` 中使用内联脚本，输出不会回传到调用方

### 根因
`Start-Process -Verb RunAs` 通过 UAC 提升启动新进程，新进程的 stdout/stderr 与调用方完全隔离。

### 解决
1. 使用独立的 `.ps1` 文件而非内联脚本
2. 在脚本中将输出重定向到文件：
```powershell
Start-Process -FilePath "powershell.exe" -ArgumentList "-File C:\path\to\script.ps1 > C:\path\to\output.txt 2>&1" -Verb RunAs -Wait
```

---

## 坑 9：启动脚本缺少 sleep infinity

### 症状
- 启动脚本执行完毕后，WSL 发行版很快被停止
- 即使设置了 `instanceIdleTimeout=-1`，脚本退出后 WSL 仍可能被标记为空闲

### 根因
当 WSL 中没有任何前台进程时，即使配置了 `instanceIdleTimeout=-1`，某些场景下 WSL 仍可能判定为空闲。

### 解决
在启动脚本末尾添加：
```bash
exec sleep infinity
```
这会让脚本永远保持前台运行，WSL 不会认为自身空闲。

---

## 坑 10：ExecutionTimeLimit 用 [TimeSpan]::Zero 报错

### 症状
- 注册任务计划时使用 `-ExecutionTimeLimit ([TimeSpan]::Zero)` 报 XML 格式错误

### 根因
某些 Windows 版本的 Task Scheduler XML schema 不接受 `[TimeSpan]::Zero` 序列化后的格式。

### 解决
使用字符串 `'PT0S'` 代替：
```powershell
-ExecutionTimeLimit 'PT0S'
```
这是 ISO 8601 duration 格式，Task Scheduler 原生支持。

---

## 坑 11：安卓模拟器关闭虚拟化组件（最隐蔽）

### 症状
- 安装安卓模拟器（如夜神 NoxPlayer、雷电、逍遥等）后，WSL2 完全无法启动
- `wsl --status` 提示"当前计算机配置不支持 WSL2"，要求启用"虚拟机平台"可选组件
- 任务计划运行 `wsl.exe` 返回 `-1`
- `wsl -d <distro> -- echo test` 直接返回 exit code 1
- 重启电脑后问题依旧

### 根因
基于 VirtualBox/QEMU 的安卓模拟器（夜神、雷电、逍遥、BlueStacks 旧版等）与 Hyper-V 互斥。安装时会自动执行以下破坏性操作：

| 被修改项 | 修改内容 | 影响 |
|---|---|---|
| `bcdedit hypervisorlaunchtype` | `Auto` → `Off` | Hyper-V 被完全禁用 |
| `VirtualMachinePlatform` 可选组件 | 启用 → 禁用 | WSL2 依赖的虚拟机平台消失 |
| `Microsoft-Windows-Subsystem-Linux` 可选组件 | 启用 → 禁用 | WSL1 也不可用 |

**注意**：卸载模拟器时**不会自动恢复**这些设置！必须手动修复。

### 解决

**第一步**：卸载安卓模拟器，并清理残留目录（常见残留路径）：
```
D:\Program Files\Nox
C:\Users\<username>\AppData\Local\Nox
```

**第二步**：以管理员权限执行以下三条修复命令：

```powershell
# 1. 恢复 Hyper-V 启动类型
bcdedit /set hypervisorlaunchtype auto

# 2. 重新启用虚拟机平台
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 3. 重新启用 WSL
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
```

**第三步**：重启电脑。

### 验证
```powershell
# 检查 hypervisorlaunchtype 应为 Auto
bcdedit /enum | findstr hypervisor

# 检查 WSL 状态
wsl --status

# 测试 WSL 是否可用
wsl -d <distro> -- echo "OK"
```

### 预防
- **不要安装基于 VirtualBox/QEMU 的安卓模拟器**（夜神、雷电、逍遥等旧版）
- 如果必须用安卓模拟器，选择基于 Hyper-V 的版本：
  - MuMu Pro
  - 雷电9（Hyper-V 版）
  - BlueStacks 5+（Hyper-V 模式）
- 安装前备份 `bcdedit /enum` 输出，安装后对比差异
- 使用 Windows 11 的 WSA（Windows Subsystem for Android）替代安卓模拟器

### 快速诊断流程
如果用户报告"WSL2 突然不能用"且近期安装过安卓模拟器：
1. `bcdedit /enum | findstr hypervisor` → 如果是 `Off`，确认被模拟器关闭
2. `wsl --status` → 检查是否提示虚拟机平台未启用
3. 执行三条修复命令 + 重启
