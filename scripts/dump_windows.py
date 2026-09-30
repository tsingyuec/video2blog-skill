# 导出分栏文稿（MD 表格版）某区间窗口文本，输出形如 0555|文本（供改写后用 apply_windows 写回）
# 用法: python dump_windows.py transcripts/p08.md 1202 2600
import sys, re
path, lo, hi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
cur = None
for l in open(path, encoding='utf-8'):
    m = re.search(r'img/p\d+/(\d+)\.jpg', l)
    if m: cur = int(m.group(1))
    if l.startswith('| ') and cur is not None and '【跳转到' in l:
        text = l.split(' [【跳转到')[0][2:]
        if lo <= cur < hi: print(f'{cur:05d}|{text}')
        cur = None
