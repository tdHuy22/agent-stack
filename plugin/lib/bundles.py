"""Các bộ skill và plugin (việc H5 mục 1, 20/11/2026): bộ lõi luôn nạp sẵn, bộ khác bật theo việc.

Danh sách cố định ở đây, không đọc từ file trong repo (TM-166, TM-169). Chia theo số lần dùng thật 14 ngày
(`.tmp/h/ketqua.txt`) và số ký tự nạp sẵn đo bằng `tools/preload.py`.

Bật bộ = `profile.py on <bộ>`: plugin của bộ được đặt `enabledPlugins: true` (local của project, hay user với
`--user`); skill agent-stack ngoài lõi có `disable-model-invocation: true` nên không bao giờ nằm trong danh sách nạp
sẵn, Claude đọc thẳng `SKILL.md` theo dòng của hook SessionStart (bộ đang bật) hay UserPromptSubmit (bộ chưa bật mà
việc cần). Bản ghi bộ đang bật nằm ở `state/profiles/`, do `profile.py` ghi.
"""
from __future__ import annotations

import hashlib
import os
import re
import shlex
from pathlib import Path

import agentstack as A

CORE = "loi"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCRIPT = PLUGIN_ROOT / "skills" / "project-setup" / "scripts" / "profile.py"
VENDOR = "agent-stack-vendor@agent-stack-vendor-local"

BUNDLES = {
    "loi": {
        "label": "lõi: cổng an toàn, trạng thái việc, router, trang cho người đọc, trình duyệt Aside",
        "plugins": ("agent-stack@agent-stack-local", "differential-review@agent-stack-vendor-local"),
        "skills": ("done-gate", "session-keeper", "threat-model", "vet-skill", "task-router", "progress",
                   "reader-page", "reuse-best", "recursive-session", "aside-web"),
        "keywords": (),
    },
    "bao-mat": {
        "label": "quét bảo mật cả repo (Semgrep, Claude Security)",
        "plugins": ("static-analysis@agent-stack-vendor-local", "claude-security@claude-plugins-official"),
        "skills": (),
        "keywords": ("semgrep", "codeql", "sarif", "quet bao mat", "quet lo hong", "audit ca repo", "audit bao mat",
                     "security scan", "security audit", "static analysis", "phan tich tinh", "claude security",
                     "claude-security"),
    },
    "giao-dien": {
        "label": "giao diện và trang đặc biệt (html-plan, playground, project-artifact, frontend-design)",
        "plugins": ("html-plan@agent-stack-vendor-local", "playground@claude-plugins-official",
                    "project-artifact@claude-plugins-official", VENDOR),
        "skills": (),
        "keywords": ("frontend", "landing page", "man hinh app", "poster", "html-plan", "html plan", "playground",
                     "project-artifact", "project artifact", "trang tong quan project", "mockup"),
    },
    "ml": {
        "label": "chạy job GPU trên Kaggle",
        "plugins": (VENDOR,),
        "skills": ("kaggle-gpu",),
        "keywords": ("kaggle", "gpu mien phi", "free gpu"),
    },
    "viet": {
        "label": "chỉnh văn theo giọng người dùng",
        "plugins": (),
        "skills": ("writing-voice",),
        "keywords": ("sua van", "bai luan", "essay", "cover letter", "giong van", "cho tu nhien", "doc nhu ai",
                     "bot sen", "viet lai doan van", "viet lai bai"),
    },
    "cau-hinh": {
        "label": "cấu hình riêng của project (stack.json)",
        "plugins": (),
        "skills": ("project-setup",),
        "keywords": ("stack.json", "cau hinh project", "cau hinh rieng cho project", "project-setup", "muc san",
                     "router goi y sai"),
    },
}


def non_core() -> list:
    return [name for name in BUNDLES if name != CORE]


def core_plugins() -> set:
    return set(BUNDLES[CORE]["plugins"])


def skill_md(skill: str) -> Path:
    return PLUGIN_ROOT / "skills" / skill / "SKILL.md"


def bundle_of_skill(skill: str):
    """Tên bộ chứa skill agent-stack, hay None."""
    return next((name for name, b in BUNDLES.items() if skill in b["skills"]), None)


def bundles_of_plugin(plugin_id: str) -> list:
    """Các bộ ngoài lõi chứa plugin (rỗng nếu plugin thuộc lõi hay không thuộc bộ nào)."""
    if plugin_id in core_plugins():
        return []
    return [name for name in non_core() if plugin_id in BUNDLES[name]["plugins"]]


def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()


def user_settings() -> Path:
    return config_dir() / "settings.json"


def local_settings(project: Path) -> Path:
    return Path(project) / ".claude" / "settings.local.json"


def record_path(target: Path) -> Path:
    """Bản ghi của một file settings (theo đường dẫn tuyệt đối của file)."""
    digest = hashlib.sha256(str(Path(target).expanduser().resolve()).encode()).hexdigest()[:16]
    return A.state_dir() / "profiles" / f"{digest}.json"


def recorded(target: Path, key: str) -> list:
    """Bộ ngoài lõi trong danh sách `key` ("on" hay "off") của bản ghi file settings `target`; tên lạ bị bỏ
    (TM-169)."""
    rec = A.read_json(record_path(target), {}) or {}
    values = rec.get(key) if isinstance(rec, dict) else None
    names = {v for v in values if isinstance(v, str)} if isinstance(values, list) else set()
    return [name for name in non_core() if name in names]


def recorded_on(target: Path) -> list:
    return recorded(target, "on")


def active(project) -> list:
    """Bộ ngoài lõi đang bật cho project: bật ở scope user mà local không tắt, cộng bộ bật ở local (local đè user,
    như thứ tự cài đặt của Claude Code)."""
    on = set(recorded_on(user_settings()))
    if project:
        on -= set(recorded(local_settings(project), "off"))
        on |= set(recorded_on(local_settings(project)))
    return [name for name in non_core() if name in on]


def plugin_enabled(project, plugin_id: str) -> bool:
    """Plugin đang bật theo cài đặt thật: local đè project, project đè user (như route.plugin_enabled)."""
    state = False
    paths = [user_settings()]
    if project:
        paths += [Path(project) / ".claude" / "settings.json", local_settings(project)]
    for path in paths:
        data = A.read_json(path, {}) if path.is_file() else None
        table = data.get("enabledPlugins") if isinstance(data, dict) else None
        value = table.get(plugin_id) if isinstance(table, dict) else None
        if isinstance(value, bool):
            state = value
    return state


def live(name: str, project) -> bool:
    """Bộ chỉ có plugin mà mọi plugin đã cài của nó đang bật theo cài đặt thật (ví dụ cấu hình user cũ, chưa chạy
    `loi`): coi như đã bật, khỏi gợi ý thừa."""
    b = BUNDLES[name]
    if b["skills"]:
        return False
    have = installed_plugins()
    installed = [p for p in b["plugins"] if p in have]
    return bool(installed) and all(plugin_enabled(project, p) for p in installed)


def installed_plugins() -> dict:
    data = A.read_json(config_dir() / "plugins" / "installed_plugins.json", {}) or {}
    plugins = data.get("plugins") if isinstance(data, dict) else None
    return plugins if isinstance(plugins, dict) else {}


def plugin_skill_files(plugin_id: str) -> list:
    """SKILL.md của plugin đã cài (đường dẫn cài phải nằm trong thư mục plugins của cấu hình), để đọc thẳng trước khi
    /reload-plugins nạp plugin."""
    base = (config_dir() / "plugins").resolve()
    out = []
    for entry in installed_plugins().get(plugin_id) or []:
        path = entry.get("installPath") if isinstance(entry, dict) else None
        if not isinstance(path, str):
            continue
        root = Path(path).resolve()
        if base not in root.parents:
            continue
        # SKILL.md là symlink ra ngoài thư mục cài thì bỏ (không bảo model đọc file ngoài plugin).
        out += sorted(str(p) for p in root.glob("skills/*/SKILL.md") if root in p.resolve().parents)
        break
    return out


def profile_cmd(project, *args) -> str:
    where = f" --project {shlex.quote(str(project))}" if project else ""
    return f"python3 {shlex.quote(str(PROFILE_SCRIPT))} " + " ".join(args) + where


def describe(name: str) -> str:
    """Một dòng: bộ gồm gì và đọc skill ở đâu."""
    b = BUNDLES[name]
    parts = [f"skill {s} (không nạp sẵn, đọc thẳng `{skill_md(s)}`)" for s in b["skills"]]
    if b["plugins"]:
        parts.append("plugin " + ", ".join(p.split("@")[0] for p in b["plugins"]))
    return f"`{name}` ({b['label']}): " + "; ".join(parts)


def settings_root(cwd) -> Path:
    """Thư mục mà profile.py ghi `.claude/settings.local.json` và hook tra bản ghi: gốc git (Claude Code đọc file này
    ở cả cwd lẫn gốc git, đo 20/11/2026), ngoài git thì chính cwd."""
    path = Path(cwd or os.getcwd()).expanduser().resolve()
    top = A.git_out(path, "rev-parse", "--show-toplevel") if path.is_dir() else ""
    root = Path(top.strip()).resolve() if top and top.strip() else path
    # `core.worktree` của một .git lạ có thể trỏ gốc ra thư mục tùy ý: chỉ nhận gốc là chính path hay tổ tiên của nó.
    return root if root == path or root in path.parents else path


def effective(project) -> list:
    """Bộ đang bật theo bản ghi mà plugin đã cài của bộ cũng đang bật theo cài đặt thật (bật, tắt chéo hai scope có
    thể làm hai thứ lệch nhau; review 20/11)."""
    installed = installed_plugins()
    return [n for n in active(project)
            if all(plugin_enabled(project, p) for p in BUNDLES[n]["plugins"] if p in installed)]


def session_note(project) -> str:
    """Dòng cho hook SessionStart khi có bộ ngoài lõi đang bật; rỗng nếu không."""
    on = effective(project)
    if not on:
        return ""
    return ("[agent-stack] Bộ đang bật ngoài lõi: " + " | ".join(describe(n) for n in on)
            + ". Việc hợp với skill nào thì đọc thẳng SKILL.md của nó rồi làm theo.")


def _matches(folded: str, keyword: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", folded) is not None


def matched(text: str) -> list:
    """Các bộ ngoài lõi có từ khóa khớp tin (so sau khi bỏ dấu, chữ thường)."""
    folded = A.fold(text or "")
    return [name for name in non_core() if any(_matches(folded, A.fold(k)) for k in BUNDLES[name]["keywords"])]


def asked(text: str) -> list:
    """[("on"|"off", bộ)] khi cả tin chỉ là một lệnh ngắn "bật bộ <tên>[, <tên>…]" hay "tắt bộ …" (so sau khi bỏ dấu;
    tên viết bằng dấu cách hay gạch nối; cho phép "giúp mình", "đi", "nhé"…). Câu dài hơn, câu hỏi, câu phủ định hay
    câu bàn về tính năng ("khi tắt bộ ml thì…") không tính (review fable·high 20/11)."""
    folded = re.sub(r"\s+", " ", A.fold(text or "")).strip()
    names = "|".join(re.escape(n).replace(r"\-", "[ -]") for n in non_core())
    one = rf"(?:{names})"
    pattern = (rf"(?:(?:hay|vui long|nho|giup (?:minh|toi|em)) )?(bat|tat) (?:cac )?bo ({one}(?: ?(?:,|va) ?{one})*)"
               r"(?: (?:giup|cho) (?:minh|toi|em|anh|chi))?(?: (?:di|nhe|nha|voi|len|luon))*[ .!]*")
    found = re.fullmatch(pattern, folded)
    if not found:
        return []
    action = "on" if found.group(1) == "bat" else "off"
    picked = {m.group(0).replace(" ", "-") for m in re.finditer(one, found.group(2))}
    return [(action, n) for n in non_core() if n in picked]


def asked_note(text: str, project) -> str:
    """Dòng cho hook UserPromptSubmit khi người dùng bảo bật hay tắt bộ: đúng lệnh để Claude chạy ngay."""
    wants = asked(text)
    if not wants:
        return ""
    cmds = "; ".join(f"`{profile_cmd(project, action, name)}`" for action, name in wants)
    return (f"[agent-stack] Tin của người dùng là lệnh bật/tắt bộ: chạy ngay {cmds}, rồi báo lại dòng cuối lệnh "
            "in ra; bộ có plugin thì nhắc người dùng gõ /reload-plugins (Claude không tự nạp lại được), trong lúc chờ "
            "đọc thẳng các SKILL.md lệnh in ra.")


def pending(text: str, project) -> list:
    """Bộ khớp tin mà chưa bật (theo bản ghi, hay theo cài đặt thật với bộ chỉ có plugin)."""
    on = set(effective(project))
    return [n for n in matched(text) if n not in on and not live(n, project)]


def prompt_hint(text: str, project, only=None) -> str:
    """Dòng cho hook UserPromptSubmit khi tin khớp bộ chưa bật (trong `only` nếu có); rỗng nếu không."""
    wanted = [n for n in pending(text, project) if only is None or n in only]
    if not wanted:
        return ""
    parts = []
    for name in wanted:
        b = BUNDLES[name]
        reads = [str(skill_md(s)) for s in b["skills"]]
        for plugin in b["plugins"]:
            reads += plugin_skill_files(plugin)
        read = (" Đọc thẳng ngay: " + ", ".join(f"`{p}`" for p in reads[:6]) + ".") if reads else ""
        reload = " Plugin của bộ nạp đủ (subagent, hook) sau khi người dùng gõ /reload-plugins hay ở phiên mới." \
            if b["plugins"] else ""
        parts.append(f"bộ `{name}` ({b['label']}) chưa bật: `{profile_cmd(project, 'on', name)}`.{read}{reload}")
    return ("[agent-stack] Việc này có thể cần " + " ".join(parts)
            + " Tự bật được khi việc cần (chỉ ghi cấu hình local của project); tắt lại: `profile.py off <bộ>`.")
