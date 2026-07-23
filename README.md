# AI Desktop Pet Generator

把文字描述和可选参考图生成桌面宠物资源：

1. 调用 OpenAI 兼容 Image API 生成一张三行动作源图。
2. 本地抠 `#00FF00` 绿幕背景。
3. 切出 `6 / 4 / 5` 三组动作帧。
4. 打包成标准 `8 x 9` spritesheet、`pet.json` 和 `preview.png`。

## 安装

```bash
cd /Users/loge/A_project/ai-desktop-pet-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 配置

项目会自动读取当前目录下的 `.env`。默认使用 OpenAI：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_IMAGE_MODEL=gpt-image-2
# 可选：描述增强用的文本模型，默认 gpt-4o-mini
OPENAI_TEXT_MODEL=gpt-4o-mini
```

如果用 OpenAI 兼容代理：

```bash
OPENAI_BASE_URL=https://your-compatible-endpoint/v1
OPENAI_API_KEY=your-provider-key
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_TEXT_MODEL=your-chat-model
```

## 纯文字生成

```bash
petgen generate \
  --prompt "一只圆滚滚的水豚程序员，戴小耳机，温柔、聪明、适合陪伴写代码" \
  --name "水豚程序员" \
  --output outputs/capybara-coder
```

## 带参考图生成

```bash
petgen generate \
  --prompt "根据参考图设计成可爱的桌面宠物，保留颜色和标志性配饰" \
  --image /path/to/reference.png \
  --name "参考图宠物" \
  --output outputs/from-reference
```

有参考图时 `--prompt` 可以省略，会自动使用内置默认描述：

```bash
petgen generate --image /path/to/reference.png --output outputs/from-reference
```

> 内置默认描述：把参考图中的形象原样转成可爱桌面宠物，保留原本的颜色、轮廓、标志性配饰和性格特征

有参考图时会走 `/images/edits`；没有参考图时会走 `/images/generations`。

## 描述增强（enrichment）

描述过短（strip 后少于 30 字符）时，会先调用文本模型（OpenAI 兼容 `/chat/completions`）把外观、配色、性格、风格等细节补充完整，再喂给图像模型：

```bash
petgen generate --prompt "一只猫" --output outputs/cat        # 自动触发增强
petgen generate --prompt "一只猫" --no-enrich --output out/   # 强制关闭
petgen generate --prompt "很长的详细描述……" --enrich --output out/  # 强制开启
```

- 文本模型复用 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`，模型由 `--text-model` 或 `OPENAI_TEXT_MODEL` 指定（默认 `gpt-4o-mini`）。
- 增强失败（代理不支持该模型、网络错误等）时只会打印 warning 并回退到原始描述，不会中断生图。

## 只处理已有源图

如果已经有一张三行动作源图，可以跳过 API，直接打包：

```bash
petgen build \
  --source /path/to/source.png \
  --prompt "本地源图打包测试" \
  --name "本地桌宠" \
  --output outputs/local-pet
```

## 输出

每次输出目录会包含：

- `source.png`：模型原始返回图，仅 `generate` 命令会写入
- `sprite.png`：标准 `8 x 9` 桌宠 spritesheet
- `pet.json`：动画 manifest（`description` 始终是你给出的原始描述；触发描述增强时会额外记录 `_generation.enrichedDescription`）
- `preview.png`：首帧预览图

## 验证

```bash
pytest
```

当前测试只验证本地后处理和请求配置，不会发起真实网络生图请求。

## 常驻桌宠模式（前端 + 宠物管理 + 联动）

安装桌面依赖后，可以把它当成一个常驻菜单栏的桌宠 app 来用：

```bash
pip install -e ".[desktop]"
petgen app
```

`petgen app` 会启动：系统托盘（主控制面）、悬浮宠物、按需打开的**宠物库**与**设置**窗口，以及**AI 事件总线**。数据全部存在 `~/.petgen/`（可用 `$PETGEN_DATA_DIR` 或 `--data-dir` 覆盖）：`petgen.sqlite`（设置 + 宠物注册表 + 事件）、`pets/<id>/`（托管的桌宠素材）、`task-events.jsonl`（事件收件箱）。

- **宠物库**：托盘「打开宠物库…」浏览/选择/预览/删除已生成的桌宠；「✨ 创建新宠物…」会在后台跑生图流水线并自动登记入库。`petgen generate` 成功后默认也会把产物拷进库（加 `--no-register` 可关闭）。
- **设置**：托盘「设置…」配置 AI key/base_url/模型、缩放、动画/音效开关、人格（温暖/元气/沉稳/傲娇）。
- **悬浮宠物**：6 态动画（idle/attentive/happy/busy/alert/error）+ 表情叠加 + 对话气泡 + 完成庆祝粒子；左键点 = 互动台词，右键 = 菜单，可拖动，透明区点击穿透。
- **快速浮一只**（不走库/托盘）：`petgen desktop outputs/xxx --scale 1.5` 仍可用。

### 让 AI 写代码时桌宠实时反应（事件总线）

任何外部进程往 `~/.petgen/task-events.jsonl` 追加一行 JSON，桌宠约 2 秒内用对应表情回应（thinking→busy、responding→attentive、completed→happy、error→error）。附带的钩子脚本 `scripts/petgen-event.sh` 让接入只需一行，例如 Claude Code 的 `~/.claude/settings.json`：

```jsonc
{
  "hooks": {
    "PreToolUse":  [{"hooks": [{"type": "command", "command": "/abs/path/scripts/petgen-event.sh ai_thinking \"思考中\" \"\" claude_code"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "/abs/path/scripts/petgen-event.sh ai_responding \"回复中\" \"\" claude_code"}]}],
    "Stop":        [{"hooks": [{"type": "command", "command": "/abs/path/scripts/petgen-event.sh task_completed \"完成一轮\" \"\" claude_code"}]}]
  }
}
```

契约是语言无关的：`{"id","kind","title","detail","source","createdAt"}`，任何编辑器/agent 都能喂。

> 说明：托盘图标、屏上穿透手感、气泡锚定等需在真机目检；无显示器环境用 `QT_QPA_PLATFORM=offscreen` 跑的是渲染/逻辑自检。macOS 上以裸 `python` 运行时 Dock 仍可能短暂出现图标（打成 `.app` 才能彻底去除，留作后续）。

### 语音包（说话 + 音效）

桌宠可以「说话」并配反馈音效，在设置「🐶 宠物行为 → 语音包」里切换，支持 ▶ 试听。内置三包：**软萌喵 🐱 / 元气电波 ⚡ / 沉稳管家 🎩**，各带语种/音色偏好与台词池。

- **说话**用系统 TTS 实时合成（macOS 自带中文语音如「婷婷」），**反馈音效**由程序用正弦波现场合成（pop / 叮咚 / 庆祝 / 嗡 / 嘀嗒）——两者都**不打包任何第三方录音，零版权问题**。
- 触发：点击宠物 = `tap`；AI 事件按 kind 映射（completed→happy、thinking→busy、error→error…）。「安静模式」会一并静音；设置里「开启音效反馈」可总开关。
- 音效文件在 `src/petgen/resources/_sfx/`，可用 `python scripts/make_voice_sfx.py` 重新生成。
- 想用**真人录的开源音效**？把 CC0/CC-BY 的 wav 放进 `_sfx/` 并在该包 `sounds` 里写文件名即可；推荐来源（自行下载、按许可署名，**不**默认打包）：[OpenGameArt CC0 音效](https://opengameart.org/content/cc0-sound-effects)、[freesound CC0 UI 包](https://freesound.org/people/GameAudio/packs/13940/)、[itch.io CC0 音效](https://itch.io/game-assets/assets-cc0/tag-sound-effects)。

## 图像源图约定

为了让本地切图稳定，模型输出必须尽量遵守：

- 单张图，纯 `#00FF00` 绿幕背景
- 3 行动作
- 第 1 行 6 帧 idle
- 第 2 行 4 帧 attentive
- 第 3 行 5 帧 happy
- 每帧完整身体、居中、角色之间留明显绿幕间隔
