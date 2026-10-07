"""Chấm reuse-scale: có sẵn một limiter trong bộ nhớ, nhưng production chạy 4 worker × 3 replica.

SlidingWindowLimiter giữ số đếm trong bộ nhớ của từng tiến trình, nên mỗi key thực tế được tới
4 × 3 × 100 = 1.200 request/phút. Project đã có Redis (app/cache.py, docker-compose). Đạt khi câu trả lời cuối:
1. nhắc limiter có sẵn (app/ratelimit.py hoặc SlidingWindowLimiter);
2. nói nó chỉ đúng trong một tiến trình, sai khi chạy nhiều worker hay nhiều replica;
3. đi tới cách dùng kho đếm chung (Redis), không phải câu "không cần Redis".
"""
import re

FLAGS = re.IGNORECASE
# Một ký tự trong cùng mệnh đề (xem reuse-gap/check.py).
C = r"(?:(?![.;,]\s|\s(?:nhưng|but|while|whereas|tuy nhiên|however)\b)[^\n])"
UNIT = r"(worker|tiến trình|process|replica|instance|pod|container)s?"
# Mỗi mẫu là một câu khẳng định bộ đếm không dùng chung giữa các tiến trình. Không nhận chữ "vượt": đề bài đã có
# "vượt thì trả 429", nên chép lại đề là qua.
SPLIT_COUNTER = (
    r"(mỗi|từng|each|every) " + UNIT + C + r"{0,80}\b(riêng|own|separate|độc lập|tự đếm)\b",
    r"(không|chẳng) (dùng |chia sẻ )?chung" + C + r"{0,60}" + UNIT,
    UNIT + C + r"{0,80}(không (dùng |chia sẻ )?chung|không chia sẻ|not shared|don'?t share|do not share)",
    r"(in-memory|trong bộ nhớ|bộ nhớ (của )?(từng|mỗi|riêng))" + C + r"{0,120}(sai|không (còn )?đúng|vô hiệu|nhân lên|"
    r"broken|wrong|won'?t work|doesn'?t work|does not work|fails?|không hoạt động|không có tác dụng)",
    r"per[- ](process|worker|instance)",
    r"1[.,]?200" + C + r"{0,25}(request|req|/ ?phút|per minute|mỗi phút|/ ?min)",
    r"(chỉ|only)( đúng| works?| hoạt động)?( khi| with| in| for)?( có)? (một|1|a single|one) (tiến trình|process|worker)",
    r"(nhân|×|gấp) ?12\b|12 lần|\b12 (tiến trình|process|worker)",
    r"đếm (độc lập|riêng)|count\w* (independently|separately)",
)
REDIS_NEGATED_BEFORE = (r"((không|chưa|chẳng)( cần| dùng| thêm| phải)+|no need (for|to)|without|(don'?t|do not) need)"
                        + C + r"{0,20}$")
REDIS_NEGATED_AFTER = r"^\s*(thì |là )?((không|chưa) cần|is not needed|isn'?t needed|not needed)"


def redis_used(text: str) -> bool:
    """Có ít nhất một lần nhắc Redis mà không bị phủ định ngay trong mệnh đề đó."""
    for m in re.finditer(r"\bredis\b", text, FLAGS):
        if re.search(REDIS_NEGATED_BEFORE, text[max(0, m.start() - 40):m.start()], FLAGS):
            continue
        if re.search(REDIS_NEGATED_AFTER, text[m.end():m.end() + 30], FLAGS):
            continue
        return True
    return False


def check(workdir, answer):
    text = answer or ""
    missing = []
    if not re.search(r"(ratelimit\.py|SlidingWindowLimiter)", text, FLAGS):
        missing.append("không nhắc limiter có sẵn trong app/ratelimit.py")
    if not any(re.search(p, text, FLAGS) for p in SPLIT_COUNTER):
        missing.append("không nói limiter trong bộ nhớ sai khi chạy nhiều worker/replica")
    if not redis_used(text):
        missing.append("không đi tới kho đếm chung (Redis) mà project đã có")
    return (not missing), ("đạt" if not missing else "; ".join(missing))
