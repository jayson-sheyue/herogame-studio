# 作图工坊

本地像素资产生图工具（网页开在本机 `8787`）。用 Vertex AI 写提示词、出图、切分、入库。  
**不含对战游戏。** 生成的英雄/地图是文件夹，拷给正在跑游戏的人即可。

适合：自己有一台电脑、有 Google Cloud 账号，clone 之后在本地生套图。

---

## 给同事：最短路径

1. 向仓库维护人要 **GitHub 地址**（只要这个 `studio` 仓库，不要整个游戏工程）。
2. 本机安装 **Python 3.11+**、**Google Cloud CLI**。
3. 用**自己的** GCP 项目做 `gcloud auth application-default login`（不要用别人的密钥文件）。
4. `pip install -r requirements.txt` → `python3 server.py` → 浏览器打开 <http://127.0.0.1:8787>
5. 选产品线 **对战游戏资产** → **新建工程**（空文件夹，不要建在本仓库里）。
6. 先锁定风格锚点，再做地图 / 英雄。英雄必须先入库 **人物三视图**，才能出其它动作条。
7. 入库成功后，把工程里的 `assets/game/heroes/<id>/` 或 `assets/game/stages/<id>/` **整夹打包**发给维护人，合并进他电脑上的游戏即可。

生图按次计费。请用自己的 GCP 项目，并确认已开通结算。

---

## 仓库里该有什么、不该有什么

**要进 GitHub 的**

- `server.py`、`project.py`、`prompts.py`、`score.py`、各 `*_client.py`、`*_assets.py`
- `static/`（工坊网页）
- `requirements.txt`、本 README、`.gitignore`

**千万不要提交**

| 文件 | 原因 |
|---|---|
| `settings.json`、`settings.herogame.json`、`settings.deskpet.json` | 里面是你的 GCP 项目 ID |
| `projects.json` | 本机路径，别人电脑对不上 |
| `../assets/`、游戏 `game/`、任何 `.png` 套图 | 那是内容，不是工具 |
| `.venv/` | 虚拟环境 |

从现有 HeroGame 工程**拆出独立仓库**时，只复制 `studio/` 这一层（保持目录名 `studio/`），不要 `git push` 整个游戏工程。

推荐仓库布局：

```text
herogame-studio/          ← GitHub 仓库根
  README.md               ← 可把本文件再放一份到仓库根，或 clone 后读 studio/README.md
  studio/
    server.py
    requirements.txt
    static/
    ...
```

维护人本地的 `HeroGame/` **原样不动**：继续 `8787` 工坊 + `8788` 游戏。独立仓库只是给同事的一份拷贝。

---

## 本机要求

| 软件 | 说明 |
|---|---|
| macOS / Windows / Linux | 任意，用浏览器打开本机网页即可 |
| Python 3.11 或更高 | `python3 --version` |
| [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) | `gcloud` |
| Chrome 或 Edge | 打开 <http://127.0.0.1:8787> |

不需要做成 Mac App。不要装 Electron。

---

## 1. Google Cloud（每人自己的项目）

出图走 **Vertex AI**，账号要有结算。没有 GCP 的同事先建项目：[Google Cloud Console](https://console.cloud.google.com/) → 新建项目 → 绑定结算账号。

在 Cloud Console 启用：

- **Vertex AI API**（`aiplatform.googleapis.com`）—— 提示词 + 出图（必须）
- **Cloud Text-to-Speech API** —— 台词配音（可后开）
- 地图 BGM 用 Lyria，若按钮报错再在 Vertex 里开通对应预览模型

本机登录（会打开浏览器）：

```bash
gcloud init
gcloud config set project 你的GCP项目ID
gcloud auth application-default login
```

默认模型（可在工坊左侧「Vertex 设定」改）：

| 用途 | 默认 |
|---|---|
| 写提示词 | `gemini-2.5-flash` |
| 出图 | `gemini-2.5-flash-image`（Nano Banana） |
| 区域 | `global` |

点「测试鉴权」。通过后会写入本机 `studio/settings.json`（已被 gitignore）。

环境变量只作首次默认，一般不用设：

| 变量 | 含义 |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP 项目 |
| `GOOGLE_CLOUD_LOCATION` | 提示词区域 |
| `STUDIO_IMAGE_LOCATION` | 出图区域 |
| `STUDIO_IMAGE_MODEL` | 出图模型 |
| `STUDIO_TEXT_MODEL` | 提示词模型 |

---

## 2. 安装并启动

```bash
git clone https://github.com/jayson-sheyue/herogame-studio.git
cd herogame-studio/studio

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
python3 server.py
```

终端出现 uvicorn 监听后，浏览器打开：

**http://127.0.0.1:8787**

只绑本机回环地址，同事不能靠这个端口给你「远程入库」。套图用文件夹拷贝，见下文。

改代码会自动热重载。停掉：终端 `Ctrl+C`。

**端口被占用**（本机已有一份工坊）：换目录再开会再占 8787。先关掉旧的 `server.py`，或不要同时开两份。

---

## 3. 新建资产工程（和工具仓库分开）

工坊打开后：

1. 选产品线 **对战游戏资产**（同事做格斗套图选这个）。
2. **新建工程** → 选一个**空文件夹**，例如 `~/Documents/HeroPacks`。  
   不要选 GitHub clone 目录当工程，否则草稿会和工具代码混在一起。
3. 以后「切换项目」只列出这一类工程。

工程目录会长成：

```text
HeroPacks/
  herogame.json                 # 工程标记
  assets/studio/                # 草稿、切分预览（不要发给别人）
  assets/game/                  # 「采用入库」后的成品（发给维护人）
    index.json
    style/style.png
    heroes/<id>/fighter.json + 各动作 png
    stages/<id>/stage.json + stage.png
```

桌宠 / 立绘走另一条产品线，导出到 `assets/studio/exports/portraits/`，不写进对战目录。

---

## 4. 做套图（对战游戏）

顺序不要跳：

0. **Vertex 设定** 测试鉴权通过。
1. **风格锚点**：写出提示词 → 出图 → 采用入库。每个工程一份，定调后不能改。
2. **地图库**（可选）：描述 + 关键词 + 地形 → 写出提示词 → 出图 → 入库。地图不画人、不写字。
3. **英雄**：填三栏（人物形象 / 武器配饰 / 技能机制）→ 写出提示词 → 先出并入库 **人物三视图** → 再出其它动作条 → 切分播放无误 → 采用入库。
4. 入库精灵勾选去掉青色底。地图和 CG 不是青屏，不用去青。

切分：出图后点切分，同一位置循环播放。不满意点「重新切分」换切法，不必重新生图。满意再入库。

---

## 5. 把成品交给正在跑游戏的人

游戏只认 `assets/game/` 下的文件夹，**没有单独的加密包格式**。

发给维护人（整夹压缩即可）：

```text
heroes/<英雄id>/     # 必须含 fighter.json 和各 png
stages/<地图id>/     # 必须含 stage.json 和 stage.png
```

不要发：`assets/studio/drafts/`、切分预览、`.venv`、`settings.json`。

维护人收到后：

1. 解压进他电脑上游戏工程的 `assets/game/heroes/` 或 `assets/game/stages/`（与现有 id 不冲突）。
2. 打开该工程的 `assets/game/index.json`，把新 id 加进 `heroes` 或 `stages` 数组。  
   若他本机工坊也打开着同一工程，在工坊里对这个英雄/地图再点一次入库，名单会自动刷新。
3. 刷新对战页 <http://127.0.0.1:8788> （或下一场对战）。

同一局域网 **不能** 把工坊 8787 当共享盘用：每人本机生成，用压缩包或 U 盘交文件。

---

## 技能机制（填英雄简报时）

贴图只决定长什么样。行为在 `fighter.json` 的 `moves.<招>.mechanic.type`：

| type | 手感 |
|---|---|
| `melee` | 近战挥击 |
| `bolt` | 直线弹 |
| `beam` | 短时穿透光束 |
| `zone` | 贴地法阵 |
| `drop` | 从天砸下 |
| `homing` | 追踪 |
| `barrage` | 同一张图连发 |
| `trap` | 落地后停留 |

状态 `burn` / `freeze` / `poison` 是对战染色，不必再出一套燃烧图。

---

## 出图规格（心里有数即可）

- 精灵、风格锚点：实心 `#00FFFF` 青底（模型不会出透明通道）。
- 动作条：横排 5 帧（三视图 4 帧），格间留缝，禁止人物叠进下一格。
- 地图：21:9 侧视场地，不画角色、不写文字。
- 技能特效禁止青绿（会当色键抠掉）。

---

## 维护人：从现有工程拆仓库（不打断本机开发）

在游戏工程**外面**另建目录，只复制 `studio/` 源码。必须排除本机鉴权文件：

```bash
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude 'settings.json' \
  --exclude 'settings.*.json' --exclude 'projects.json' \
  /path/to/your-game/studio/ /path/to/herogame-studio/studio/
```

不要提交 `settings.json`、`projects.json`，也不要把整个游戏工程 push 上去。本机原来的工坊目录继续用即可。

---

## 常见问题

**测试鉴权失败**  
ADC 没登录、项目 ID 填错、未开通 Vertex AI、未绑定结算。再跑一次 `gcloud auth application-default login`。

**能写提示词、出图 403 / 空图**  
出图模型和区域在「Vertex 设定」里改；`gemini-2.5-flash-image` 需要项目有该模型权限。

**打开工坊没有工程**  
必须先「新建工程」指向空文件夹。不要指望 clone 下来就能直接出图。

**切分报「看不出 2×2 宫格」**  
三视图是单行四帧。更新到含该修复的工坊后再点「重新切分」。

**同事出的图在我游戏里看不到**  
id 是否已写入 `assets/game/index.json`；文件是否在 `heroes/<id>/`；对战页是否强制刷新。
