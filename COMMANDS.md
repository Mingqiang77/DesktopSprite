# DesktopSprite 初始化命令记录

本文件记录了本项目（DesktopSprite）初始化 Git 仓库及关联远程仓库所使用的全部命令。

## 1. 查看项目当前状态

```powershell
# 查看当前目录内容
Get-ChildItem -Force

# 确认当前目录是否已经属于某个 Git 仓库（若是，会显示仓库根目录）
git rev-parse --show-toplevel

# 查看已有远程仓库配置
git remote -v

# 查看当前分支和远端分支
git branch -a
```

> 说明：执行后确认 `DesktopSprite` 目录原本挂在上级仓库 `D:\iKun\iKun` 下，
> 需要为它单独初始化一个独立仓库。

## 2. 初始化本地仓库

```powershell
cd D:\iKun\iKun\DesktopSprite

# 在当前目录初始化一个新的 Git 仓库
git init
```

## 3. 关联远程仓库

```powershell
# 添加 GitHub 远程仓库地址
git remote add origin https://github.com/Mingqiang77/DesktopSprite.git

# 确认远程仓库已配置
git remote -v
```

## 4. 暂存并提交初始文件

```powershell
# 查看哪些文件会被跟踪（确认 .venv 和 .idea 已被 .gitignore 忽略）
git status

# 将项目文件加入暂存区
git add .

# 创建初始提交
git commit -m "初始化 DesktopSprite 项目"
```

## 5. 推送到 GitHub

```powershell
# 将本地 main 分支推送到远程
git push -u origin main
```

> 注意：如果远程仓库还没有在 GitHub 上创建，推送会失败，
> 需要先在 https://github.com/Mingqiang77/DesktopSprite 手动创建空仓库后再推送。

## 6. 常用后续命令

```powershell
# 查看提交历史
git log --oneline

# 查看当前状态
git status

# 拉取远程更新
git pull

# 提交新改动
git add .
git commit -m "描述本次改动"
git push
```

