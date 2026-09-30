#!/usr/bin/env python3
"""通过 kedou.life 在线字幕服务抓取 B 站 AI 字幕。纯 Python 标准库实现（零 pip 依赖）。

接口 body 需要 RSA+AES 加密（逆向自其前端，详见 reference/kedou-api.md）：
  1) GET  /api/auth/keys              -> { k1: RSA 公钥, k2: 用私钥加密的 AES 密钥 }
  2) d  = 公钥运算(k1, k2)            -> AES 密钥（实测 16 字符 -> AES-128，PKCS#1 type-01 块）
  3) f  = AES-128-CBC/Pkcs7({\"url\":...}, key=d, iv=base64 解码前 16 字节)
  4) f2 = RSA-PKCS1#1v1.5 每 117 字符一块，块字节拼接后 base64（encryptLong 等价）
  5) POST /api/video/subtitleExtract  body=f2  header 带 kdsystem: Kedou

用法:
  python scripts/kedou_fetch.py --out <subs目录> --bv BV1xxxx --parts 1,2,3 [--delay 6]
"""
import argparse
import base64
import binascii
import json
import os
import random
import time
import urllib.request

IV_B64 = "a2Vkb3VAODk4OSE2MzIzMw=="
BASE = "https://www.kedou.life"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/120 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": BASE + "/caption/subtitle/bilibili",
           "Origin": BASE, "KdSystem": "Kedou", "Content-Type": "application/json"}


# ---------------------------------------------------------------- ASN.1/ RSA
def _tlv(data, i):
    """解析一个 DER TLV，返回 (tag, value, next_index)。"""
    tag = data[i]
    i += 1
    ln = data[i]; i += 1
    if ln & 0x80:
        nbytes = ln & 0x7F
        ln = int.from_bytes(data[i:i + nbytes], "big"); i += nbytes
    return tag, data[i:i + ln], i + ln


def rsa_pubkey_from_spki_b64(k1: str):
    """从 base64 的 SubjectPublicKeyInfo 提取 (n, e)。"""
    der = base64.b64decode(k1)
    _, spki, _ = _tlv(der, 0)                     # 外层 SEQUENCE
    _, alg, j = _tlv(spki, 0)                     # AlgorithmIdentifier（跳过）
    _, bits, _ = _tlv(spki, j)                    # BIT STRING
    pk = bits[1:]                                 # 去掉未用位数 0x00
    _, inner, _ = _tlv(pk, 0)                     # RSAPublicKey SEQUENCE
    _, n_b, j = _tlv(inner, 0)                    # modulus
    _, e_b, _ = _tlv(inner, j)                    # publicExponent
    n = int.from_bytes(n_b.lstrip(b"\x00"), "big")
    e = int.from_bytes(e_b.lstrip(b"\x00"), "big")
    return n, e, (n.bit_length() + 7) // 8


def rsa_public_encrypt_pkcs1(n, e, klen, data: bytes) -> bytes:
    """PKCS#1 v1.5 type-02 加密：EM = 00 02 PS(nonzero) 00 msg，C = EM^e mod n。"""
    if len(data) > klen - 11:
        raise ValueError("块超长")
    ps = bytes(random.randint(1, 255) for _ in range(klen - len(data) - 3))
    em = b"\x00\x02" + ps + b"\x00" + data
    c = pow(int.from_bytes(em, "big"), e, n)
    return c.to_bytes(klen, "big")


def rsa_public_decrypt_pkcs1(n, e, klen, data: bytes) -> bytes:
    """PKCS#1 v1.5 type-01 的"公钥运算"（等价 Node publicDecrypt）：
    用公钥模幂解开"私钥加密"的块，EM = 00 01 FF..FF 00 msg。"""
    c = int.from_bytes(data, "big")
    m = pow(c, e, n)
    em = m.to_bytes(klen, "big")
    sep = em.find(b"\x00", 2)                       # 00 01 FF..FF 00 MSG
    if em[0:2] != b"\x00\x01" or sep == -1:
        raise ValueError("type-01 填充不匹配")
    msg = em[sep + 1:]
    if not msg:
        raise ValueError("空报文")
    return msg


def rsa_encrypt_long(n, e, klen, text: str) -> bytes:
    """与前端 encryptLong 一致：>245 字符按 117 字符分块（PKCS#1 v1.5），块拼接。"""
    chunks = [text] if len(text) <= 245 else [text[i:i + 117] for i in range(0, len(text), 117)]
    return b"".join(rsa_public_encrypt_pkcs1(n, e, klen, c.encode("utf-8")) for c in chunks)


# ---------------------------------------------------------------- AES-CBC
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


def _xtime(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else (a << 1)


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def _key_schedule(key: bytes):
    """按 AES-128/192/256 展开轮密钥，返回 round_keys[r][16 存 State 列序]。"""
    nk = len(key) // 4
    nr = nk + 6
    words = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(words[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]                      # RotWord
            t = [_SBOX[x] for x in t]              # SubWord
            t[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[x] for x in t]
        words.append([a ^ b for a, b in zip(words[i - nk], t)])
    out = []
    col = []
    for w in words:
        col.append(w)
        if len(col) == 4:
            # 词序 w0..w3 各 4 字节；State 列 r0..r3 为每词同序字节
            out.append(bytes(col[0] + col[1] + col[2] + col[3]))
            col = []
    return out


def _encrypt_block(block: bytes, rks):
    """block 按流序：b[4c+r] 为第 c 列第 r 行。返回同样顺序的密文块。"""
    nr = len(rks) - 1
    s = [[block[4 * c + r] for c in range(4)] for r in range(4)]  # s[行][列]

    def addrk(rk):
        for r in range(4):
            for c in range(4):
                s[r][c] ^= rk[4 * c + r]

    addrk(rks[0])
    for rnd in range(1, nr + 1):
        for r in range(4):
            for c in range(4):
                s[r][c] = _SBOX[s[r][c]]                       # SubBytes
        s = [s[r][r:] + s[r][:r] for r in range(4)]            # ShiftRows
        if rnd != nr:                                          # MixColumns
            for c in range(4):
                a = [s[0][c], s[1][c], s[2][c], s[3][c]]
                s[0][c] = _mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3]
                s[1][c] = a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3]
                s[2][c] = a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3)
                s[3][c] = _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)
        addrk(rks[rnd])
    return bytes(s[r][c] for c in range(4) for r in range(4))


def aes_cbc_encrypt_pkcs7(plain: bytes, key: bytes, iv: bytes) -> bytes:
    rks = _key_schedule(key)
    padlen = 16 - len(plain) % 16
    plain += bytes([padlen]) * padlen
    prev = iv[:16]
    out = bytearray()
    for i in range(0, len(plain), 16):
        blk = bytes(a ^ b for a, b in zip(plain[i:i + 16], prev))
        cb = _encrypt_block(blk, rks)
        out += cb
        prev = cb
    return bytes(out)


# ---------------------------------------------------------------- 主流程
def http_json(url, body=None):
    req = urllib.request.Request(url, data=body, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def extract(url):
    keys = http_json(BASE + "/api/auth/keys")
    if keys.get("code") != 200:
        raise RuntimeError("获取公钥失败: " + json.dumps(keys, ensure_ascii=False))
    k1, k2 = keys["data"]["k1"], keys["data"]["k2"]
    n, e, klen = rsa_pubkey_from_spki_b64(k1)
    aes_key = rsa_public_decrypt_pkcs1(n, e, klen, base64.b64decode(k2)).decode("utf-8")
    iv = base64.b64decode(IV_B64)[:16]
    enc1 = base64.b64encode(aes_cbc_encrypt_pkcs7(
        json.dumps({"url": url}, separators=(",", ":")).encode("utf-8"),
        aes_key.encode("utf-8"), iv)).decode()
    body = base64.b64encode(rsa_encrypt_long(n, e, klen, enc1)).decode()
    return http_json(BASE + "/api/video/subtitleExtract", body.encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--bv", required=True)
    ap.add_argument("--parts", required=True)
    ap.add_argument("--delay", type=float, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for i, p in enumerate(a.parts.split(",")):
        p = p.strip()
        url = f"https://www.bilibili.com/video/{a.bv}/?p={p}"
        out = os.path.join(a.out, f"kedou_{int(p):02d}.json")
        try:
            j = extract(url)
            with open(out, "w", encoding="utf-8") as f:
                json.dump(j, f, ensure_ascii=False)
            items = ((j.get("data") or {}).get("subtitleItemVoList") or [])
            print(f"p{p}: ok code={j.get('code')} status={j.get('data', {}).get('status')} "
                  f"tracks={len(items)} -> {out}")
        except Exception as ex:                                # noqa: BLE001
            print(f"p{p}: ERR {ex}")
        if i != len(a.parts.split(",")) - 1:
            time.sleep(a.delay)


if __name__ == "__main__":
    main()
