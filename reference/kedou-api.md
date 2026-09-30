# Kedou 字幕接口：原理与维护

> kedou.life 提供「粘贴 B 站链接 → 导出字幕」的在线服务，其网页端调用自有后端接口。本文件记录其请求加密方式，便于脚本长期可用以及故障排查。

## 接口

```
GET  https://www.kedou.life/api/auth/keys
POST https://www.kedou.life/api/video/subtitleExtract
```

请求头（POST 时）需包含：

```
content-type: application/json
kdsystem: Kedou
origin: https://www.kedou.life
referer: https://www.kedou.life/caption/subtitle/bilibili
```

body **不是明文 JSON**，而是加密后的字符串；直接 POST 明文会得到：

```json
{ "code": 530, "message": "数据处理异常", "data": null }
```

## 加密流程（逆向自其前端 `kedou.js`）

1. `GET /api/auth/keys` 返回 `{ data: { k1, k2 } }`：
   - `k1`：RSA 公钥（base64 的 DER/SPKI，2048 位）。
   - `k2`：用**私钥**加密过的 AES 密钥（base64）。
2. 用 `k1` 对 `k2` 做 **RSA 公钥解密**（即公钥运算）得到 AES 密钥字符串 `d`（实测 16 字符 → AES-128）。
   - 即"公钥运算"（decryptByPublicKey）：把密文视为整数做 m = c^e mod n，再按 PKCS#1 type-01 去填充（`00 01 FF..FF 00 <AES密钥>`）。Python 版在 `scripts/kedou_fetch.py` 的 `rsa_public_decrypt_pkcs1`。
3. 用 AES-CBC / Pkcs7 加密 body：
   - key = `d` 的 UTF-8 字节；
   - iv = base64 解码固定串 `a2Vkb3VAODk4OSE2MzIzMw==`（即 `kedou@8989!63233`）；
   - 明文 = `JSON.stringify({ url: "<视频地址>" })`；
   - 输出 base64 密文。
4. 用 `k1` 做 **RSA 长文本加密**：把上一步字符串按 **117 字符**分块，每块 PKCS#1 v1.5 加密（2048 位 → 每块 256 字节），把所有块字节拼接后 base64。
   - 注意：前端 `encryptLong` 在输入 ≤245 字符时只加密一整块；这里按 117 分块同样能被服务端解出（服务端按 256 字节切块解密）。
5. `POST /api/video/subtitleExtract`，body = 上一步的 base64 字符串。

成功返回：

```json
{
  "code": 200,
  "data": {
    "vid": "BV..._1",
    "status": "解析完成",
    "subtitleItemVoList": [
      { "lang": "中文", "langDesc": "中文", "content": "<SRT 文本>" }
    ]
  }
}
```

`content` 就是标准 SRT（时间戳形如 `0:0:0,1 --> 0:0:4,98`）。

## 限流

- 连续请求约 **10 次**后会返回 `code: 500, message: 请求过于频繁，请稍后再试`（连同 `code:530` 之外的普通错误）。
- 处理：**分批请求 + 每次间隔数秒**；被限流后**等待约 1–2 分钟**再继续，通常即可恢复。
- 脚本 `kedou_fetch.py` 已内置间隔（默认 6 秒，`--delay` 可调）与逐条容错。

## 排查清单

| 症状 | 可能原因 | 处理 |
| --- | --- | --- |
| `code:530 数据处理异常` | body 未加密 / 加密方式改变 | 核对本文件第 2–4 步；确认使用同一套 RSA+AES |
| `code:500 请求过于频繁` | 触发限流 | 等待 1–2 分钟后分批重试 |
| `code:200` 但 `subtitleItemVoList` 为空 | 该分 P 没有 AI 字幕 | 跳过或改用其他转写方式（本地 Whisper 等） |
| `auth/keys` 报错 | 站点改版 | 重新从前端 JS 提取加密逻辑（搜索 `useReqPublicKey` / `encryptLong`） |

## 免责声明

该接口属于第三方站点的服务，仅用于个人学习整理字幕；如站点政策或接口变化，以实际为准。
