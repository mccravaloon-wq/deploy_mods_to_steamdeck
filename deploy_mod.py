#!/usr/bin/env python3
"""
Steam Deck Mod 部署工具

将本机的 mod zip 文件自动传输到 Steam Deck 并解压。
支持 SSH 密码认证（通过 sshpass）。
使用 questionary TUI 库提供交互式界面。

使用方式：
  source venv/bin/activate && ./deploy_mod.py
"""

# ── 自动激活 venv ──────────────────────────────
import os, sys
_venv = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv')
_python = os.path.join(_venv, 'bin', 'python3')
if sys.executable != _python and os.path.exists(_python):
    os.execv(_python, [_python] + sys.argv)
# ────────────────────────────────────────────────

import argparse
import os
import sys
import json
import subprocess
import shlex
from pathlib import Path

try:
    import questionary
    from questionary import Choice, Separator
    from questionary import Style as QStyle
except ImportError:
    print("需要安装 questionary: pip install questionary")
    sys.exit(1)

# ──────────── 常量 ────────────
CONFIG_DIR = os.path.expanduser("~/.config/deck_mod_deploy")
CONFIG_PATH = os.path.join(CONFIG_DIR, "profiles.json")
BACK = object()  # 返回上一级标记
EXIT = object()  # 退出程序标记

SSH_OPTS = [
    "-o", "ConnectTimeout=5",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "LogLevel=ERROR",
    "-o", "NumberOfPasswordPrompts=1",
]

# ──────────── 样式 ────────────

class Style:
    GREEN  = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED    = '\033[0;31m'
    CYAN   = '\033[0;36m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    NC     = '\033[0m'

QUESTIONARY_STYLE = QStyle([
    ('qmark',       'fg:cyan bold'),
    ('question',    'bold'),
    ('pointer',     'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected',    'fg:cyan'),
    ('answer',      'fg:cyan bold'),
    ('instruction', 'fg:gray'),
    ('separator',   'fg:gray'),
    ('text',        ''),
    ('disabled',    'fg:gray italic'),
    ('', ''),
])


def _ask(question, *args, **kwargs):
    """执行 questionary 提问。按 Esc 返回 BACK，按 Ctrl+C 退出程序。
    支持两种传参：
      _ask(questionary.text, "提示", default=...)  # 类 + 参数
      _ask(questionary.text("提示", default=...))    # 已构造的对象
    """
    if args or kwargs:
        q = question(*args, qmark="❯", style=QUESTIONARY_STYLE, **kwargs)
    elif callable(question):
        q = question(qmark="❯", style=QUESTIONARY_STYLE)
    else:
        q = question

    _add_esc_handler(q)

    try:
        result = q.ask()
    except KeyboardInterrupt:
        print()
        sys.exit(1)
    if result is None:
        return BACK
    return result


def _add_esc_handler(q):
    """给 question 对象添加 Esc 取消键绑定。"""
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    try:
        esc_kb = KeyBindings()
        @esc_kb.add('escape')
        def _cancel(event):
            event.app.exit(result=None)
        new_kb = merge_key_bindings([q.application.key_bindings, esc_kb])
        q.application.key_bindings = new_kb
    except Exception:
        pass


def info(msg):
    print(f"  {Style.GREEN}▶{Style.NC} {msg}")

def warn(msg):
    print(f"  {Style.YELLOW}⚠{Style.NC} {msg}")

def error(msg):
    print(f"  {Style.RED}✗{Style.NC} {msg}")

def success(msg):
    print(f"  {Style.GREEN}✔{Style.NC} {msg}")

def header(text):
    width = 50
    print(f"\n  {Style.BOLD}{'═' * width}{Style.NC}")
    print(f"  {Style.BOLD}  {text}{Style.NC}")
    print(f"  {Style.BOLD}{'═' * width}{Style.NC}\n")

def divider():
    print(f"  {Style.DIM}{'─' * 50}{Style.NC}")


# ──────────── 配置管理 ────────────

def _load_profiles() -> list[dict]:
    if not os.path.exists(CONFIG_PATH):
        return []
    try:
        with open(CONFIG_PATH, 'r') as f:
            data = json.load(f)
        return data.get('profiles', [])
    except (json.JSONDecodeError, IOError):
        warn(f"配置文件损坏，将重新创建: {CONFIG_PATH}")
        return []


def _save_profiles(profiles: list[dict]):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump({'profiles': profiles}, f, indent=2, ensure_ascii=False)


def _profile_label(p: dict) -> str:
    host = p.get('host', '?')
    user = p.get('user', '?')
    port = p.get('port', 22)
    label = p.get('name', f'{user}@{host}')
    return f"{label}  ({user}@{host}:{port})"


def _add_profile(profiles: list[dict]):
    print()
    info("添加新连接配置（按 Esc 取消）：")
    name = _ask(questionary.text("  配置名称"), instruction="")
    if name is BACK or not name:
        return

    profile = {'name': name}

    host = _ask(questionary.text("  主机地址"))
    if host is BACK: return
    profile['host'] = host

    port_str = _ask(questionary.text("  端口", default="22"))
    if port_str is BACK: return
    profile['port'] = int(port_str) if port_str.strip() else 22

    user = _ask(questionary.text("  用户名", default="deck"))
    if user is BACK: return
    profile['user'] = user

    pwd = _ask(questionary.password("  SSH 密码", default=""))
    if pwd is BACK: return
    profile['password'] = pwd

    sd = _ask(questionary.text("  Steam 游戏目录"))
    if sd is BACK: return
    profile['steam_dir'] = sd

    profiles.append(profile)
    _save_profiles(profiles)
    success(f"配置「{name}」已保存")


def _edit_profile(profiles: list[dict]):
    if not profiles:
        warn("暂无配置可编辑。")
        return
    choices = [Choice(_profile_label(p), value=i) for i, p in enumerate(profiles)]
    choices.append(Separator("─── 返回 ───"))
    idx = _ask(questionary.select, "选择要编辑的配置", choices=choices)
    if idx is BACK or idx == -1:
        return
    p = profiles[idx]
    info(f"编辑配置「{p['name']}」（直接回车保持原值）：")

    host = _ask(questionary.text("  主机地址", default=p.get('host', '')))
    if host is BACK: return
    p['host'] = host

    port_str = _ask(questionary.text("  端口", default=str(p.get('port', 22))))
    if port_str is BACK: return
    p['port'] = int(port_str) if port_str.strip() else p.get('port', 22)

    usr = _ask(questionary.text("  用户名", default=p.get('user', '')))
    if usr is BACK: return
    p['user'] = usr

    pwd = _ask(questionary.password("  SSH 密码", default=p.get('password', '')))
    if pwd is BACK: return
    p['password'] = pwd

    sd = _ask(questionary.text("  Steam 游戏目录", default=p.get('steam_dir', '')))
    if sd is BACK: return
    p['steam_dir'] = sd

    _save_profiles(profiles)
    success(f"配置「{p['name']}」已更新")


def _delete_profile(profiles: list[dict]):
    if not profiles:
        warn("暂无配置可删除。")
        return
    choices = [Choice(_profile_label(p), value=i) for i, p in enumerate(profiles)]
    choices.append(Separator("─── 返回 ───"))
    idx = _ask(questionary.select, "选择要删除的配置", choices=choices)
    if idx is BACK or idx == -1:
        return
    p = profiles[idx]
    result = _ask(questionary.confirm, f"确定删除配置「{p['name']}」({p.get('host', '?')})?",
                  auto_enter=False)
    if result is BACK or not result:
        return
    profiles.pop(idx)
    _save_profiles(profiles)
    success(f"配置「{p['name']}」已删除")


def manage_profiles() -> dict:
    """
    交互式选择/管理配置。
    必须选择一个配置才能继续，返回选中的 profile dict。
    在菜单处按 Esc 退出整个程序。
    """
    profiles = _load_profiles()

    while True:
        choices = []
        for i, p in enumerate(profiles):
            choices.append(Choice(_profile_label(p), value=('select', i)))

        choices.append(Separator("─── 操作 ───"))
        choices.append(Choice("+ 添加新配置",        value='add'))
        choices.append(Choice("编辑/删除配置...",     value='manage'))

        if not profiles:
            header("连接配置管理  （暂无配置，请先添加）")
        else:
            header("连接配置管理")

        result = _ask(questionary.select(
            "请选择一个连接配置", choices=choices,
            instruction="↑↓ 移动 · Enter 确认 · 输入过滤 · Esc 退出",
        ))
        if result is BACK:
            sys.exit(0)

        if isinstance(result, tuple) and result[0] == 'select':
            return profiles[result[1]]
        elif result == 'add':
            _add_profile(profiles)
        elif result == 'manage':
            mgmt = _ask(questionary.select("配置管理", choices=[
                Choice("编辑配置...",   value='edit'),
                Choice("删除配置...",   value='delete'),
                Separator("─── 返回 ───"),
            ]))
            if mgmt is BACK:
                continue
            if mgmt == 'edit':
                _edit_profile(profiles)
            elif mgmt == 'delete':
                _delete_profile(profiles)


# ──────────── SSH / SCP 辅助 ────────────

def _build_cmd(password: str, base_cmd: list[str]) -> list[str]:
    if password:
        return ["sshpass", "-p", password] + base_cmd
    return base_cmd


def ssh_test(user: str, host: str, port: int, password: str) -> bool:
    cmd = _build_cmd(password, ["ssh", *SSH_OPTS, "-p", str(port), f"{user}@{host}", "echo ok"])
    return subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0


def remote_cmd(user: str, host: str, port: int, password: str, command: str) -> str:
    cmd = _build_cmd(password, ["ssh", *SSH_OPTS, "-p", str(port), f"{user}@{host}", command])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"远程命令失败: {command}\n{result.stderr.strip()}")
    return result.stdout.strip()


def remote_cmd_ok(user: str, host: str, port: int, password: str, command: str) -> bool:
    cmd = _build_cmd(password, ["ssh", *SSH_OPTS, "-p", str(port), f"{user}@{host}", command])
    return subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0


def scp_file(local_path: str, remote_dest: str, user: str, host: str, port: int, password: str):
    cmd = _build_cmd(password, ["scp", *SSH_OPTS, "-P", str(port), local_path, remote_dest])
    subprocess.run(cmd, check=True, timeout=120)


# ──────────── 交互步骤 ────────────

def step_connect(user: str, host: str, port: int, password: str):
    """连接远程主机。返回 (user, host, port, password) 或 BACK。"""
    use_sshpass = password and subprocess.run(["sshpass", "-V"], capture_output=True, timeout=5).returncode == 0
    if not use_sshpass and password:
        warn("已配置 SSH 密码，但未找到 sshpass。")
        warn("请安装: brew install hudochenkov/sshpass/sshpass (macOS)")

    info(f"正在连接 {user}@{host}:{port} ……")
    if ssh_test(user, host, port, password):
        success("连接成功！")
        return user, host, port, password

    if password:
        warn(f"预配密码连接失败（{user}@{host}）")
    else:
        warn(f"连接失败（{user}@{host}）—— 没有配置密码")

    pw = _ask(questionary.password("SSH 密码"))
    if pw is BACK:
        return BACK
    if ssh_test(user, host, port, pw):
        success("连接成功！")
        return user, host, port, pw

    warn("连接失败，可能是 IP 不对。")
    host = _ask(questionary.text("请输入新的 IP 地址（留空返回）"))
    if host is BACK or not host:
        return BACK

    pw2 = _ask(questionary.password("SSH 密码"))
    if pw2 is BACK:
        return BACK
    if not ssh_test(user, host, port, pw2):
        error(f"连接失败 {user}@{host}:{port}")
        return BACK
    success(f"已连接到 {user}@{host}")
    return user, host, port, pw2


def step_choose_game(user: str, host: str, port: int, password: str,
                     steam_dir: str):
    """选择游戏。返回 (game_name, game_dir) 或 BACK。"""
    if not remote_cmd_ok(user, host, port, password, f"test -d {shlex.quote(steam_dir)}"):
        error(f"远程目录 {steam_dir} 不存在。")
        return BACK

    info("正在获取游戏列表……")
    raw_games = remote_cmd(user, host, port, password,
                           f"cd {shlex.quote(steam_dir)} && for d in */; do [ -d \"$d\" ] && echo \"$d\"; done")
    games = [g.rstrip('/') for g in raw_games.splitlines() if g.strip()]

    if not games:
        error(f"{steam_dir} 下没有找到任何游戏目录。")
        return BACK

    divider()
    choices = [Choice(g, value=g) for g in games]
    selected = _ask(questionary.select("请选择要导入 mod 的游戏", choices=choices,
                                       instruction="↑↓ 移动 · 输入过滤 · Enter 确认 · Esc 返回"))
    if selected is BACK:
        return BACK
    game_dir = f"{steam_dir}/{selected}"
    print()
    success(f"已选择: {game_dir}")
    return selected, game_dir


def _find_mod_dirs_remote(user: str, host: str, port: int, password: str, game_dir: str) -> list[str]:
    common_names = ["mods", "Mods", "MODS", "mod", "Mod", "MOD",
                    "bepinex", "BepInEx", "plugins", "Plugins", "loader", "PAK"]
    name_conditions = " -o ".join(f"-name '{n}'" for n in common_names)
    script = (
        f"find {shlex.quote(game_dir)} -maxdepth 8 -type d "
        f"\\( -name '.git' -o -name 'node_modules' -o -name '__pycache__' \\) -prune -o "
        f"\\( -type d \\( {name_conditions} \\) \\) -print 2>/dev/null"
    )
    raw = remote_cmd(user, host, port, password, script)
    dirs = [d.strip() for d in raw.splitlines() if d.strip() and d.startswith(game_dir)]
    return sorted(set(dirs))


def step_determine_mod_dir(user: str, host: str, port: int, password: str, game_dir: str):
    """确定 mod 目录。返回完整路径或 BACK。"""
    info("正在检查游戏目录下的文件夹（含 .app 包内深层搜索）……")

    raw = remote_cmd(user, host, port, password,
                     f"cd {shlex.quote(game_dir)} && for d in */; do [ -d \"$d\" ] && echo \"$d\"; done") or ""
    top_subdirs = [s.rstrip('/') for s in raw.splitlines() if s.strip()]

    common_names = ["mods", "Mods", "MODS", "mod", "Mod", "MOD",
                    "BepInEx", "plugins", "Plugins", "loader", "PAK"]

    for name in common_names:
        if name in top_subdirs:
            mod_dir = f"{game_dir}/{name}"
            success(f"找到 mod 目录: {mod_dir}")
            return mod_dir

    info("一级目录未找到，正在深层搜索 .app 包内结构……")
    found_dirs = _find_mod_dirs_remote(user, host, port, password, game_dir)

    if found_dirs:
        divider()
        choices = []
        for d in found_dirs:
            short = d.replace(game_dir, "", 1).lstrip('/')
            choices.append(Choice(short, value=d))
        selected = _ask(questionary.select(
            "在 .app 包内发现以下可能的 mod 目录", choices=choices,
            instruction="↑↓ 移动 · Enter 确认 · Esc 返回"))
        if selected is BACK:
            return BACK
        print()
        success(f"已选择 mod 目录: {selected}")
        return selected

    print()
    error("未找到常见的 mod 目录。")
    if top_subdirs:
        print(f"  {Style.DIM}当前游戏目录下的内容：{Style.NC}")
        for s in top_subdirs:
            if s.endswith('.app'):
                print(f"    - {s}/   {Style.DIM}(.app 包，可尝试内部如 Contents/Resources/mods){Style.NC}")
            else:
                print(f"    - {s}")
    print()
    info("请在远端手动创建好 mod 文件夹后重试。")
    return BACK


def step_local_zip():
    """选择本地 zip。返回文件路径或 BACK。"""
    divider()
    print(f"  {Style.BOLD}选择本地 mod zip 文件{Style.NC}")

    while True:
        raw = _ask(questionary.path(
            "本机 mod zip 文件路径",
            file_filter=lambda f: f.endswith('.zip') or os.path.isdir(f),
        ))
        if raw is BACK:
            return BACK
        path = os.path.expanduser(raw)
        if not path:
            continue
        if not os.path.isfile(path):
            warn(f"文件不存在: {path}")
            continue
        if not path.lower().endswith('.zip'):
            warn("文件不是 .zip 格式。")
            continue
        return os.path.abspath(path)


def step_transfer_and_extract(
    user: str, host: str, port: int, password: str,
    local_zip: str, full_mod_dir: str,
):
    filename = os.path.basename(local_zip)
    info(f"正在传输 {filename} ……")
    remote_dest = f"{user}@{host}:{full_mod_dir}/"
    scp_file(local_zip, remote_dest, user, host, port, password)
    success("文件传输完成！")

    info("正在解压缩 ……")
    remote_cmd(user, host, port, password,
        f"cd {shlex.quote(full_mod_dir)} && unzip -o {shlex.quote(filename)} && rm -f {shlex.quote(filename)}")
    success("解压缩完成！")


# ──────────── 主入口（状态机） ────────────

def _parse_args() -> argparse.Namespace:
    """解析命令行参数。提供了的参数会跳过对应的交互步骤。"""
    parser = argparse.ArgumentParser(
        prog="deploy_mod",
        description="Steam Deck Mod 部署工具。提供参数则跳过对应交互步骤。",
    )
    parser.add_argument("-p", "--profile", help="已保存的配置名称（跳过配置选择）")
    parser.add_argument("-u", "--user", help="SSH 用户名（跳过连接输入）")
    parser.add_argument("-H", "--host", help="SSH 主机地址（跳过连接输入）")
    parser.add_argument("-P", "--port", type=int, default=22, help="SSH 端口（默认 22）")
    parser.add_argument("-W", "--password", help="SSH 密码（跳过密码输入）")
    parser.add_argument("-g", "--game", help="游戏目录名（跳过游戏选择）")
    parser.add_argument("-m", "--mod-dir", help="完整 mod 目录路径（跳过 mod 目录检测）")
    parser.add_argument("-z", "--zip", help="本地 mod zip 路径（跳过文件选择）")
    parser.add_argument("--steam-dir", help="Steam 游戏根目录（覆盖配置）")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="非交互模式：遇到任何缺失必填参数直接报错退出，不进入交互")
    return parser.parse_args()


def main():
    print()
    print(f"  {Style.BOLD}╔{'═' * 46}╗{Style.NC}")
    print(f"  {Style.BOLD}║   Steam Deck Mod 部署工具 {Style.NC}")
    print(f"  {Style.BOLD}╚{'═' * 46}╝{Style.NC}")

    args = _parse_args()

    # ── 非交互模式：检查所有必需参数，缺则直接报错退出 ──
    missing = []
    if args.yes:
        # 至少要有一种连接来源：--profile，或 --host
        if not args.profile and not args.host:
            missing.append("--host 或 --profile（至少需要一种连接来源）")
        if not args.game:
            missing.append("--game")
        if not args.mod_dir:
            missing.append("--mod-dir")
        if not args.zip:
            missing.append("--zip")
        if missing:
            print(f"  {Style.RED}✗{Style.NC} 非交互模式需要以下参数：", file=sys.stderr)
            for m in missing:
                print(f"    - {m}", file=sys.stderr)
            sys.exit(1)

    # ── 提前解析 CLI 参数 → 决定哪些状态可以跳过 ──
    profile_name = args.profile
    cli_user      = args.user
    cli_host      = args.host
    cli_port      = args.port
    cli_password  = args.password
    cli_game      = args.game
    cli_mod_dir   = args.mod_dir
    cli_zip       = args.zip
    cli_steam_dir = args.steam_dir

    # 状态变量
    profile  = None
    user     = cli_user or ""
    host     = cli_host or ""
    port     = cli_port
    password = cli_password or ""
    steam_dir = ""
    game_dir  = ""
    full_mod_dir = cli_mod_dir or ""
    local_zip = cli_zip or ""

    try:
        # ── 状态机 ──
        # 跳过标记：若 CLI 已提供参数则该状态直接跳过
        skip_state1 = bool(cli_user and cli_host)
        skip_state2 = bool(cli_game and cli_steam_dir or cli_game)
        skip_state3 = bool(cli_mod_dir)
        skip_state4 = bool(cli_zip)

        state = 0  # 0=配置管理, 1=连接, 2=选游戏, 3=mod目录, 4=选文件, 5=传输解压
        while True:
            if state == 0:
                # 优先用 CLI 的 --profile；否则进入配置选择
                if profile_name:
                    profiles = _load_profiles()
                    found = next((p for p in profiles if p['name'] == profile_name), None)
                    if not found:
                        error(f"未找到配置「{profile_name}」")
                        sys.exit(1)
                    profile = found
                else:
                    if args.yes:
                        error("非交互模式：--profile 缺失且未提供 --host")
                        sys.exit(1)
                    profile = manage_profiles()
                user  = profile.get('user', 'deck')
                host  = profile.get('host', '')
                port  = profile.get('port', 22)
                password = profile.get('password', '')
                steam_dir = profile.get('steam_dir', '')
                # CLI 参数覆盖配置
                if cli_user: user = cli_user
                if cli_host: host = cli_host
                if cli_port != 22: port = cli_port
                if cli_password: password = cli_password
                if cli_steam_dir: steam_dir = cli_steam_dir
                info(f"已选用: {Style.BOLD}{profile['name']}{Style.NC}  ({user}@{host}:{port})")
                state = 1

            elif state == 1:
                if skip_state1:
                    info(f"CLI 参数已提供连接信息，跳过连接验证: {user}@{host}:{port}")
                    state = 2
                    continue
                if args.yes:
                    error("非交互模式：--host 缺失（或配置不全）")
                    sys.exit(1)
                header("1. 连接远程主机")
                r = step_connect(user, host, port, password)
                if r is BACK:
                    state = 0
                    continue
                user, host, port, password = r
                state = 2

            elif state == 2:
                if skip_state2:
                    if cli_game:
                        selected = cli_game
                        game_dir = f"{steam_dir}/{selected}"
                        info(f"CLI 参数已指定游戏: {game_dir}")
                    state = 3
                    continue
                if args.yes:
                    error("非交互模式：--game 缺失")
                    sys.exit(1)
                header("2. 选择游戏")
                r = step_choose_game(user, host, port, password, steam_dir)
                if r is BACK:
                    state = 0
                    continue
                game_name, game_dir = r
                state = 3

            elif state == 3:
                if skip_state3:
                    info(f"CLI 参数已指定 mod 目录: {full_mod_dir}")
                    state = 4
                    continue
                if args.yes:
                    error("非交互模式：--mod-dir 缺失")
                    sys.exit(1)
                header("3. 确定 Mod 目录")
                r = step_determine_mod_dir(user, host, port, password, game_dir)
                if r is BACK:
                    state = 2
                    continue
                full_mod_dir = r
                state = 4

            elif state == 4:
                if skip_state4:
                    if not os.path.isfile(local_zip):
                        error(f"--zip 文件不存在: {local_zip}")
                        sys.exit(1)
                    info(f"CLI 参数已指定 zip 文件: {local_zip}")
                    state = 5
                    continue
                if args.yes:
                    error("非交互模式：--zip 缺失")
                    sys.exit(1)
                header("4. 选择本地 Mod 文件")
                r = step_local_zip()
                if r is BACK:
                    state = 3
                    continue
                local_zip = r
                state = 5

            elif state == 5:
                header("5. 传输并解压")
                step_transfer_and_extract(user, host, port, password, local_zip, full_mod_dir)
                divider()
                print(f"  {Style.GREEN}{Style.BOLD}🎉 全部完成！{Style.NC}")
                print(f"  Mod 已部署到: {Style.CYAN}{user}@{host}:{full_mod_dir}{Style.NC}")
                divider()
                break

    except subprocess.TimeoutExpired:
        error("操作超时，请检查网络连接。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        error(f"命令执行失败: {e}")
        sys.exit(1)
    except RuntimeError as e:
        error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n  {Style.YELLOW}用户中断，退出。{Style.NC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
