# macOS 桌面客户端

定位：个人／小范围手动分发，无 OTA；首版 `0.1.0-beta.1`（构建号 `1`），Apple Silicon、macOS 15+。原生 AppKit + WKWebView 窗口，PyInstaller onedir 携带 Python 服务及依赖；系统 WebKit 无需额外下载。

## 构建

在 Apple Silicon Mac 安装 Xcode Command Line Tools、Python 3.14 和项目构建依赖：

```bash
studio/.venv/bin/python -m pip install -r desktop/requirements-build.txt
studio/.venv/bin/python studio/scripts/check.py
studio/.venv/bin/python desktop/build.py
```

产物在 `dist/`，应用暂存在 `build/macos/作图工坊.app`。脚本拒绝覆盖同名 DMG；修改正式发布内容须更新 `desktop/version.json` 及安装说明，使用新的版本号。构建会扫描源码及产物，带上依赖许可证、依赖版本、公开源码文件 SHA-256、Git HEAD 与工作区是否有未提交更改。当前本地包包含工作区已有功能；`working_tree_modified` 明确标识本地构建，不冒充与 PR 提交逐字一致的正式发布包。

PyInstaller 随附的 certifi/gRPC 公共信任根经 X.509 解析验证后，以 `.crt` 名称携带，内容字节保持原样；runtime hook 指向这些公共资源。私钥与用户凭据不进入打包目录，TLS 验证保持启用。发布前仍需执行 skill 的 secret guard（有该 skill 时构建脚本自动执行），不能跳过。

```bash
studio/.venv/bin/python desktop/smoke.py 'build/macos/作图工坊.app/Contents/Resources/backend/studio-service'
'build/macos/作图工坊.app/Contents/Resources/backend/studio-service' --self-check
codesign --verify --deep --strict 'build/macos/作图工坊.app'
hdiutil verify dist/HeroGameStudio-0.1.0-beta.1-macOS-arm64.dmg
```

`smoke.py` 用临时空目录、最小 PATH 和实际冻结的可执行文件验证资源、中文路径、工程关联、普通设置重启保留及会话密钥重启清除；没有真实 API 请求或真实用户数据。`--self-check` 检查随包公共证书、TTS/gRPC 模块和 macOS 钥匙串后端，不读取钥匙串条目。

## 运行与数据

应用只监听 `127.0.0.1` 的系统分配端口，不占用网页服务的 8787。每次启动建立独立 HttpOnly / SameSite 会话，并拒绝异源请求；网页不能直接操作该私有服务。原生桥只允许主窗口的本地页面请求文件选择、保存及普通界面偏好。

工程保存在用户选定的文件夹。工程登记和普通设置使用稳定的 `~/Library/Application Support/HeroGameStudio/`，系统钥匙串槽位由稳定的设置路径和产品线决定。安装包不包含旧网页登记、设置、工程、ADC 或密钥。旧工程通过「选择文件夹」重新关联；不自动搬迁用户数据。环境变量 `STUDIO_DATA_DIR` 可显式指定独立绝对路径供源码或集成测试使用。

网页会话偏好只保留模式、当前对象、角色描述及帧数；API Key 输入不写入偏好或 WebKit 存储。普通服务和模型设置由后端设置文件保存。关闭窗口视为退出；待保存修改、未保存的 Key、进行中任务或下载会提示。正常退出终止自己持有的后端，父进程意外消失时后端也退出。外链打开默认浏览器；系统编辑菜单支持复制、粘贴、撤销与全选。

## 手动安装与更新

打开 DMG，把应用拖到 Applications。更新前等待任务完成并退出，再替换应用；工程、应用数据目录和钥匙串原地保留。失败时可放回原 `.app`；不要通过删除工程或应用数据目录排障。首次桌面版没有旧安装包可做跨版本升级验证；同一产物重装／重启保留可以单独核验。

默认构建仅 ad-hoc 签名，未做 Developer ID 签名或 Apple 公证。公开发行需准备自己的开发者签名与公证环境，并先把源码与 README 合入 `main`，再从确定提交另发新版本。当前不创建公开 Release，不自动替换用户已安装应用。

未验证：Intel、其他 macOS 版本、无开发工具的全新机器、真实 API Key 的生成／语音／配额、真实系统钥匙串交互。离线测试或冻结服务通过不代表这些项目通过。

## 官方参考

- [PyInstaller macOS 架构与签名](https://pyinstaller.org/en/stable/feature-notes.html#macos-specific-options)：使用 PyInstaller 6.22.0 onedir、arm64。
- [Apple WKDownloadDelegate](https://developer.apple.com/documentation/webkit/wkdownloaddelegate)：原生保存目标、失败及完成处理。
- [Apple WKScriptMessageHandlerWithReply](https://developer.apple.com/documentation/webkit/wkscriptmessagehandlerwithreply)：限定本地页面的异步文件选择桥。
