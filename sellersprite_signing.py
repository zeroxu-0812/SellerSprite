"""卖家精灵 tk 反爬签名（TKK 算法），复制自 keepa-monitor，自包含。"""


def extension_version_token(version: str) -> str:
    return f"{version.replace('.', '00', 1).replace('.', '0')}.1364508470"


def sellersprite_token(*parts: str, ext_version: str) -> str:
    values = [str(part) for part in parts if part is not None and str(part)]
    if not values:
        return ""
    return token_calculate("".join(values), ext_version)


def token_calculate(text: str, tkk: str) -> str:
    def mix(value: int, seed: str) -> int:
        index = 0
        while index < len(seed) - 2:
            shift_char = seed[index + 2]
            shift = ord(shift_char) - 87 if "a" <= shift_char else int(shift_char)
            shifted = value >> shift if seed[index + 1] == "+" else value << shift
            value = (value + shifted) & 0xFFFFFFFF if seed[index] == "+" else value ^ shifted
            index += 3
        return value

    first, second = tkk.split(".", 1)
    base = int(first or "0")
    codepoints = []
    index = 0

    while index < len(text):
        char_code = ord(text[index])
        if char_code < 0x80:
            codepoints.append(char_code)
        elif char_code < 0x800:
            codepoints.extend([char_code >> 6 | 0xC0, char_code & 0x3F | 0x80])
        elif 0xD800 == (char_code & 0xFC00) and index + 1 < len(text):
            next_code = ord(text[index + 1])
            if 0xDC00 == (next_code & 0xFC00):
                combined = 0x10000 + ((char_code & 0x3FF) << 10) + (next_code & 0x3FF)
                codepoints.extend([
                    combined >> 18 | 0xF0,
                    combined >> 12 & 0x3F | 0x80,
                    combined >> 6 & 0x3F | 0x80,
                    combined & 0x3F | 0x80,
                ])
                index += 1
            else:
                codepoints.extend([
                    char_code >> 12 | 0xE0,
                    char_code >> 6 & 0x3F | 0x80,
                    char_code & 0x3F | 0x80,
                ])
        else:
            codepoints.extend([
                char_code >> 12 | 0xE0,
                char_code >> 6 & 0x3F | 0x80,
                char_code & 0x3F | 0x80,
            ])
        index += 1

    value = base
    for codepoint in codepoints:
        value += codepoint
        value = mix(value, "+-a^+6")
    value = mix(value, "+-3^+b+-f")
    value ^= int(second or "0")

    if value < 0:
        value = 0x80000000 + (value & 0x7FFFFFFF)

    token = value % 1_000_000
    return f"{token}.{token ^ base}"
