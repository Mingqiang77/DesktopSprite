# iKun Desktop Sprite

电脑桌面 —— iKun精灵,一起守护我们最好的KunKun。基于 PyQt5 + pynput 实现，支持全局键盘联动、自动状态轮换、气泡提示与系统托盘。

---

## 功能特性

- **无边框透明悬浮窗**：始终置顶，不抢占焦点，只在任务栏托盘区显示图标
- **图片模式 + Fallback 绘制**：自动加载 `images/ikun.jpg`（去除边缘白底），加载失败时显示代码绘制的矢量形象
- **五种宠物状态**：发呆、开心、困倦、被戳、打字中，自动轮换并附带不同动画（弹跳、摇晃、呼吸、敲击等）
- **全局键盘联动**：使用 pynput 独立线程监听键盘，打字时宠物进入打字状态；连续打字 30 秒触发疲劳伸懒腰 + 气泡轮播
- **气泡提示**：淡入淡出，显示 3 秒后自动消失；疲劳时轮播 "唱🎤/跳💃/Rap🎶/打🏀"，被戳时固定显示 "你干嘛~"
- **鼠标交互**：左键拖拽移动、单击被戳（严格区分拖拽与点击）、右键菜单（隐藏 / 重置位置 / 退出）
- **系统托盘**：托盘图标右键支持显示/隐藏宠物、退出程序

---

## 项目结构

```text
DesktopSprite/
├── desktop_pet.py       # 主程序（单文件运行入口）
├── desktop_pet.spec     # PyInstaller 打包配置
├── requirements.txt     # Python 依赖
├── images/
│   └── ikun.jpg         # 宠物图片资源（1080x1080，打包时自动内嵌）
├── dist/
│   └── iKun.exe         # Windows 打包产物（单文件可执行）
├── build/               # PyInstaller 构建缓存
└── README.md            # 本文件
```

---

## 环境依赖

- Python 3.10+
- PyQt5
- pynput

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 启动方式

### 源码运行

```bash
python desktop_pet.py
```

### 虚拟环境运行（推荐）

```bash
# 创建虚拟环境
python -m venv .venv

# Windows
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe desktop_pet.py

# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
python desktop_pet.py
```

---

## 代码逻辑概述

### 1. 窗口与初始化（`DesktopPet.__init__`）

- 设置无边框、透明背景、始终置顶、不抢夺焦点的窗口属性
- 启动位置固定在**屏幕右下角**（预留任务栏空间）
- 初始化系统托盘图标与右键菜单
- 启动 **pynput 键盘监听独立线程**，捕获全局按键事件

### 2. 图片加载（`_load_image`）

- 多路径查找 `ikun.jpg`（兼容源码运行与 PyInstaller 打包后的 `_MEIPASS` 临时目录）
- 加载成功后先等比缩放至 150×150，再通过 **Flood Fill（洪水填充）** 从图片四条边开始去除边缘连通的白色背景，保留主体内部的白色（如眼睛、高光）
- 图片加载失败时切换为 **Fallback 矢量绘制模式**（黄色圆脸 + 中分 + 表情）

### 3. 状态机（`PetState`）

内置 5 种状态，通过 `QTimer` 自动轮换或事件触发：

| 状态 | 触发方式 | 动画表现 |
|---|---|---|
| IDLE（发呆） | 默认 / 超时恢复 | 轻微呼吸上下浮动 |
| HAPPY（开心） | 自动轮换（10~20s） | 正弦波弹跳 + 腮红 |
| SLEEPY（困倦） | 自动轮换（10~20s） | 缓慢浮动 + 左右摇晃 + 半闭眼 |
| POKE（被戳） | 鼠标单击（移动 < 5px） | 高频震动 + 眼泪 + "你干嘛~" 气泡 |
| TYPING（打字中） | 全局键盘输入 | 头部晃动 + 双手敲击键盘 + 专注眼神 |

- 状态切换间隔：**10~20 秒随机**（排除被戳与打字状态）
- 被戳状态 1.5 秒后自动恢复发呆

### 4. 键盘联动（`pynput` 独立线程）

- `keyboard.Listener` 在后台线程运行，通过 `on_press` 记录按键时间戳
- 首次按键 → `QTimer.singleShot` 切回主线程进入 **TYPING 状态**
- 停止输入超过 **2 秒** → 自动恢复发呆
- 连续输入超过 **30 秒** → 触发疲劳：伸懒腰动画 + 按顺序轮播 `BUBBLE_TEXTS` 气泡

### 5. 气泡系统

- **疲劳气泡**：取 `BUBBLE_TEXTS[bubble_index % len]`，显示后 `bubble_index += 1`
- **被戳气泡**：固定显示 `BUBBLE_POKE_TEXT`，不影响轮播索引
- 显示在宠物**头顶正上方**，圆角矩形，带淡入淡出，3 秒后自动消失
- 同一时间只显示一个气泡，新气泡出现时旧气泡立即关闭

### 6. 鼠标交互

- **左键按下**：记录拖拽偏移与起始位置
- **鼠标移动**：若左键按住则跟随移动
- **左键释放**：计算移动距离（曼哈顿距离），若 **< 5 像素** 视为单击，触发被戳；否则视为拖拽，不触发
- **右键**：弹出菜单（隐藏 / 重置位置 / 退出）

### 7. 绘制流程（`paintEvent`）

1. 应用整体偏移（弹跳、摇晃）
2. 应用头部倾斜 / 伸懒腰变换（绕宠物中心旋转/缩放）
3. 绘制宠物主体（图片模式或 Fallback 矢量模式）
4. 若为打字状态：绘制键盘底板 → 绘制双手（交替敲击）
5. 重置变换，在窗口绝对坐标系中绘制气泡（避免被裁切）

---

## 打包说明

### Windows → `.exe`

已配置 `desktop_pet.spec`，图片通过 `datas=[('images', 'images')]` 自动内嵌到单文件 EXE 中。

```bash
# 使用 spec 打包
pyinstaller desktop_pet.spec --clean

# 重命名为 iKun.exe
mv dist/desktop_pet.exe dist/iKun.exe
```

**分发时只需一个文件**：`dist/iKun.exe`

### macOS → `.app` / `.dmg`

macOS 上 PyInstaller 默认生成 `.app` 应用包（而非单文件），`.dmg` 仅作为分发容器。

```bash
# 1. 打包为 .app
pyinstaller desktop_pet.py \
  --name iKun \
  --windowed \
  --add-data "images:images" \
  --hidden-import pynput.keyboard._darwin \
  --clean

# 2. 制作 .dmg（将 .app 放入磁盘映像）
hdiutil create -volname "iKun Desktop Sprite" \
  -srcfolder dist/iKun.app \
  -ov -format UDZO \
  dist/iKun.dmg
```

**macOS 注意事项**：
- 代码中 `sys.platform == "win32"` 的判断会自动跳过 Windows 专属逻辑（如隐藏控制台），不影响运行
- 系统托盘、无边框置顶等行为在 macOS 上可能与 Windows 表现略有差异，建议针对性测试

---

## 常见问题

1. **pynput 提示未安装**
   ```bash
   pip install pynput
   ```

2. **打字状态不触发**
   - Windows 上全局键盘钩子可能需要**管理员权限**，尝试右键 "以管理员身份运行"
   - 部分安全软件会拦截全局钩子，请检查杀毒软件日志

3. **图片加载失败**
   - 确保 `images/ikun.jpg` 存在，或与 `.exe` 同级目录下有 `images/ikun.jpg`
   - 打包后的 `.exe` 会自动解压图片到临时目录，无需手动放置

4. **宠物窗口不显示**
   - 检查是否点击了 "隐藏宠物"，双击托盘图标或托盘右键 "显示宠物" 即可恢复