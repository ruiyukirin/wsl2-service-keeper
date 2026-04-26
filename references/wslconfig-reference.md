# .wslconfig 完整配置参考

> 适用于 WSL2，文件位置：`C:\Users\<username>\.wslconfig`

---

## 文件格式

INI 格式，使用节（section）和键值对：

```ini
[section-name]
key=value
```

修改后需执行 `wsl --shutdown` 再重启 WSL 才生效。

---

## [wsl2] 节

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `kernel` | string | 内置 | 自定义 Linux 内核路径 |
| `kernelCommandLine` | string | "" | 内核启动参数 |
| `memory` | string | 主机内存 50% | WSL2 VM 内存限制，如 `8GB`、`4096MB` |
| `processors` | int | 主机逻辑核心数 | 分配给 WSL2 的处理器数 |
| `swap` | string | 主机内存 25% | 交换空间大小，`0` 禁用 |
| `swapFile` | string | `%USERPROFILE%\AppData\Local\Temp\swap.vhdx` | 交换文件路径 |
| `localhostForwarding` | bool | true | 是否将 WSL 端口转发到 localhost |
| `guiApplications` | bool | true | 是否启用 WSLg GUI 应用支持 |
| `nestedVirtualization` | bool | true | 是否启用嵌套虚拟化 |
| `vmIdleTimeout` | int | 60000 (ms) | **VM 空闲超时**，`-1` 禁用 |
| `vmComputeScheme` | string | "auto" | VM 计算方案 |

---

## [general] 节

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `hostname` | string | 计算机名 | WSL 实例主机名 |
| `defaultUid` | int | 0 | 默认用户 UID |
| `networkingMode` | string | "nat" | 网络模式：`nat` / `mirrored` / `virtio` |
| `autoProxy` | bool | false | 是否自动继承 Windows 代理设置 |
| `instanceIdleTimeout` | int | 有默认值 (ms) | **发行版空闲超时**，`-1` 禁用 |

---

## 服务保活推荐配置

```ini
[general]
# 阻止发行版在空闲时自动停止（关键！）
instanceIdleTimeout=-1

[wsl2]
# 保持 VM 进程存活
vmIdleTimeout=-1
# 禁用 GUI 支持（减少资源占用，无桌面需求时推荐）
guiApplications=false
# 按需调整内存（如需限制）
# memory=8GB
# 按需调整处理器数
# processors=4
```

---

## instanceIdleTimeout vs vmIdleTimeout 详解

```
Windows Host
  └── WSL2 VM (vmIdleTimeout 控制)
       └── Ubuntu-22.04 (instanceIdleTimeout 控制)
            └── systemd
                 └── user services
```

| 场景 | vmIdleTimeout | instanceIdleTimeout | 结果 |
|------|:---:|:---:|------|
| 两个都没设 | ⏱️ 超时 | ⏱️ 超时 | VM 和发行版都可能停止 |
| 只设 vmIdleTimeout=-1 | ✅ VM 存活 | ⏱️ 超时 | VM 活着，但发行版仍会停止，服务被 SIGTERM |
| 只设 instanceIdleTimeout=-1 | ⏱️ 超时 | ✅ 发行版不停 | VM 可能停止导致发行版也被停 |
| **两个都设 -1** | ✅ VM 存活 | ✅ 发行版不停 | **服务持久运行** ✅ |

---

## 常见问题

### Q: 修改 .wslconfig 后不生效？
A: 必须执行 `wsl --shutdown` 完全关闭所有 WSL 实例，然后重新启动。

### Q: instanceIdleTimeout 的默认值是多少？
A: 微软未公开精确默认值，实测大约 1 分钟左右。设为 `-1` 禁用。

### Q: 设了 instanceIdleTimeout=-1 后 WSL 会占用大量内存吗？
A: 不会。它只是阻止空闲停止，WSL 仍然按 `.wslconfig` 中的 `memory` 设置使用内存。

### Q: 可以用 `dbus-launch true` 替代 sleep infinity 保活吗？
A: 可以，但 `sleep infinity` 更简洁明确。`dbus-launch true` 是社区方案，原理相同——保持一个前台进程运行。

### Q: mirrored 网络模式和 nat 模式哪个好？
A: `mirrored` 模式（Windows 11 22H2+）让 WSL 和 Windows 共享网络栈，localhost 访问更简单。`nat` 模式是传统模式，兼容性更好。按需选择。

### Q: 安装安卓模拟器后 .wslconfig 不生效了？
A: 不是 .wslconfig 的问题。安卓模拟器（夜神、雷电、逍遥等）安装时会关闭 Hyper-V（`bcdedit hypervisorlaunchtype=Off`）和禁用 VirtualMachinePlatform 可选组件，导致 WSL2 完全无法启动。需要先恢复虚拟化组件：
1. `bcdedit /set hypervisorlaunchtype auto`
2. `dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart`
3. `dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart`
4. 重启电脑

### Q: 怎么确认虚拟化组件是否被模拟器破坏？
A: 运行以下命令：
```powershell
# 检查 Hyper-V 启动类型（应为 Auto）
bcdedit /enum | findstr hypervisor

# 检查 WSL 状态
wsl --status

# 快速测试 WSL 是否可用
wsl -d <distro> -- echo "OK"
```
如果 `hypervisorlaunchtype` 是 `Off` 或 `wsl --status` 提示虚拟机平台未启用，说明被破坏了。
