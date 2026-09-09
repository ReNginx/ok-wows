# 本地便携包

在仓库根目录使用已安装依赖的本地环境构建：

```powershell
.\.venv\Scripts\python.exe packaging/build_portable.py
```

输出位于 `dist/ok-wows-portable-时间戳/`，并生成同名 ZIP。完整解压后运行 `ok-wows.exe`，无需额外安装 Python。exe 是带 `requireAdministrator` 声明的启动器，需要保留旁边的程序文件和 `runtime` 目录。Windows 会在双击启动时请求管理员权限。

构建使用 Windows 自带的 .NET Framework C# 编译器、本机 Python 3.12 标准库和仓库 `.venv` 依赖。每次输出新目录，不覆盖旧包。包内不复制个人 `configs`、`logs`、截图目录或自定义任务，不连接模板项目的更新库。依赖包自带的许可证随运行环境保留；此包未做代码签名。

计划任务仍由随包 Python 执行 `main.py -t N`，保持原有最高权限设置。创建计划后若移动便携包，应重新创建计划。

构建脚本会检查随包解释器能否加载关键依赖、应用配置及 UU 标注，并保存文件 SHA-256 清单。它不会启动游戏、UU 或创建 Windows 计划任务。实际前台操作需在管理员权限下验证。
