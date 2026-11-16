# 作图工坊

本地像素资产工坊，支持 macOS 桌面客户端与源码网页运行：用自己的 Vertex AI Express / Google AI Studio API Key 制作像素格斗套图和桌宠立绘（提示词 → 出图 → 切分 → 入库或导出）。**不含对战游戏。**

公开仓库：<https://github.com/jayson-sheyue/herogame-studio>  
对战端另仓：<https://github.com/jayson-sheyue/herogame>

鉴权完全使用 **API Key**，不需要 Google Cloud CLI、GCP 项目 ID 或 ADC 登录。密钥默认只保存在本机服务内存中；主动勾选「记住密钥」后才使用系统凭据库。普通设置文件、工程、浏览器存储和导出包不包含 API Key。

---

## macOS 客户端（测试版）

从 [GitHub 测试版发布页](https://github.com/jayson-sheyue/herogame-studio/releases/tag/v0.1.0-beta.2) 下载。Apple Silicon（M 系列芯片）／macOS 15 或更高版本：打开 `HeroGameStudio-0.1.0-beta.2-macOS-arm64.dmg`，将 **作图工坊.app** 拖入 **Applications** 后启动。内置 Python、依赖和本地服务，无需安装 Python、Node 或 gcloud，也不必保持终端开启。选择产品线与工程文件夹后，在 **API Key 设置**中输入自己的密钥。

客户端使用原生 macOS 窗口、文件选择和保存对话框；关闭窗口即退出，任务或未保存修改会先提示。下载取消不会显示保存成功；客户端退出后只停止自己启动的服务，不影响原有网页服务。

- 工程与导出：仍在你选择的独立工程文件夹，可直接打开原网页工程。
- 工程列表与普通设置：`~/Library/Application Support/HeroGameStudio/`。原源码目录中的登记、设置与密钥不自动复制；旧工程通过选择原文件夹重新关联。
- 密钥默认仅本次会话有效，正常退出后清除；主动记住时使用 macOS 钥匙串。应用升级保持 Bundle ID 和设置路径不变。
- 手动升级：等待任务完成、正常退出，再替换应用。保留应用数据目录及工程；备份时复制整个工程文件夹。删除 `.app` 不会删除工程。

这是预发布测试包，只做 ad-hoc 完整性签名，**尚未做 Developer ID 签名与 Apple 公证**，从网络取得的副本可能被 Gatekeeper 拦截，仅供测试，不作为已公证稳定版。已验证范围与源码构建说明见 [macOS 桌面交付说明](desktop/README.md)。

## 源码网页运行

## 依赖

| 依赖 | 版本 / 说明 |
|---|---|
| 操作系统 | macOS、Windows 或 Linux |
| Python | **3.11 或更高**（`python3 --version`） |
| pip | 随 Python 安装 |
| API Key | 自己的 Express 或 AI Studio Key，及所选模型需要的权限 / 配额 |
| 浏览器 | Chrome / Edge / Firefox |
| 网络 | 出图时访问 Vertex AI |

Python 包见 `studio/requirements.txt`：FastAPI、Uvicorn、Pillow、`google-genai`、Cloud TTS 等。API Key 由你自己提供，按所选服务的实际用量计费。

---

## 1. 获取自己的 API Key

- **Vertex AI Express**：在 [Vertex AI Studio API Keys](https://console.cloud.google.com/vertex-ai/studio/settings/api-keys) 获取 Key。工坊支持 `AQ.` 开头的 Key，通过 Express 全局接口调用，不传项目 ID / 区域。
- **Google AI Studio**：在 [AI Studio API Keys](https://aistudio.google.com/apikey) 获取 Key。工坊支持 `AI…` 开头的 Key，也允许手动选择 AI Studio 使用新格式的授权 Key。

前缀仅用于「自动识别」的建议（`AQ.` → Express，其余 → AI Studio），不能证明 Key 的来源或权限。识别不符时在工坊中手动选择服务，不会自动把请求转发给另一服务。两条产品线分别记住服务和模型，密钥也分别保留。

模型是否可调用取决于 Key 的 API 限制、地区、结算和配额。连接检查不会生成内容；实际生图、配音和 BGM 生成可能收费。

---

## 2. 克隆并启动工坊

```bash
git clone https://github.com/jayson-sheyue/herogame-studio.git
cd herogame-studio/studio

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
python3 launch.py
```

服务就绪后会自动打开浏览器：**http://127.0.0.1:8787**。如果未自动打开，手动访问该地址。

macOS 完成首次安装后，也可直接双击仓库根目录的 `start.command`；它优先使用 `studio/.venv`，无需每次手动激活。服务已运行时会打开已有服务；被其他程序占用的端口会提示处理，不会自动结束其他进程。

**不要双击 `studio/static/index.html` 来使用工坊**：`file://` 页面无法连接后端，直接打开时只显示启动指引。工坊只监听本机；使用期间保持终端开启，按 `Ctrl+C` 停止本次启动的服务。需要开发热重载时仍可运行 `python3 server.py`。

工坊左侧 **API Key 设置**：

1. 选择服务来源（可自动识别），粘贴 API Key，并填写该服务支持的模型 ID。
2. 点击 **保存设置**，或 **测试连接并保存**。连接检查对提示词和图像模型调用 `countTokens`，不执行生成；全部通过后才保存新设置。失败保留原设置和输入，逐项显示原因。
3. 密钥默认仅保留在本次服务会话中，重启后重新输入。需要记住时主动勾选 **记住密钥（系统凭据库）**；macOS 使用钥匙串，Windows / Linux 需要可用的系统凭据后端。不可用时会报错，**不会退回明文文件**。
4. 密钥输入留空会保留已设置的 Key，输入新值可替换；点 **清除密钥** 会移除当前产品线的会话和已记住的 Key。环境变量中的 Key 在本次会话中也不会自动补回，重启后仍按环境变量加载。

设置下一个任务生效；已开始的任务使用其配置快照。API 只返回是否已设置与存储位置，不回传密钥或掩码。`studio/settings.<产品线>.json` 仅保存服务、模型及存储方式；旧的 project / location 字段不再用于鉴权，旧 ADC 文件不会被读取或修改。

普通设置优先级：请求中的模型 / 服务 > 当前产品线设置文件 > 环境变量 > 默认值。密钥优先级：会话中显式设置 / 清除 > 本安装位置及产品线的系统凭据 > 环境变量。

| 可选环境变量 | 含义 |
|---|---|
| `STUDIO_API_KEY` | 本机服务 Key；其次兼容 `GOOGLE_API_KEY`、`GEMINI_API_KEY` |
| `STUDIO_API_PROVIDER` | `auto`、`vertex` 或 `ai_studio` |
| `STUDIO_TEXT_MODEL` | 未保存配置时的提示词模型，默认 `gemini-3.8-flash` |
| `STUDIO_IMAGE_MODEL` | 未保存配置时的图像模型，默认 `gemini-2.5-flash-image` |

已有模型选择保持原样，不会静默改用其他模型。旧 `gemini-2.5-flash` 的可用性已受服务方生命周期限制；若当前 Key 不能使用，请手动填写该服务当前可用的文本模型。`settings.example.json` 仅演示非秘密配置，不要在 JSON 中加入 API Key。

**配音与 BGM 边界**：Gemini-TTS 使用同一 Key 的生成接口，2.5 TTS 的模型 ID 会按所选服务对应到其正式 / preview 名称。PCM 结果保存为真实 WAV，旧 MP3 仍可预览；入库与导出记录实际扩展名。声线目录是选择参考，连接检查不验证音频生成。原 Cloud 朗读 / 旧版克隆改为 API Key 请求，仍需独立 Cloud Text-to-Speech 权限；Express 不提供这些独立接口，AI Studio 限制到 Gemini API 的 Key 也通常无此权限。不会回退 ADC、自动换引擎或替换 Key。Cloud 目录仅附带常见中文声线示例；其他语种可使用 Gemini 预置声线。Lyria 使用 AI Studio Interactions 接口及其模型权限；Express 模式不支持该接口，可上传已有 BGM。

官方接入参考（本次按 `google-genai` 2.23.0、`keyring` 25.7.0 验证）：[Express Key 与全局端点](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/express-mode/overview)、[Express 可用 REST 接口](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/express-mode/api-reference)、[Gemini API Key](https://ai.google.dev/gemini-api/docs/api-key)、[Gemini generateContent 配音](https://ai.google.dev/gemini-api/docs/generate-content/speech-generation)、[模型生命周期](https://ai.google.dev/gemini-api/docs/deprecations)、[keyring 系统凭据库](https://keyring.readthedocs.io/en/stable/)。

---

## 3. 新建内容工程（不要用本仓库当工程）

1. 选产品线 **对战游戏资产**。
2. **新建工程** → 选一个**空文件夹**（例如 `~/Documents/HeroPacks`）。不要选 clone 下来的 `herogame-studio` 目录。
3. 带 `game/serve.py` 的对战目录会被拒绝，避免写进别人的游戏工程。

工程目录会变成：

```text
HeroPacks/
  herogame.json
  assets/studio/     # 草稿，不要发给别人
  assets/game/       # 「采用入库」后的成品
```

---

## 4. 做套图

顺序不要跳：

1. **风格锚点** → 写出提示词 → 出图 → 采用入库（每个工程一份，定调后不能改）。
2. **地图**（可选）→ 描述 + 关键词 + 地形 → 出图 → 入库。不画人、不写字。
3. **英雄** → 形象 / 武器 / 技能机制 → 先入库 **人物三视图** → 再出其它动作条 → 切分播放 → 入库。
4. 精灵勾选去掉青色底。地图不用去青。

切分只预览；不满意点「重新切分」，不必重新生图。

---

## 5. 导出给对战游戏

「采用入库」只写当前内容工程，**不会**热更新任何正在跑的游戏。

1. 点 **导出此英雄数据包** 或 **导出此地图数据包**（`.hgpk.zip`）。
2. 发给对战维护人，或自己导入对战仓：

```bash
cd herogame/game    # 对战仓库
python3 import_pack.py ~/Downloads/某英雄.hgpk.zip
# 或把 zip 放到 game/incoming/ 再 python3 serve.py
```

不要提交 `settings.json`、`projects.json`、草稿 PNG、`.venv`。

---

## 6. 桌宠立绘与保存

选择 **桌宠 / 立绘资产**，使用独立工程；锁定风格后新建立绘，选择动作清单与帧数，先生成并锁定人物三视图，再制作其余动作。切分后点 **去青导出**，透明 PNG 写在当前工程的 `assets/studio/exports/portraits/<id>/<动作>/`，不写入对战目录。

- 提示词、动作蓝图、形象和配饰会自动保存。切换立绘或工程前会先等待保存，失败时保留当前编辑并提示原因；保存失败后不会继续提交生成、切分或导出。
- 同一立绘在其他窗口更新后，旧窗口的保存会提示冲突。先复制保留待合并文字，再点击列表中当前立绘，确认重新读取后合并。刷新或离开页面时，如果仍有待保存编辑，浏览器会提示。
- 同一份资产的写操作互斥；独立资产可继续处理。立绘生成期间可以浏览其他页面，生成结束后再新建或切换立绘。
- 导出全部时，任务面板会区分 **完成 / 部分完成 / 失败**，列出未成功的动作。成功项保留，可在失败动作的卡片上单独重试。单个动作重新导出失败时，旧透明帧保留；完整新结果就绪后才替换。

## 7. 工程切换与运行边界

工坊使用一个本机服务进程和一个活动工程。生成、保存等工程任务执行期间，切换产品线、切换工程和清空工程会被拒绝；任务结束后可继续。工程切换会使旧标签页的上下文失效，旧页写入会提示刷新，避免把旧作品写进新工程。更新代码后请刷新所有已打开的工坊标签页。

核心工程、英雄和立绘 JSON 元数据通过临时文件写入后替换，写入失败会保留原文件。仍建议定期备份整个内容工程文件夹。不要为同一份工程启动多个服务实例或使用多个 Uvicorn worker；本次并发保护仅覆盖单服务进程中的请求。

任务面板保留本次页面会话的最近任务，刷新后不恢复历史。请求超时或关闭页面不等于服务端已取消生成，后台仍可能继续执行和计费；先等待并重新查看结果，避免盲目重复提交。

## 开发检查（离线，不调用付费 API）

先激活 `studio/.venv`，从仓库根目录运行：

```bash
python3 -m pip install -r studio/requirements-dev.txt
python3 studio/scripts/check.py
```

检查包含 Python 语法、原有去青测试、临时工程 API / 文件保存与导出回归，以及浏览器脚本的状态和乱序测试。开发检查额外需要 Node.js 18 或更新版本；正常使用工坊不需要 Node.js。测试使用临时工程，不读取本机工程登记、设置或 ADC，也不会请求真实生成服务。浏览器人工验收和真实 Vertex 出图需另行执行，离线测试不代表模型调用已验证。

工程请求保护使用 FastAPI 的[自定义 APIRoute 扩展方式](https://fastapi.tiangolo.com/how-to/custom-request-and-route/)。脚本客户端写入 API 前，需要从 `/api/health` 响应头取得 `X-Studio-Workspace`，并在写请求中带上该头；切换工程后使用切换响应头中的新值。此值用于检测过期上下文，不是登录凭据。

---

## 不要提交到 Git 的文件

| 文件 | 原因 |
|---|---|
| `studio/settings.json`、`settings.*.json` | 本机服务和模型偏好 |
| `studio/projects.json` | 本机文件夹路径 |
| `.venv/`、`__pycache__/` | 环境 |
| 任何套图 PNG / 内容工程 | 内容不属于本工具仓 |

---

## 常见问题

**测试鉴权失败**  
确认 Key 的服务来源、API 限制、结算与模型权限；在设置中选择正确来源后重试。不再使用 ADC 或 gcloud 登录。

**出图 403 / 空图**  
当前 Key 对所选模型没有权限，或配额不足。在 API Key 设置中核对服务来源与模型 ID。

**打开工坊没有工程**  
必须先新建/打开一个空内容文件夹。

**切分报看不出 2×2 宫格**  
三视图是单行四帧。更新到本仓库最新代码后再切。
