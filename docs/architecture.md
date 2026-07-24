# 架构概览

项目分为两条主线：生成链路和常驻桌宠运行时。

## 生成链路

```text
envfile → prompt → openai_text/openai_image → spritesheet → pet_manifest → library
```

- `envfile`：读取当前目录 `.env`。
- `prompt`：把用户描述整理成图像生成提示词。
- `openai_text`：短描述增强，可显式用 `--enrich` / `--no-enrich` 控制。
- `openai_image`：调用 OpenAI 兼容 Image API。纯文字走 `/images/generations`，参考图走 `/images/edits`。
- `spritesheet`：本地绿幕抠图、连通域切帧、归一化、合成 `8 x 9` spritesheet。
- `pet_manifest`：加载和校验 `pet.json`，拒绝越界路径和损坏 sprite。
- `library`：把生成结果登记到本地宠物库。

## 运行时

```text
store → eventbus/reminder → coordinator → tray/desktop_window/bubble
```

- `store`：SQLite 存储设置、宠物索引、AI 事件和提醒。
- `eventbus`：按字节增量读取 JSONL 事件，避免中文多字节标题导致 offset 漂移。
- `reminder_nl` / `reminder_scheduler`：中文自然语言提醒解析和到期检测。
- `coordinator`：把托盘、窗口、库、设置、事件、提醒、番茄钟串起来。
- `desktop_window`：透明桌宠窗口、动画调度、拖动、穿透、表情叠加和撒花。
- `bubble`：桌宠气泡，外部标题按纯文本处理，不渲染富文本。
- `speak` / `sound` / `voicepack`：语音包、TTS 和原创合成音效。

## 存储

默认数据目录：

```text
~/.petgen/
```

主要文件：

- `petgen.sqlite`：设置、宠物索引、事件、提醒。
- `pets/<id>/`：登记后的宠物资产。
- `task-events.jsonl`：AI 工具事件收件箱。
- `task-events.state.json`：事件总线读取 offset。
- `sfx/`：运行时生成的音效缓存。

数据库使用 `PRAGMA user_version` 做顺序迁移，并启用 WAL 以降低常驻 App 内多组件读写冲突。

## 容错边界

普通生成和资产处理倾向 fail fast：缺 API key、坏响应、坏 manifest、切图失败都会显式报错。

桌面 App 和外部 hook 有更强的不中断策略：

- hook 写事件失败只 warning 并返回 0，避免阻塞宿主 AI 工具。
- 单个损坏宠物不拖垮 App，跳过并提示。
- 设置读取遇到坏值时回到默认值，让桌宠仍可启动。
- 事件总线会跳过超长或畸形行，并按 poll 聚合 warning。

## 本地切图限制

绿幕抠图基于颜色分离。若角色主体本身是绿色，且和 `#00FF00` 背景接近，算法无法凭颜色区分前景和背景。提示词会引导模型避免绿色主体；确实需要绿色角色时，应增加非绿色肚皮、描边或配饰。
