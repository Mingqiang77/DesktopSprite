# DesktopSprite 初始化命令记录

本文件记录本项目（DesktopSprite）初始化 Git 仓库、关联并推送到远程仓库时实际执行的全部命令（PowerShell）。

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

> 说明：检查后发现 `DesktopSprite` 目录原本挂在上级仓库 `D:\iKun\iKun` 下（远程为 Yit / KLTN），
> 因此需要在这里单独初始化一个独立仓库。

## 2. 初始化本地仓库

```powershell
cd D:\iKun\iKun\DesktopSprite

# 在当前目录初始化一个新的 Git 仓库
git init
```

## 3. 处理目录归属（safe.directory）问题

在 Windows 上若目录属主与当前 Git 用户不一致，Git 会报
`detected dubious ownership in repository` 并拒绝执行命令（完整原因与处理记录见
[TROUBLESHOOTING.md](TROUBLESHOOTING.md)）。此时有两种处理方式：

方式一：写入全局配置（需要对应权限）：

```powershell
git config --global --add safe.directory D:/iKun/iKun/DesktopSprite
```

方式二（本次实际使用）：通过环境变量临时生效，不改动全局配置：

```powershell
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'D:/iKun/iKun/DesktopSprite'
```

> 说明：后续 Git 命令都需在该环境变量设置后执行。

方式三（永久修复，后续已执行）：把目录加入全局白名单：

```powershell
git config --global --add safe.directory D:/iKun/iKun/DesktopSprite
```

## 4. 关联远程仓库

```powershell
# 添加 GitHub 远程仓库地址
git remote add origin https://github.com/Mingqiang77/DesktopSprite.git

# 确认远程仓库已配置
git remote -v
```

## 5. 暂存并提交初始文件

```powershell
# 查看哪些文件会被跟踪（确认 .venv 和 .idea 已被 .gitignore 忽略）
git status

# 将项目文件加入暂存区
git add .

# 创建初始提交
git commit -m "初始化 DesktopSprite 项目"

# 将默认分支名从 master 改为 main
git branch -M main
```

## 6. 推送到 GitHub

```powershell
# 将本地 main 分支推送到远程并建立跟踪关系
git push -u origin main
```

> 注意：推送需要联网；若远程仓库尚未在 GitHub 上创建，请先到
> https://github.com/Mingqiang77/DesktopSprite 创建空仓库后再推送。
> 本次推送实际成功，但命令因凭据/网络等待而超时未返回，可通过下面第 7 步验证。

## 7. 验证推送结果

```powershell
# 查看远程仓库是否已有提交及分支
git ls-remote https://github.com/Mingqiang77/DesktopSprite.git

# 对比本地 HEAD 与远程分支
git rev-parse HEAD
git branch -vv
git status
```

## 8. 常用后续命令

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
