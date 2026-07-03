# Deploy Mods to Steam Deck

将本机的 Mod zip 文件自动传输到 Steam Deck（或其他 SSH 主机）并解压部署。

## 功能

- **连接配置管理** — 多套 SSH 连接信息可视化管理（增/删/改）
- **自动连接** — 支持 sshpass 密码认证，无需手动交互
- **游戏选择** — 列出 Steam 游戏目录，方向键选择
- **Mod 目录自动检测** — 支持 macOS .app 包内深层搜索（`BepInEx`/`mods`/`plugins` 等）
- **文件传输 + 解压** — SCP 上传后远程自动解压
- **返回上一级** — 任何步骤按 Esc 可回退

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

## 配置存储

连接配置保存在 `~/.config/deck_mod_deploy/profiles.json`，可直接编辑。

## 技术栈

- Python 3 + [questionary](https://github.com/tmbo/questionary)（TUI 交互）
- SSH/SCP + sshpass（远程传输）
- 纯标准库 + 仅 questionary 外部依赖
