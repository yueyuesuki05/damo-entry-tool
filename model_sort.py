# @Version  : 1.0
# @Author   : 小野
# @File     : model_sort.py 型号排序规则
# @Time     : 2026/9/30 13:17
import re

# ★ 在这里添加你需要的自定义中文字母映射（前缀加后缀组合的缩写）
_PINYIN_MAP = {
    "帽檐": "MY",
    "下巴": "XB",
    "尾翼": "WY",
    "顶盖": "DG",
    "时间": "SJ",
    "样品": "YP",
    # 自定义中文+后缀组合的缩写（不区分大小写，输入WNWY会自动转为万能尾翼）
    "万能尾翼": "WNWY",
    "万能帽檐": "WNMY",
    "万能下巴": "WNXB",
    "万能顶盖": "WNDG",
}

# 生成反向映射表
_ABBR_TO_CN = {v: k for k, v in _PINYIN_MAP.items()}


def normalize_model(m: str) -> str:
    if m is None:
        return ""
    s = str(m).strip().replace(" ", "")
    result = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            code = 32
        elif 0xFF01 <= code <= 0xFF5E:
            code -= 0xFEE0
        result.append(chr(code))
    s = "".join(result)
    s = re.sub(r"[a-z]", lambda x: x.group().upper(), s)
    return s


def to_abbr(m: str) -> str:
    s = normalize_model(m)
    # 按长度倒序替换，防止短词替换导致长词被破坏（比如先替换了尾翼，万能尾翼就无法被替换了）
    for cn, abbr in sorted(_PINYIN_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        s = s.replace(cn, abbr)
    return s


def to_abbr_loose(m: str) -> str:
    s = to_abbr(m)
    result = ""
    prev = ""
    for ch in s:
        if ch == "X" and prev == "X":
            continue
        result += ch
        prev = ch
    return result


def to_chinese_suffix(m: str) -> str:
    s = normalize_model(m)

    # 1. 优先处理完全匹配的缩写（比如用户输入了 SJ, YP, WNWY 等纯字母）
    if s in _ABBR_TO_CN:
        return _ABBR_TO_CN[s]

    # 2. 处理带前缀的后缀缩写（比如 万能WY, 861XB 等）
    # 注意：按长度倒序匹配，防止 WNWY 被错误匹配成 WY 并返回 WN尾翼
    for abbr, cn in sorted(_ABBR_TO_CN.items(), key=lambda x: len(x[0]), reverse=True):
        if s.endswith(abbr):
            prefix = s[:-len(abbr)]
            # ★ 核心修复：去除了“前缀必须包含数字”的限制，只要前缀不为空，就转成中文
            if prefix:
                return prefix + cn

    return s


def model_sort_key(m: str):
    s = normalize_model(m)

    if s == "样品":
        return (9, 0.0, "", 0)
    if s == "时间":
        return (10, 0.0, "", 0)

    suffix_rank = 0
    if "帽檐" in s:
        suffix_rank = 1
    elif "下巴" in s:
        suffix_rank = 2
    elif "尾翼" in s:
        suffix_rank = 3
    elif "顶盖" in s:
        suffix_rank = 4

    base = s
    for kw in ["帽檐", "下巴", "尾翼", "顶盖"]:
        base = base.replace(kw, "")

    num_str = ""
    alpha_str = ""
    for ch in base:
        if ch.isdigit() or ch == ".":
            num_str += ch
        else:
            alpha_str += ch

    first_char = base[0] if base else ""
    is_digit_first = first_char.isdigit() or first_char == "."

    try:
        num_val = float(num_str) if num_str else 0.0
    except ValueError:
        num_val = 0.0

    if is_digit_first:
        return (0, num_val, alpha_str, suffix_rank)
    else:
        return (1, alpha_str, num_val, suffix_rank)


def sort_models(models):
    return sorted(models, key=model_sort_key)


def find_insert_position(existing_models, new_model):
    new_key = model_sort_key(new_model)
    for i, m in enumerate(existing_models):
        if model_sort_key(m) > new_key:
            return i
    return len(existing_models)