#!/usr/bin/env python3
"""通过 kedou.life 在线字幕服务抓取视频平台的 AI 字幕（支持 Bilibili / YouTube）。
纯 Python 标准库实现（零 pip 依赖）。

接口 body 需要 RSA+AES 加密（逆向自其前端，详见 reference/kedou-api.md）：
  1) GET  /api/auth/keys              -> { k1: RSA 公钥, k2: 用私钥加密的 AES 密钥 }
  2) aes_key = 公钥运算(k1, k2)       -> AES 密钥（实测 16 字符 -> AES-128，PKCS#1 type-01 块）
  3) encrypted = AES-128-CBC/Pkcs7({"url":...}, key=aes_key, iv=base64 解码前 16 字节)
  4) body = RSA-PKCS1#1v1.5 每 117 字符一块，块字节拼接后 base64（前端 encryptLong 等价）
  5) POST /api/video/subtitleExtract  body=body  header 带 KdSystem: Kedou

输出：``<workdir>/subs/kedou_<视频ID>.json``，其中
``data.subtitleItemVoList[0].content`` 即 SRT 文本（部分平台 content 为空、
只有 srcUrl，脚本会自动下载回填）。

目录约定：每个视频一个以 ``--bv``（视频 ID）命名的子目录，多个视频天然共存。

用法:
    python subtitle_fetch.py --workdir <dir> --bv BV1xxxx
    python subtitle_fetch.py --platform youtube --bv dQw4w9WgXcQ --workdir <dir>
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import urllib.request


def _force_utf8_stdio() -> None:
    """Windows/Git Bash（GBK）下把中文输出统一为 UTF-8，避免乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 服务端常量
AES_IV_B64 = "a2Vkb3VAODk4OSE2MzIzMw=="  # base64("kedou@8989!63233")，取前 16 字节作 IV
API_BASE = "https://www.kedou.life"
KEYS_ENDPOINT = API_BASE + "/api/auth/keys"
EXTRACT_ENDPOINT = API_BASE + "/api/video/subtitleExtract"
HTTP_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "Chrome/120 Safari/537.36"),
    "Referer": API_BASE + "/caption/subtitle/bilibili",
    "Origin": API_BASE,
    "KdSystem": "Kedou",
    "Content-Type": "application/json",
}
REQUEST_TIMEOUT_SEC = 30

# 支持的视频平台：视频页 URL 构造规则
PLATFORM_URLS = {
    "bilibili": lambda video_id: f"https://www.bilibili.com/video/{video_id}/",
    "youtube": lambda video_id: f"https://www.youtube.com/watch?v={video_id}",
}

# RSA 分块参数（对应前端 encryptLong：文本不超过该长度时单块加密，否则按 RSA_CHUNK_SIZE 分块）
RSA_SINGLE_BLOCK_LIMIT = 245
RSA_CHUNK_SIZE = 117
# PKCS#1 v1.5 填充最少 11 字节：00 02 PS(>=8) 00
PKCS1_MIN_PADDING = 11


# ---------------------------------------------------------------- DER/ASN.1 解析
def _parse_der_tlv(data: bytes, index: int) -> tuple[int, bytes, int]:
    """解析一个 DER TLV 结构，返回 (tag, value, 下一结构的起始下标)。"""
    tag = data[index]
    index += 1
    length = data[index]
    index += 1
    if length & 0x80:  # 长格式：低位字节数表示后续多少字节是真实长度
        num_length_bytes = length & 0x7F
        length = int.from_bytes(data[index:index + num_length_bytes], "big")
        index += num_length_bytes
    return tag, data[index:index + length], index + length


def load_rsa_public_key(spki_b64: str) -> tuple[int, int, int]:
    """从 base64 的 SubjectPublicKeyInfo 中提取 (modulus n, exponent e, 字节长度 klen)。"""
    der = base64.b64decode(spki_b64)
    _, spki, _ = _parse_der_tlv(der, 0)          # 外层 SEQUENCE
    _, _, offset = _parse_der_tlv(spki, 0)       # AlgorithmIdentifier（跳过）
    _, bit_string, _ = _parse_der_tlv(spki, offset)
    public_key_bytes = bit_string[1:]            # 去掉 BIT STRING 的未用位数 0x00
    _, inner, _ = _parse_der_tlv(public_key_bytes, 0)   # RSAPublicKey SEQUENCE
    _, modulus_bytes, offset = _parse_der_tlv(inner, 0)
    _, exponent_bytes, _ = _parse_der_tlv(inner, offset)
    modulus = int.from_bytes(modulus_bytes.lstrip(b"\x00"), "big")
    exponent = int.from_bytes(exponent_bytes.lstrip(b"\x00"), "big")
    key_byte_length = (modulus.bit_length() + 7) // 8
    return modulus, exponent, key_byte_length


# ---------------------------------------------------------------- PKCS#1 v1.5
def rsa_public_encrypt_pkcs1(modulus: int, exponent: int, key_byte_length: int,
                             message: bytes) -> bytes:
    """PKCS#1 v1.5 type-02 公钥加密：EM = 00 02 PS(nonzero) 00 msg，C = EM^e mod n。"""
    max_message_length = key_byte_length - PKCS1_MIN_PADDING
    if len(message) > max_message_length:
        raise ValueError(f"加密块超长：{len(message)} > {max_message_length}")
    padding = bytes(random.randint(1, 255)
                    for _ in range(key_byte_length - len(message) - 3))
    encoded_message = b"\x00\x02" + padding + b"\x00" + message
    ciphertext = pow(int.from_bytes(encoded_message, "big"), exponent, modulus)
    return ciphertext.to_bytes(key_byte_length, "big")


def rsa_public_decrypt_pkcs1(modulus: int, exponent: int, key_byte_length: int,
                             ciphertext: bytes) -> bytes:
    """PKCS#1 v1.5 type-01 的"公钥运算"（等价 Node 的 publicDecrypt）。

    服务端用私钥签名 AES 密钥（EM = 00 01 FF..FF 00 msg），这里用公钥还原。
    """
    value = int.from_bytes(ciphertext, "big")
    encoded_message = pow(value, exponent, modulus).to_bytes(key_byte_length, "big")
    separator_index = encoded_message.find(b"\x00", 2)   # 00 01 FF..FF 00 MSG
    if encoded_message[0:2] != b"\x00\x01" or separator_index == -1:
        raise ValueError("type-01 填充不匹配")
    message = encoded_message[separator_index + 1:]
    if not message:
        raise ValueError("空报文")
    return message


def rsa_encrypt_long(modulus: int, exponent: int, key_byte_length: int,
                     text: str) -> bytes:
    """与前端 encryptLong 一致：超过单块上限按 RSA_CHUNK_SIZE 字符分块（PKCS#1 v1.5），块拼接。"""
    if len(text) <= RSA_SINGLE_BLOCK_LIMIT:
        chunks = [text]
    else:
        chunks = [text[i:i + RSA_CHUNK_SIZE] for i in range(0, len(text), RSA_CHUNK_SIZE)]
    return b"".join(
        rsa_public_encrypt_pkcs1(modulus, exponent, key_byte_length, chunk.encode("utf-8"))
        for chunk in chunks
    )


# ---------------------------------------------------------------- AES-CBC（纯 Python 实现）
_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D]


def _gf_mul(a: int, b: int) -> int:
    """GF(2^8) 乘法（模 x^8+x^4+x^3+x+1）。"""
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else (a << 1)
        b >>= 1
    return result


def _expand_key_schedule(key: bytes) -> list[bytes]:
    """按 AES-128/192/256 展开轮密钥，返回每轮 16 字节的列序密钥块。"""
    num_words = len(key) // 4
    num_rounds = num_words + 6
    words = [list(key[4 * i:4 * i + 4]) for i in range(num_words)]
    for i in range(num_words, 4 * (num_rounds + 1)):
        temp = list(words[i - 1])
        if i % num_words == 0:
            temp = temp[1:] + temp[:1]                 # RotWord
            temp = [_SBOX[x] for x in temp]            # SubWord
            temp[0] ^= _RCON[i // num_words - 1]
        elif num_words > 6 and i % num_words == 4:
            temp = [_SBOX[x] for x in temp]
        words.append([a ^ b for a, b in zip(words[i - num_words], temp)])

    round_keys = []
    column_group = []
    for word in words:
        column_group.append(word)
        if len(column_group) == 4:
            round_keys.append(bytes(column_group[0] + column_group[1]
                                    + column_group[2] + column_group[3]))
            column_group = []
    return round_keys


def _encrypt_block(block: bytes, round_keys: list[bytes]) -> bytes:
    """加密单个 16 字节块；block[4c+r] 为第 c 列第 r 行，返回同序密文。"""
    num_rounds = len(round_keys) - 1
    state = [[block[4 * c + r] for c in range(4)] for r in range(4)]  # state[行][列]

    def add_round_key(round_key: bytes) -> None:
        for r in range(4):
            for c in range(4):
                state[r][c] ^= round_key[4 * c + r]

    add_round_key(round_keys[0])
    for round_index in range(1, num_rounds + 1):
        for r in range(4):                                     # SubBytes
            for c in range(4):
                state[r][c] = _SBOX[state[r][c]]
        state = [state[r][r:] + state[r][:r] for r in range(4)]  # ShiftRows
        if round_index != num_rounds:                            # MixColumns（末轮跳过）
            for c in range(4):
                col = [state[0][c], state[1][c], state[2][c], state[3][c]]
                state[0][c] = _gf_mul(col[0], 2) ^ _gf_mul(col[1], 3) ^ col[2] ^ col[3]
                state[1][c] = col[0] ^ _gf_mul(col[1], 2) ^ _gf_mul(col[2], 3) ^ col[3]
                state[2][c] = col[0] ^ col[1] ^ _gf_mul(col[2], 2) ^ _gf_mul(col[3], 3)
                state[3][c] = _gf_mul(col[0], 3) ^ col[1] ^ col[2] ^ _gf_mul(col[3], 2)
        add_round_key(round_keys[round_index])
    return bytes(state[r][c] for c in range(4) for r in range(4))


def aes_cbc_encrypt_pkcs7(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-CBC 加密 + PKCS#7 填充。"""
    round_keys = _expand_key_schedule(key)
    pad_length = 16 - len(plaintext) % 16
    plaintext += bytes([pad_length]) * pad_length

    previous_block = iv[:16]
    ciphertext = bytearray()
    for offset in range(0, len(plaintext), 16):
        xored = bytes(a ^ b for a, b in zip(plaintext[offset:offset + 16], previous_block))
        encrypted_block = _encrypt_block(xored, round_keys)
        ciphertext += encrypted_block
        previous_block = encrypted_block
    return bytes(ciphertext)


# ---------------------------------------------------------------- 主流程
def request_json(url: str, body: bytes | None = None) -> dict:
    """发送 HTTP 请求并解析 JSON 响应。"""
    request = urllib.request.Request(url, data=body, headers=HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as response:
        return json.loads(response.read().decode("utf-8"))


def encrypt_video_url(video_url: str) -> str:
    """按接口约定加密 {"url": video_url}，返回可直接作为 POST body 的 base64 字符串。"""
    key_response = request_json(KEYS_ENDPOINT)
    if key_response.get("code") != 200:
        raise RuntimeError("获取公钥失败: " + json.dumps(key_response, ensure_ascii=False))

    public_key_b64 = key_response["data"]["k1"]
    encrypted_aes_key_b64 = key_response["data"]["k2"]
    modulus, exponent, key_byte_length = load_rsa_public_key(public_key_b64)
    aes_key = rsa_public_decrypt_pkcs1(
        modulus, exponent, key_byte_length, base64.b64decode(encrypted_aes_key_b64)
    ).decode("utf-8")

    iv = base64.b64decode(AES_IV_B64)[:16]
    plaintext = json.dumps({"url": video_url}, separators=(",", ":")).encode("utf-8")
    aes_encrypted = base64.b64encode(
        aes_cbc_encrypt_pkcs7(plaintext, aes_key.encode("utf-8"), iv)
    ).decode()
    rsa_encrypted = rsa_encrypt_long(modulus, exponent, key_byte_length, aes_encrypted)
    return base64.b64encode(rsa_encrypted).decode()


def fetch_subtitle(video_url: str) -> dict:
    """请求字幕提取接口，返回原始 JSON 响应。"""
    body = encrypt_video_url(video_url).encode("utf-8")
    return request_json(EXTRACT_ENDPOINT, body)


def resolve_subtitle_content(response: dict) -> str:
    """从响应中取出 SRT 文本；kedou 对部分平台只回字幕源地址而不内联文本。

    YouTube 等平台的响应里 ``content`` 可能为 null，同时给一个 ``srcUrl``
    （指向平台官方字幕，内容即标准 SRT）。此时下载 srcUrl 并回填到
    content，保证下游 build_transcript.py 拿到统一格式。
    """
    items = (response.get("data") or {}).get("subtitleItemVoList") or []
    if not items:
        return ""
    item = items[0]
    content = item.get("content") or ""
    if content or not item.get("srcUrl"):
        return content
    request = urllib.request.Request(item["srcUrl"],
                                     headers={"User-Agent": HTTP_HEADERS["User-Agent"]})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as resp:
        content = resp.read().decode("utf-8", errors="replace")
    item["content"] = content
    return content


def build_video_url(platform: str, video_id: str) -> str:
    """按平台构造视频页 URL（kedou 用它定位视频）。"""
    builder = PLATFORM_URLS.get(platform)
    if builder is None:
        raise ValueError(f"不支持的平台: {platform}（可选: {', '.join(PLATFORM_URLS)}）")
    return builder(video_id)


# ---------------------------------------------------------------- CLI
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通过 kedou.life 抓取视频平台的 AI 字幕")
    parser.add_argument("--workdir", required=True,
                        help="工作目录（输出到 <workdir>/subs/kedou_<视频ID>.json）")
    parser.add_argument("--bv", required=True,
                        help="视频 ID：B 站为 BV 号，YouTube 为 11 位视频 ID")
    parser.add_argument("--platform", default="bilibili", choices=sorted(PLATFORM_URLS),
                        help="视频平台，默认 bilibili")
    return parser.parse_args()


def main() -> None:
    _force_utf8_stdio()
    args = parse_args()
    subs_dir = os.path.join(args.workdir, "subs")
    os.makedirs(subs_dir, exist_ok=True)
    video_url = build_video_url(args.platform, args.bv)
    output_path = os.path.join(subs_dir, f"kedou_{args.bv}.json")
    try:
        response = fetch_subtitle(video_url)
        subtitle_items = (response.get("data") or {}).get("subtitleItemVoList") or []
        srt_text = resolve_subtitle_content(response)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(response, f, ensure_ascii=False)
        print(f"{args.bv}: ok code={response.get('code')} "
              f"status={response.get('data', {}).get('status')} "
              f"tracks={len(subtitle_items)} srt_bytes={len(srt_text.encode('utf-8'))} -> {output_path}")
    except Exception as exc:
        print(f"{args.bv}: ERR {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
