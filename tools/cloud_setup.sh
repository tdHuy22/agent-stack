#!/bin/bash
# Setup script cho environment của cloud session (claude.ai/code).
# Dán nguyên file vào ô "Setup script" của environment. Script chạy bằng root trên Ubuntu
# trước khi Claude Code mở, rồi được cache khoảng 7 ngày.
#
# Việc làm:
#   1. Tải agent-stack vào ~/Documents/Claude/agent-stack (đúng đường dẫn mà luật chung ghi cứng):
#      git clone; proxy GitHub chặn thì tải từng file qua raw.githubusercontent.com theo
#      tools/cloud-files.txt.
#   2. Trỏ ~/.claude/CLAUDE.md tới global/CLAUDE.global.md (luật chung).
#   3. Trỏ ~/.claude/skills/agent-stack tới plugin/ (Claude Code nạp thành plugin skills-dir).
#      Thêm biến môi trường CLAUDE_CODE_PLUGIN_DIRS=/root/Documents/Claude/agent-stack/plugin
#      cho environment nếu cách này không nạp.
#
# Luôn thoát 0: setup script thoát khác 0 thì phiên cloud không khởi động được.
# Biến AGENT_STACK_* chỉ để test; muốn ghim commit thì sửa REF ngay dưới đây
# (tên nhánh, tag, hay SHA đầy đủ 40 ký tự).

REF="${AGENT_STACK_REF:-main}"
REPO_URL="${AGENT_STACK_REPO_URL:-https://github.com/tdHuy22/agent-stack.git}"
RAW_BASE="${AGENT_STACK_RAW_BASE:-https://raw.githubusercontent.com/tdHuy22/agent-stack}"
DEST="${AGENT_STACK_DEST:-$HOME/Documents/Claude/agent-stack}"
MANIFEST=tools/cloud-files.txt
CORE_FILES=".agent-stack-root plugin/.claude-plugin/plugin.json global/CLAUDE.global.md"
ALLOWED_TOP=".agent-stack-root plugin global catalog.json vetted.lock routing-table.md"

say() { echo "[agent-stack] $*"; }

# Chạy lệnh với giới hạn thời gian nếu máy có `timeout` (macOS không có).
limited() {
    local secs=$1
    shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$secs" "$@"
    else
        "$@"
    fi
}

has_core() {
    local dir=$1 f
    for f in $CORE_FILES; do
        [ -f "$dir/$f" ] || return 1
    done
}

# Một dòng của danh sách file hợp lệ khi là đường dẫn tương đối an toàn trong thư mục cho phép.
valid_path() {
    local p=$1 part top
    case "$p" in
        ""|/*|*//*|*/) return 1 ;;
    esac
    printf '%s' "$p" | LC_ALL=C grep -qE '^[A-Za-z0-9._@+/-]+$' || return 1
    local IFS=/
    for part in $p; do
        case "$part" in
            ""|.|..) return 1 ;;
        esac
    done
    top=${p%%/*}
    IFS=' '
    for part in $ALLOWED_TOP; do
        [ "$top" = "$part" ] && return 0
    done
    return 1
}

# init + fetch thay cho clone để REF nhận được cả nhánh, tag và SHA đầy đủ.
fetch_git() {
    local tmp=$1
    command -v git >/dev/null 2>&1 || return 1
    git init --quiet "$tmp" && git -C "$tmp" remote add origin "$REPO_URL" || return 1
    limited 120 git -C "$tmp" fetch --quiet --depth 1 origin "$REF" 2>&1 | sed 's/^/[agent-stack] git: /'
    git -C "$tmp" checkout --quiet FETCH_HEAD 2>/dev/null && has_core "$tmp"
}

fetch_raw() {
    local tmp=$1 list line n=0
    list=$(curl -fsSL --max-time 30 "$RAW_BASE/$REF/$MANIFEST") || { say "không tải được $MANIFEST"; return 1; }
    while IFS= read -r line; do
        case "$line" in ""|\#*) continue ;; esac
        if ! valid_path "$line"; then
            say "danh sách file có dòng không hợp lệ, bỏ cả lần tải: $line"
            return 1
        fi
        mkdir -p "$tmp/$(dirname "$line")" || return 1
        curl -fsSL --max-time 60 -o "$tmp/$line" "$RAW_BASE/$REF/$line" || { say "tải lỗi: $line"; return 1; }
        n=$((n + 1))
    done <<EOF
$list
EOF
    find "$tmp" -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} +
    say "đã tải $n file qua raw.githubusercontent.com"
    has_core "$tmp"
}

# state/ (nhật ký của hook, không có trong bản tải) đi theo bản cũ vào $DEST.old; chuyển sang bản đang dùng.
move_state() {
    [ -d "$DEST.old/state" ] && [ ! -L "$DEST.old/state" ] && [ -d "$DEST" ] && [ ! -e "$DEST/state" ] \
        && mv "$DEST.old/state" "$DEST/state"
}

# Tải bản mới vào thư mục tạm cạnh đích, đủ file cốt lõi mới thay bản cũ.
install_repo() {
    local parent tmp
    # Lần trước bị ngắt giữa các bước thay thư mục: lấy lại bản cũ, hay state/ còn nằm trong bản cũ.
    if [ ! -e "$DEST" ] && [ ! -L "$DEST" ] && [ -d "$DEST.old" ]; then
        mv "$DEST.old" "$DEST" && say "đã lấy lại bản cũ từ $DEST.old"
    fi
    move_state
    if [ -d "$DEST/.git" ] && command -v git >/dev/null 2>&1; then
        git -C "$DEST" remote set-url origin "$REPO_URL" 2>/dev/null
        if limited 120 git -C "$DEST" fetch --quiet --depth 1 origin "$REF" \
            && git -C "$DEST" reset --quiet --keep FETCH_HEAD && has_core "$DEST"; then
            say "đã cập nhật $DEST ($(git -C "$DEST" rev-parse --short HEAD))"
            return 0
        fi
        say "cập nhật bằng git không được, tải lại"
    fi
    parent=$(dirname "$DEST")
    mkdir -p "$parent" || return 1
    tmp=$(mktemp -d "$parent/.agent-stack-new.XXXXXX") || return 1
    rmdir "$tmp"
    if fetch_git "$tmp"; then
        say "đã clone $REPO_URL ($REF)"
    else
        rm -rf "$tmp"
        mkdir -p "$tmp"
        say "clone không được, thử tải từng file"
        if ! fetch_raw "$tmp"; then
            rm -rf "$tmp"
            return 1
        fi
    fi
    if [ -e "$DEST" ] || [ -L "$DEST" ]; then
        rm -rf "$DEST.old" && mv "$DEST" "$DEST.old" || { rm -rf "$tmp"; return 1; }
    fi
    if ! mv "$tmp" "$DEST"; then
        [ -e "$DEST.old" ] && mv "$DEST.old" "$DEST"
        rm -rf "$tmp"
        return 1
    fi
    move_state
    rm -rf "$DEST.old"
}

# Trỏ link tới đích; file thật có sẵn (không phải link) thì sao lưu trước.
link_to() {
    local target=$1 link=$2
    mkdir -p "$(dirname "$link")" || return 1
    if [ -e "$link" ] && [ ! -L "$link" ]; then
        local backup
        backup="$link.bak-$(date +%Y%m%d%H%M%S)"
        mv "$link" "$backup" && say "đã sao lưu $link thành $backup"
    fi
    ln -sfn "$target" "$link"
}

main() {
    if [ "$(uname -s)" = "Darwin" ] && [ "${AGENT_STACK_SETUP_FORCE:-}" != "1" ]; then
        say "script này cho máy ảo cloud; trên Mac dùng ./install.sh --apply"
        return 0
    fi
    if ! install_repo; then
        has_core "$DEST" || { say "không tải được agent-stack; phiên vẫn chạy nhưng không có agent-stack"; return 0; }
        say "không tải được bản mới, dùng bản đã có ở $DEST"
    fi
    link_to "$DEST/global/CLAUDE.global.md" "$HOME/.claude/CLAUDE.md" && say "~/.claude/CLAUDE.md -> luật chung"
    link_to "$DEST/plugin" "$HOME/.claude/skills/agent-stack" && say "~/.claude/skills/agent-stack -> plugin"
    if command -v python3 >/dev/null 2>&1; then
        say "hook chạy bằng $(python3 --version 2>&1)"
    else
        say "thiếu python3: hook của agent-stack sẽ không chạy"
    fi
}

main "$@" || say "gặp lỗi không lường trước, bỏ qua"
exit 0
