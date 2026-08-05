# DesktopSprite

桌面 iKun 宠物（Desktop iKun Pet）—— 一个基于 PyQt5 的 Windows 桌面悬浮宠物程序。

## 功能特性

- 无边框、置顶、背景透明的悬浮窗口，宠物始终浮在所有窗口最上层
- 鼠标左键单击宠物触发随机表情动画，按住可拖拽移动位置
- 内置多种状态：发呆、开心、困倦、被戳，自动轮换
- 右键菜单与系统托盘：显示宠物、隐藏宠物、重置位置、退出程序
- 优先加载 `images/ikun.jpg` 宠物形象，找不到图片时自动回退为纯代码绘制的矢量小鸡（带 iKun 中分发型和篮球元素）
- 支持 PyInstaller 打包为单文件 exe，运行时无控制台黑框

## 目录结构

```text
DesktopSprite/
├── desktop_pet.py      # 主程序（窗口、状态机、动画、托盘）
├── desktop_pet.spec    # PyInstaller 打包配置
├── images/ikun.jpg     # 宠物形象图片
├── requirements.txt    # Python 依赖
├── skills.md           # 需求说明
└── README.md           # 项目说明（本文件）
```

## 环境要求

- Windows
- Python 3.x
- PyQt5（见 `requirements.txt`）

## 快速开始

```powershell
# 1. 创建并激活虚拟环境（可选）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python desktop_pet.py
```

## 打包为 exe

```powershell
pip install pyinstaller
pyinstaller desktop_pet.spec
```

打包完成后，单文件程序位于 `dist/desktop_pet.exe`，双击即可运行（无控制台窗口）。

## 使用说明

- 左键单击宠物：随机表情动画
- 按住左键拖拽：移动宠物位置
- 右键单击宠物或托盘图标：显示菜单（显示 / 隐藏宠物、重置位置、退出程序）
- 双击托盘图标：重新显示宠物

## 远程仓库

- 地址：<https://github.com/Mingqiang77/DesktopSprite.git>
- 默认分支：`main`
