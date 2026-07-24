# 排障指南

## 找不到 `petgen`

确认已经安装当前项目：

```bash
source .venv/bin/activate
pip install -e ".[desktop]"
petgen --help
```

也可以直接用模块入口：

```bash
python -m petgen --help
```

## 缺少 API Key

生成时报：

```text
OPENAI_API_KEY is required
```

在当前目录创建 `.env`：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_IMAGE_MODEL=gpt-image-2
```

也可以在命令行显式传 `--api-key` / `--base-url`。

## PySide6 或 Qt 启动失败

桌面 App 需要安装 desktop extras：

```bash
pip install -e ".[desktop]"
```

无显示器或 CI 环境跑测试时设置：

```bash
QT_QPA_PLATFORM=offscreen pytest
```

macOS 上裸 `python` 运行时 Dock 仍可能短暂出现图标；彻底隐藏通常需要后续打成 `.app`。

## 托盘、窗口穿透或气泡位置异常

这些行为依赖真实桌面环境，offscreen 测试只能覆盖逻辑和渲染，不等价于真机体验。建议在 macOS 真机上检查：

- 托盘图标是否出现。
- 透明区是否穿透点击。
- 右键菜单是否正常。
- 气泡是否锚定在宠物附近。
- 多显示器和缩放比例下窗口是否跑偏。

## 生成结果切图失败

常见原因：

- 模型没有生成 3 行动作。
- 帧之间贴得太近，连通域被识别成一个整体。
- 背景不是纯 `#00FF00`。
- 角色主体本身偏绿色，和绿幕无法区分。

可尝试：

```bash
petgen generate --prompt "角色不要以绿色为主，使用明显非绿色描边，三行动作清晰分隔"
```

已有源图可直接调试本地后处理：

```bash
petgen build --source /path/to/source.png --output outputs/debug-build
```

## 没有声音或语音

声音功能是 best effort：

- 音效依赖 QtMultimedia 和可用音频设备。
- TTS 优先使用 `edge-tts`，失败后尝试系统 TTS。
- 静音模式或「开启音效反馈」关闭时不会播放。

内置音效如果没有随包安装，会在数据目录的 `sfx/` 下运行时生成，不需要写入安装包目录。

## 提醒解析不符合预期

支持的常见表达：

- `明天下午三点 开会`
- `今天 9点半 站会`
- `周一 10点 周会`
- `每天 9点 喝水`
- `1小时后 吃药`
- `半小时后 休息`

解析不了时，快速提醒会把整句作为标题，并默认设置为 1 小时后。

## AI 工具没有触发桌宠

先确认工具接入状态：

```bash
petgen tools status all
```

手动写一条事件：

```bash
petgen event task_completed "手动测试" "" manual
```

再检查事件文件：

```bash
tail -n 5 ~/.petgen/task-events.jsonl
```

如果事件文件有内容但桌宠不响应，确认 App 是否正在运行，以及数据目录是否和 hook 写入位置一致。工具接线固定写默认 `~/.petgen`。
