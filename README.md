# iKun Desktop Sprite

电脑桌面 —— iKun精灵，一起守护我们最好的 KunKun。基于 PyQt5 + pynput 实现，支持全局键盘联动、自动状态轮换、气泡提示、点击穿透与系统托盘。

---

## 分发

- Windows 单文件：`dist/iKun.exe`（本地打包产物，**不入版本库**，请用 Release 分发或自行构建）
- macOS 需自行打包（见文末「打包说明」）

## 功能特性

- **无边框透明悬浮窗**：始终置顶、不抢占焦点，只在任务栏托盘区显示图标
- **点击穿透**：宠物周围的透明区域不会挡住鼠标，宠物身后照常操作（Windows）
- **图片模式 + Fallback 绘制**：自动加载 `images/ikun.jpg`，裁掉源图边框带后去除白底；加载失败时显示矢量形象
- **五种宠物状态**：发呆、开心、困倦、被戳、打字中，各自动画不同（呼吸、弹跳、摇晃、震动、敲击）
- **全局键盘联动**：pynput 独立线程监听键盘，打字时切到打字状态；连续打字每满 30 秒触发疲劳（伸懒腰 + 气泡轮播）
- **气泡提示**：淡入淡出，3 秒后消失；疲劳时轮播 `唱🎤 / 跳💃 / Rap🎶 / 打🏀`，被戳时固定显示 `你干嘛~`
- **鼠标交互**：左键拖拽移动、单击被戳（严格区分拖拽与点击）、右键菜单（隐藏 / 重置位置 / 退出）
- **系统托盘**：显示/隐藏宠物、重置位置、退出
- **省电设计**：发呆/困倦降到 12fps，窗口隐藏时停掉全部定时器
- **高 DPI 与多屏**：支持 150%/200% 缩放，重置位置落在宠物当前所在屏幕

---

## 项目结构

```text
DesktopSprite/
├── desktop_pet.py          # 主程序（单文件运行入口）
├── desktop_pet.spec        # PyInstaller 打包配置
├── requirements.txt        # 运行依赖
├── requirements-dev.txt    # 开发 / 打包 / 测试依赖
├── tests/
│   └── test_desktop_pet.py # offscreen 模式下运行的回归测试
├── images/
│   └── ikun.jpg            # 宠物图片资源（1080x1080，打包时自动内嵌）
├── .github/workflows/
│   └── build.yml           # CI：headless 测试 → Windows exe → macOS dmg
├── build/                  # PyInstaller 构建缓存（已忽略）
└── dist/                   # 打包产物（已忽略）
```

## 环境依赖

- Python 3.10+（已在 3.14 上验证）
- PyQt5、pynput

```bash
pip install -r requirements.txt
```

## 启动方式

```bash
python desktop_pet.py
```

虚拟环境（推荐）：

```bash
python -m venv .venv
# Windows
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe desktop_pet.py

# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
python desktop_pet.py
```

## 运行测试

测试全部在 Qt 的 `offscreen` 平台下跑：不弹窗、不挂钩真实键盘。

```bash
pip install -r requirements-dev.txt
pytest -q
```

覆盖的关键行为：去白底 / 裁边框带 / 透明区域正确性、预处理耗时、跨线程按键信号、
30 秒疲劳节律、打字超时回发呆、被戳打断后接回打字、气泡不闪、点击穿透命中区、
按状态降帧、隐藏停定时器、默认位置不压任务栏。

---

## 代码逻辑概述

### 1. 窗口与初始化（`DesktopPet.__init__`）

- 无边框、透明背景、始终置顶、不接收焦点
- 启动位置 = 主屏 `availableGeometry()` 右下角（已扣除任务栏）
- `main()` 里先开 `AA_EnableHighDpiScaling`，再创建 `QApplication`
- 控制台只在"该控制台属于本进程"时才隐藏，避免连带隐藏用户自己的命令行窗口

### 2. 图片预处理（`_load_image`）

1. 多路径查找 `ikun.jpg`（`_MEIPASS` / 脚本目录 / 可执行文件目录 / CWD / 上级目录）
2. `_trim_border_bands`：裁掉四周"整行整列同色"的窄边框带（≤8px）。源图顶部有 5px 灰边，
   缩放后会在宠物头顶留下一条可见灰线，靠这一步消除
3. 按设备像素比缩放到 150×150 逻辑尺寸，高分屏不发虚
4. `_flood_fill_background`：直接读写 ARGB32 原始缓冲区做扫描线洪水填充，
   从四条边出发把连通的近白色（各通道 >240）置为透明，主体内部的白色（眼睛、高光）保留
5. `_build_pet_region`：生成逻辑像素下的非透明区域，供点击穿透判定与命中测试使用
6. 全部失败则切到 `_draw_fallback_mode` 矢量形象（不会崩溃）

### 3. 状态机（`PetState`）

| 状态 | 触发方式 | 动画表现 |
|---|---|---|
| IDLE（发呆） | 默认 / 超时恢复 | 轻微呼吸上下浮动（12fps） |
| HAPPY（开心） | 自动轮换 | 正弦波弹跳 + 腮红（30fps） |
| SLEEPY（困倦） | 自动轮换 | 缓慢浮动 + 左右摇晃 + 半闭眼（12fps） |
| POKE（被戳） | 左键单击（移动 < 5px） | 高频震动 + 眼泪 + `你干嘛~` 气泡 |
| TYPING（打字中） | 全局键盘输入 | 头部晃动 + 双手敲键盘 + 专注眼神（30fps） |

- 自动轮换间隔 **10~20 秒随机**，只在 IDLE / HAPPY / SLEEPY 之间切换（权重 5:3:2）
- 被戳 1.5 秒后自动恢复；若此时手还在打字，自动接回 TYPING 而不是发呆

### 4. 键盘联动（pynput 独立线程）

- `on_press` 运行在 pynput 子线程，**只做两件事**：记录时间戳、`emit` 一个跨线程信号
- `DesktopPet._key_event`（`pyqtSignal`）由主线程的 `_on_key_pressed` 消费；
  不能在子线程里直接调 `QTimer.singleShot` —— Qt 定时器依赖调用线程的事件循环，
  子线程没有事件循环，回调会静默失效
- 停止输入超过 **2 秒** → 回 IDLE
- 连续打字每满 **30 秒** → 伸懒腰 2 秒 + 弹一条疲劳气泡，并把 30 秒起算点推到当前时刻

### 5. 气泡系统

- **疲劳气泡**：取 `BUBBLE_TEXTS[bubble_index % len]`，每次触发后 `bubble_index += 1`
- **被戳气泡**：固定 `BUBBLE_POKE_TEXT`，不推进轮播索引
- 显示在宠物**头顶正上方**，圆角矩形 + 指向宠物的小三角，淡入 0.15/帧、淡出 0.08/帧，3 秒后淡出
- 同一时间只有一个气泡；旧气泡未消失时换文案直接替换，不会闪一下

### 6. 鼠标交互与点击穿透

- **左键按下**：记录拖拽偏移与起始位置
- **鼠标移动**：左键按住则跟随移动
- **左键释放**：用**欧氏距离**判断，< 5px 视为单击并触发被戳，否则视为拖拽
- **右键**：弹出复用同一个 `QMenu`（隐藏 / 重置位置 / 退出）
- **点击穿透**：`nativeEvent` 拦截 `WM_NCHITTEST`，命中点不在"宠物非透明区域 ∪ 可见气泡"内时
  返回 `HTTRANSPARENT`，把鼠标事件让给下层窗口。没有这一步，220×220 的透明窗会变成隐形挡板

### 7. 绘制流程（`paintEvent`）

1. 清屏为透明
2. 应用整体偏移（弹跳、摇晃）→ 以宠物中心为轴做头部倾斜 / 伸懒腰缩放
3. 绘制宠物主体（图片模式按 DPR 居中，或矢量模式）
4. 打字状态额外绘制键盘底板与交替敲击的双手
5. 重置变换，在窗口绝对坐标系绘制气泡（避免被裁切）

## 关键参数速查

| 常量 | 默认值 | 含义 |
|---|---|---|
| `PET_SIZE` / `WINDOW_SIZE` | 150 / 220 | 宠物尺寸 / 窗口尺寸 |
| `ANIMATION_FPS` / `IDLE_FPS` | 30 / 12 | 活跃帧率 / 发呆帧率 |
| `STATE_INTERVAL_MIN/MAX` | 10000 / 20000 | 自动轮换间隔（ms） |
| `TYPING_TIMEOUT` | 2000 | 停手多久回发呆（ms） |
| `TYPING_FATIGUE_TIME` | 30000 | 疲劳周期（ms） |
| `POKE_RECOVER_TIME` | 1500 | 被戳时长（ms） |
| `STRETCH_DURATION` | 2000 | 伸懒腰时长（ms） |
| `BUBBLE_SHOW_DURATION` | 3000 | 气泡停留（ms） |
| `CLICK_THRESHOLD` | 5.0 | 单击判定距离（px） |
| `MAX_BORDER_TRIM` | 8 | 源图边框带最大裁剪像素 |

---

## 打包说明

### Windows → `dist/iKun.exe`

spec 已内嵌 `images/`，产物名 `iKun`，并显式声明 pynput 平台后端：

```bash
pip install -r requirements-dev.txt
pyinstaller desktop_pet.spec --clean
# 产物：dist/iKun.exe
```

**分发时只需一个文件**：`dist/iKun.exe`

### macOS → `.app` / `.dmg`

macOS 上 PyInstaller 生成 `.app`，`.dmg` 只是分发容器。**必须**加 pynput 后端的
`--hidden-import`，否则打包后键盘联动会静默失效：

```bash
pyinstaller desktop_pet.py \
  --name iKun \
  --windowed --onefile \
  --add-data "images:images" \
  --hidden-import pynput.keyboard._darwin \
  --hidden-import pynput.mouse._darwin \
  --clean

hdiutil create -volname "iKun Desktop Sprite" \
  -srcfolder dist/iKun.app \
  -ov -format UDZO dist/iKun.dmg
```

**macOS 注意事项**：

- 需在「系统设置 → 隐私与安全性 → 辅助功能」中授权，全局键盘监听才生效
- 系统托盘、无边框置顶等行为与 Windows 略有差异；点击穿透在 macOS 上未实现

CI（`.github/workflows/build.yml`）已包含：headless 测试 → Windows exe → macOS dmg。

---

## 常见问题

1. **pynput 提示未安装**
   ```bash
   pip install pynput
   ```

2. **打字状态不触发**
   - Windows 上全局键盘钩子可能需要**管理员权限**（尤其前台窗口是管理员程序时），尝试「以管理员身份运行」
   - 部分安全软件会拦截全局钩子，请检查杀毒软件日志
   - 打包版另有专门坑：漏了 `--hidden-import pynput.keyboard._win32`（macOS 为 `_darwin`）会静默失效

3. **杀毒软件报警**
   全局键盘钩子的行为特征与键盘记录器相似，未签名的 exe 容易被拦。分发前建议做代码签名。

4. **图片加载失败**
   - 确保 `images/ikun.jpg` 存在，或与 `.exe` 同级目录下有 `images/ikun.jpg`
   - 打包后的 `.exe` 会自动解压图片到临时目录，无需手动放置
   - 加载失败不会崩溃，会退回矢量形象

5. **宠物窗口不显示**
   托盘图标右键「显示宠物」，或双击托盘图标恢复。

6. **点击桌面上的东西没反应**
   说明点到宠物本体了（宠物区域优先响应）。拖动挪开即可；透明区域是穿透的。

## 已知限制

- **图片模式下表情不随状态变化**：照片本身是静态的，被戳 / 打字只有震动、键盘双手和气泡，
  眼睛变化只在 fallback 矢量形象里生效
- **气泡宽度受限**：文案过长会被窗口边缘裁切（当前文案都很短）
- **点击穿透仅 Windows**：依赖 `WM_NCHITTEST`；macOS 上透明区域仍会吃掉鼠标事件

## 许可

[MIT License](LICENSE)
