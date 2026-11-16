# 作图工坊

本地网页工具：用自己的 Google Cloud / Vertex AI 制作像素格斗套图和桌宠立绘（提示词 → 出图 → 切分 → 入库或导出）。**不含对战游戏。**

公开仓库：<https://github.com/jayson-sheyue/herogame-studio>  
对战端另仓：<https://github.com/jayson-sheyue/herogame>

本仓库**没有** GCP 项目 ID、密钥、服务账号或本机路径。鉴权只存在你电脑上的 `studio/settings.json`（已被 gitignore）。可参考 `studio/settings.example.json` 自行填写。Application Default Credentials 在本机 `~/.config/gcloud/`，**不要**把该目录或任何服务账号 JSON 拷进仓库。

---

## 依赖

| 依赖 | 版本 / 说明 |
|---|---|
| 操作系统 | macOS、Windows 或 Linux |
| Python | **3.11 或更高**（`python3 --version`） |
| pip | 随 Python 安装 |
| [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) | `gcloud` |
| GCP 项目 | **你自己的**项目，必须开通结算 |
| 浏览器 | Chrome / Edge / Firefox |
| 网络 | 出图时访问 Vertex AI |

Python 包见 `studio/requirements.txt`：FastAPI、Uvicorn、Pillow、`google-genai`、Cloud TTS 等。**不要**把别人的 `settings.json` 或 ADC 密钥拷过来。

---

## 1. 安装 Google Cloud CLI 并登录

1. 安装 CLI：<https://cloud.google.com/sdk/docs/install>
2. [Google Cloud Console](https://console.cloud.google.com/) 新建项目，绑定结算账号。
3. 启用 API：
   - **Vertex AI API**（`aiplatform.googleapis.com`）— 必须
   - **Cloud Text-to-Speech API**（`texttospeech.googleapis.com`）— 台词配音，可后开
4. 本机执行（会打开浏览器登录**你的** Google 账号）：

```bash
gcloud init
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com
```

`YOUR_GCP_PROJECT_ID` 换成你自己的项目 ID。出图按次计费。

---

## 2. 克隆并启动工坊

```bash
git clone https://github.com/jayson-sheyue/herogame-studio.git
cd herogame-studio/studio

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
python3 server.py
```

终端出现 Uvicorn 监听后，浏览器打开：**http://127.0.0.1:8787**

只监听本机。停掉：`Ctrl+C`。端口被占用时先结束旧的 `server.py`。

工坊左侧 **Vertex 设定** 填写你的 GCP 项目 ID，点 **测试鉴权**。通过后写入本机 `settings.json`（不会进 Git）。也可先复制 `settings.example.json` 为 `settings.json` 再改项目 ID。

可选环境变量（仅作首次默认，一般不用）：

| 变量 | 含义 |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP 项目 |
| `GOOGLE_CLOUD_LOCATION` | 提示词区域，默认 `global` |
| `STUDIO_IMAGE_LOCATION` | 出图区域 |
| `STUDIO_TEXT_MODEL` | 默认 `gemini-2.5-flash` |
| `STUDIO_IMAGE_MODEL` | 默认 `gemini-2.5-flash-image` |

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

选择 **桌宠 / 立绘资产**，使用独立工程；锁定风格后新建立绘，选择动作清单与帧数，先生成人物三视图，再制作其余动作。切分后点 **去青导出**，透明 PNG 写在当前工程的 `assets/studio/exports/portraits/<id>/<动作>/`，不写入对战目录。

- 提示词、形象和配饰会自动保存。切换立绘或工程前会先等待保存，失败时保留当前编辑并提示原因；保存失败后不会继续提交生成、切分或导出。
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

检查包含 Python 语法、透明帧导出、临时工程 API / 文件保存与导出回归，以及浏览器脚本的状态和乱序测试。开发检查额外需要 Node.js 18 或更新版本；正常使用工坊不需要 Node.js。测试使用临时工程，不读取本机工程登记、设置或 ADC，也不会请求真实生成服务。浏览器人工验收和真实 Vertex 出图需另行执行，离线测试不代表模型调用已验证。

工程请求保护使用 FastAPI 的[自定义 APIRoute 扩展方式](https://fastapi.tiangolo.com/how-to/custom-request-and-route/)。脚本客户端写入 API 前，需要从 `/api/health` 响应头取得 `X-Studio-Workspace`，并在写请求中带上该头；切换工程后使用切换响应头中的新值。此值用于检测过期上下文，不是登录凭据。

---

## 不要提交到 Git 的文件

| 文件 | 原因 |
|---|---|
| `studio/settings.json`、`settings.*.json` | 你的 GCP 项目 ID |
| `studio/projects.json` | 本机文件夹路径 |
| `.venv/`、`__pycache__/` | 环境 |
| 任何套图 PNG / 内容工程 | 内容不属于本工具仓 |

---

## 常见问题

**测试鉴权失败**  
ADC 未登录、项目 ID 填错、未开通 Vertex AI 或未绑定结算。再跑 `gcloud auth application-default login`。

**出图 403 / 空图**  
当前账号对所选出图模型没有权限。在 Vertex 设定里核对模型名与区域。

**打开工坊没有工程**  
必须先新建/打开一个空内容文件夹。

**切分报看不出 2×2 宫格**  
三视图是单行四帧。更新到本仓库最新代码后再切。
