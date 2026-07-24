# AI Desktop Pet Generator 🐾

<p align="center">
  <table align="center">
    <tr>
      <td align="center"><img src="docs/images/hero.png" alt="主角：灰白小猫" width="360"></td>
      <td align="center"><img src="docs/images/idle.gif" alt="主角的 idle 呼吸动画（会动）" width="200"></td>
    </tr>
    <tr>
      <td align="center"><sub><b>灰白小猫</b> · 由一句话 / 参考图生成</sub></td>
      <td align="center"><sub>idle 呼吸动画</sub></td>
    </tr>
  </table>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue.svg" alt="Python >= 3.10">
  <img src="https://img.shields.io/badge/tests-pytest%20%2B%20ruff-brightgreen.svg" alt="pytest + ruff">
</p>

<p align="center">
  把一句话（或一张参考图）变成一只<sub>　</sub><b>常驻桌面的高质感宠物</b>。<br>
  AI 生图 → 本地绿幕抠图 → 切帧打包成 <code>8×9</code> 精灵表 → 在系统托盘里养起来，<br>还能在你用 AI 写代码时实时做出反应。
</p>

<p align="center">
  <sub>更多画风一致的伙伴：</sub><br>
  <img src="docs/images/gallery.png" alt="更多宠物：六角恐龙、小熊猫、柯基幼崽、短尾矮袋鼠、绒绒猫头鹰、小刺猬" width="820">
</p>

---

## 它能做什么

- 🎨 **文字 / 参考图生宠**：一句描述，或丢一张参考图保留配色与标志配饰。
- 🧩 **本地后处理**：绿幕抠图、连通域切帧、归一打包成标准桌宠 spritesheet。
- 🖥️ **常驻桌宠 App**：托盘、悬浮宠物、宠物库、设置、气泡、撒花。
- 🔌 **AI 编码联动**：接通 Claude Code / Codex / Antigravity，任务完成时桌宠实时回应。
- 🗣️ **语音包 + 提醒 + 番茄钟**：TTS 说话、原创合成音效、中文自然语言提醒、25/5 专注。

## 安装

使用桌宠 App：

```bash
cd /Users/loge/A_project/ai-desktop-pet-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[desktop]"
```

开发和测试：

```bash
pip install -e ".[dev,desktop]"
```

核心生成链路依赖 `Pillow`、`requests`、`numpy`；桌面 App 额外依赖 `PySide6` 和语音相关能力。

## 配置

项目会自动读取当前目录下的 `.env`。默认使用 OpenAI：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_TEXT_MODEL=gpt-4o-mini
```

也可以使用 OpenAI 兼容代理：

```bash
OPENAI_BASE_URL=https://your-compatible-endpoint/v1
OPENAI_API_KEY=your-provider-key
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_TEXT_MODEL=your-chat-model
```

## 生成你的桌宠

纯文字生成：

```bash
petgen generate \
  --prompt "一只圆滚滚的水豚程序员，戴小耳机，温柔、聪明、适合陪伴写代码" \
  --name "水豚程序员" \
  --output outputs/capybara-coder
```

带参考图生成：

```bash
petgen generate \
  --image /path/to/reference.png \
  --prompt "保留颜色和标志性配饰，设计成可爱桌面宠物" \
  --output outputs/from-reference
```

只处理已有源图：

```bash
petgen build --source /path/to/source.png --name "本地桌宠" --output outputs/local-pet
```

输出目录包含：

- `source.png`：模型原始返回图（仅 `generate` 写入）
- `sprite.png`：标准 `8 x 9` 桌宠 spritesheet（透明通道）
- `pet.json`：动画 manifest
- `preview.png`：首帧预览图

<p align="center">
  <img src="docs/images/spritesheet.png" alt="标准 8x9 桌宠 spritesheet 示例（透明通道，浅底便于查看）" width="430">
  <br><sub>打包出的 <code>8 × 9</code> 精灵表</sub>
</p>

## 启动桌宠 App

```bash
petgen app
```

`petgen app` 会启动系统托盘、悬浮宠物、宠物库、设置面板和 AI 事件总线。数据默认存放在 `~/.petgen/`，也可以用 `$PETGEN_DATA_DIR` 或 `--data-dir` 覆盖。

常用入口：

- 打开宠物库：浏览、选择、预览、删除宠物，也可以创建新宠物。
- 打开设置：配置 API、模型、动画、音效、语音包、人格和工具接入。
- 快速浮一只：`petgen desktop outputs/xxx --scale 1.5`。
- 快速提醒：支持「明天下午三点 开会」「每天 9点 喝水」「1小时后 吃药」。

## AI 工具接入

桌宠可以读取 AI 编码工具写入的事件，并切换到对应表情。GUI 路径：

```text
petgen app → 设置 → 🔌 工具接入
```

CLI 等价命令：

```bash
petgen tools status all
petgen tools connect all
petgen tools disconnect all
petgen event KIND TITLE [DETAIL] [SOURCE]
```

接入细节、旧 hook 迁移和手写事件协议见 [docs/integrations.md](docs/integrations.md)。

## 更多文档

- [docs/development.md](docs/development.md)：开发、测试、lint、wheel 构建和发布检查。
- [docs/integrations.md](docs/integrations.md)：Claude Code / Codex / Antigravity 接入说明。
- [docs/architecture.md](docs/architecture.md)：生成链路、运行时组件、存储和容错设计。
- [docs/troubleshooting.md](docs/troubleshooting.md)：API、PySide6、音效、提醒、切图失败等常见问题。

## 图像源图约定

为让本地切图稳定，模型输出应尽量遵守：

- 单张图，纯 `#00FF00` 绿幕背景。
- 3 行动作：第 1 行 6 帧 idle、第 2 行 4 帧 attentive、第 3 行 5 帧 happy。
- 每帧完整身体、居中，角色之间留明显绿幕间隔。
- 角色本体不要以绿色为主；同色前景与绿幕无法仅靠颜色分离。

## 许可

[MIT](LICENSE)
