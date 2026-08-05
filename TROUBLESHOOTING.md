# 故障排查记录：git add . 报错 "dubious ownership"

## 1. 现象

在执行 `git add .` 时报错，Git 拒绝操作：

```text
fatal: detected dubious ownership in repository at 'D:/iKun/iKun/DesktopSprite'
'D:/iKun/iKun/DesktopSprite' is owned by:
	ASYCN/Mingqiang.Zhang (S-1-5-21-377092140-2262755499-2929672975-31280)
but the current user is:
	SHLW11NH5105/CodexSandboxOffline (S-1-5-21-1616852645-1954540533-2330833993-1005)
To add an exception for this directory, call:
	git config --global --add safe.directory D:/iKun/iKun/DesktopSprite
```

## 2. 报错原因

这是 Git 2.35.2 起引入的 `safe.directory` 安全机制：

- Git 发现仓库所在目录 `D:\iKun\iKun\DesktopSprite` 的属主是 `Mingqiang.Zhang`，
  而当前执行 Git 命令的用户是 `CodexSandboxOffline`，两者不是同一个用户。
- 为了防止恶意用户通过共享目录篡改他人仓库，Git 默认拒绝在这种目录下执行操作，
  除非把该目录显式加入 `safe.directory` 白名单。

> 说明：本项目所在目录由 `Mingqiang.Zhang` 创建，而代码执行环境（沙箱）以
> `CodexSandboxOffline` 身份运行命令，因此触发了该安全校验。

## 3. 处理过程与结果

### 方案一（临时）：通过环境变量注入白名单

不需要修改任何配置文件，但只在当前会话有效：

```powershell
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'D:/iKun/iKun/DesktopSprite'
```

### 方案二（永久，本次最终采用）：写入全局 Git 配置

```powershell
git config --global --add safe.directory D:/iKun/iKun/DesktopSprite
```

执行后全局配置 `C:\Users\mingqiang.zhang\.gitconfig` 中新增一条白名单记录，
对所有仓库操作永久生效。

> 说明：首次以普通权限执行时提示
> `error: could not lock config file C:/Users/mingqiang.zhang/.gitconfig: Permission denied`，
> 因为该全局配置文件属主为 `Mingqiang.Zhang`；获得授权后以更高权限执行即写入成功。

## 4. 验证结果

清空环境变量后重新执行：

```powershell
Remove-Item Env:GIT_CONFIG_COUNT, Env:GIT_CONFIG_KEY_0, Env:GIT_CONFIG_VALUE_0 -ErrorAction SilentlyContinue
git add .
```

输出：

```text
git add exit=0
```

同时确认白名单记录已写入全局配置文件（来源为文件而非命令行参数）：

```powershell
git config --show-origin --get-all safe.directory
```

输出：

```text
file:C:/Users/mingqiang.zhang/.gitconfig	D:/iKun/iKun/HonmaKr
file:C:/Users/mingqiang.zhang/.gitconfig	D:/iKun/iKun/DesktopSprite
```

结论：报错已解决，`git add .` 恢复正常，无需再设置任何环境变量。

## 5. 适用场景提醒-1

- 该报错仅在“仓库目录属主 ≠ 当前 Git 用户”时出现。
- 如果平时以 `Mingqiang.Zhang` 身份直接操作本仓库（属主相同），不会触发该错误。
- 若以后在其他机器或账号下遇到同样报错，按第 3 节方案二把对应目录加入 `safe.directory` 即可。

