# 打包指南 (Packaging)

把 PetGen 打包成 macOS `.app` + `.dmg`,双击直接启动桌宠。

## 前置条件

- macOS(本机架构产出本架构包,如 arm64 → arm64)
- 项目 venv 已装好桌面依赖:`pip install -e ".[desktop]"`
- 安装 PyInstaller:`pip install pyinstaller`

## 一键构建

```bash
# 从项目根目录运行
python packaging/make_app_icon.py                 # (可选)重生成 PetGen.icns 图标
pyinstaller packaging/petgen.spec --noconfirm     # 产出 dist/PetGen.app
bash packaging/make_dmg.sh                        # 产出 dist/PetGen.dmg
```

产物:
- `dist/PetGen.app` — 可运行的应用包(约 144MB,含 PySide6 运行时)
- `dist/PetGen.dmg` — 分发镜像(约 63MB,带拖拽到应用程序的布局)

## 分发给用户

用户拿到 `PetGen.dmg` 后:
1. 双击打开,把 `PetGen.app` 拖到「应用程序」文件夹
2. **首次打开需右键 → 打开**(绕过 Gatekeeper,因为本包未签名)
3. 启动后在系统托盘(菜单栏)出现图标 → 设置里填 OpenAI API Key

## 关键配置说明

| 配置 | 作用 |
|------|------|
| `launcher.py` 入口 | 双击直接进桌宠模式,绕过 CLI 的 argparse(裸双击没参数会显示帮助) |
| `datas: petgen/resources` | 保留 SVG 图标 + SFX 目录结构(theme.py/sound.py 靠 `__file__` 定位) |
| `hiddenimports` | `QtMultimedia`/`QtTextToSpeech`/`edge_tts` 在 try/except 内导入,需显式声明 |
| `LSUIElement: true` | 托盘常驻 App,启动即无 Dock 图标(比运行时 ctypes 切换更可靠) |
| `collect_submodules(petgen/aiohttp)` | 代码大量函数内动态 import;edge-tts 依赖 aiohttp 的 C 扩展 |

## 不在本次范围

- **Windows .exe**:必须 Windows CI runner 构建,本机 Mac 不能产出 `.exe`。需在 `.github/workflows` 加 Windows job。
- **代码签名/公证**:需 Apple Developer 账号。未签名包首次打开要走右键"打开"。
- **App 图标**:`packaging/PetGen.icns`(灰白小猫),用 `python packaging/make_app_icon.py` 从 `docs/images/pet-cat.png` 重新生成。

## 重新构建

```bash
rm -rf build/PetGen dist/PetGen.app dist/PetGen.dmg build/petgen
pyinstaller packaging/petgen.spec --noconfirm && bash packaging/make_dmg.sh
```
