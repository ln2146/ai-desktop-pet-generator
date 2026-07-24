# 开发指南

## 环境

```bash
cd /Users/loge/A_project/ai-desktop-pet-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,desktop]"
```

项目要求 Python `>=3.10`。CI 覆盖 Python 3.10 和 3.12。

## 常用命令

静态检查：

```bash
ruff check .
```

全量测试：

```bash
QT_QPA_PLATFORM=offscreen pytest
```

构建 wheel：

```bash
python -m pip wheel . --no-deps -w /tmp/petgen-wheel
```

本地 CLI 冒烟：

```bash
petgen --help
petgen tools status all
```

## 测试范围

测试覆盖：

- prompt 和 OpenAI 请求形状。
- 文本描述增强失败路径。
- 绿幕抠图、切帧、spritesheet 合成。
- manifest 校验和路径越界保护。
- SQLite 存储、迁移、提醒逻辑。
- 桌面窗口、气泡、托盘、设置面板的 offscreen 逻辑。
- AI 工具接入的配置读写和恢复。
- 音效生成、语音包选择和播放器池上限。

测试不会发起真实网络生图请求。

## 发布前检查

发布前建议至少跑：

```bash
ruff check .
QT_QPA_PLATFORM=offscreen pytest
python -m pip wheel . --no-deps -w /tmp/petgen-wheel
```

并做一次 macOS 真机冒烟：

- `petgen app` 能启动。
- 托盘菜单可打开库和设置。
- 悬浮宠物可拖动、右键、点击互动。
- 气泡位置正常。
- `petgen event task_completed "测试" "" manual` 能触发表情。
- 提醒和番茄钟到期能弹气泡。
- 语音包试听不崩溃。

## CI

GitHub Actions 在 push 到 `main` 和 pull request 时运行：

- `ruff check .`
- `pytest`

CI 环境设置 `QT_QPA_PLATFORM=offscreen`，并安装 PySide6 所需的 Linux 系统库。

## 文档维护原则

README 只保留快速上手和导航。长说明放入 `docs/`：

- 工具接入：`docs/integrations.md`
- 架构说明：`docs/architecture.md`
- 排障说明：`docs/troubleshooting.md`
- 开发验证：`docs/development.md`
