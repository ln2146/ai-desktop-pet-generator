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

## 图像源图约定

为了让本地切图稳定，模型输出必须尽量遵守：

- 单张图，纯 `#00FF00` 绿幕背景
- 3 行动作
- 第 1 行 6 帧 idle
- 第 2 行 4 帧 attentive
- 第 3 行 5 帧 happy
- 每帧完整身体、居中、角色之间留明显绿幕间隔
