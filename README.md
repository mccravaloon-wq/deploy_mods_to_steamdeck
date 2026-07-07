# Deploy Mods to Steam Deck

将本机的 Mod zip 文件自动传输到 Steam Deck（或其他 SSH 主机）并解压部署。

## 功能

- **连接配置管理** — 多套 SSH 连接信息可视化管理（增/删/改）
- **自动连接** — 支持 sshpass 密码认证，无需手动交互
- **游戏选择** — 列出 Steam 游戏目录，方向键选择
- **Mod 目录自动检测** — 支持 macOS .app 包内深层搜索（`BepInEx`/`mods`/`plugins` 等）
- **文件传输 + 解压** — SCP 上传后远程自动解压
- **返回上一级** — 任何步骤按 Esc 可回退
- **CLI 参数跳过交互** — 传哪个参数就跳过哪一步
- **非交互模式** — `-y` 模式缺参即报错，适合脚本/cron 调用

## 环境要求

- Python 3.9+
- SSH 客户端（`ssh` / `scp`）
- 【可选】`sshpass` — 如需配置 SSH 密码自动认证
  - macOS: `brew install hudochenkov/sshpass/sshpass`
  - Linux: `sudo apt install sshpass`

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install questionary

# 2. 运行（会自动激活 venv）
./deploy_mod.py
```

首次运行会自动引导创建连接配置，后续可直接选择已保存的配置使用。

## 使用流程

```
选择配置 → 连接主机 → 选择游戏 → 确定 Mod 目录 → 选择本地 zip → 传输部署
                     ↑  Esc 回退  ←──── Esc 回退  ←──── Esc 回退
```

按 **Esc** 回退到上一步，按 **Ctrl+C** 随时终止脚本。

## CLI 参数

```
./deploy_mod.py [选项]
```

| 短 | 长 | 说明 |
|----|----|------|
| `-p` | `--profile` | 已保存的配置名称（跳过配置选择） |
| `-u` | `--user` | SSH 用户名 |
| `-H` | `--host` | SSH 主机地址 |
| `-P` | `--port` | SSH 端口（默认 22） |
| `-W` | `--password` | SSH 密码 |
| `-g` | `--game` | 游戏目录名 |
| `-m` | `--mod-dir` | 完整 mod 目录路径 |
| `-z` | `--zip` | 本地 mod zip 路径 |
| | `--steam-dir` | Steam 游戏根目录（覆盖配置） |
| `-y` | `--yes` | 非交互模式：缺任何必填参数直接报错退出 |

### 示例

```bash
# 完全交互
./deploy_mod.py

# 部分跳过：指定连接和 zip，其它仍交互
./deploy_mod.py -H 192.168.101.91 -W mypassword -z ~/Downloads/mod.zip

# 完全非交互
./deploy_mod.py -y -p "Steam Deck 办公室" \
                -g "Stardew Valley" \
                -m "/run/media/deck/.../Stardew Valley.app/Contents/MacOS/Mods" \
                -z ~/Downloads/mod.zip
```

`-y` 模式会在启动时和每步前校验所有必填参数，缺失立即报错退出，不会卡在交互界面。

## 配置存储

连接配置保存在 `~/.config/deck_mod_deploy/profiles.json`，可直接编辑。

## 技术栈

- Python 3 + [questionary](https://github.com/tmbo/questionary)（TUI 交互）
- SSH/SCP + sshpass（远程传输）
- 纯标准库 + 仅 questionary 外部依赖