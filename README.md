# DesktopSprite

桌面精灵（Desktop Sprite）项目。

## 项目简介

DesktopSprite 是一个桌面精灵项目。当前仓库已完成初始化，并关联到 GitHub 远程仓库。

## 当前状态

- Git 仓库：已初始化，默认分支为 `main`
- 远程仓库：[https://github.com/Mingqiang77/DesktopSprite.git](https://github.com/Mingqiang77/DesktopSprite.git)
- 工作区：与远程 `origin/main` 保持同步

## 目录结构

```text
DesktopSprite/
├── .gitignore           # Git 忽略规则
├── COMMANDS.md          # 初始化及常用命令记录
├── README.md            # 项目说明（本文件）
└── TROUBLESHOOTING.md   # 故障排查记录
```

## 快速开始

```powershell
# 创建虚拟环境（如尚未创建）
python -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1
```

## 常用命令

仓库初始化、远程关联、提交推送等全部命令见 [COMMANDS.md](COMMANDS.md)。

```powershell
git status              # 查看工作区状态
git add .               # 暂存所有改动
git commit -m "提交说明" # 创建提交
git push                # 推送到远程
git pull                # 拉取远程更新
```

## 故障排查

遇到 `git add .` 报 "dubious ownership" 等问题时，参考
[TROUBLESHOOTING.md](TROUBLESHOOTING.md)。

## 远程仓库

- 地址：<https://github.com/Mingqiang77/DesktopSprite.git>
- 默认分支：`main`
