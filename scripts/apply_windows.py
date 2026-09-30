# 把改写后的 NNNNN|文本 写回分栏文稿（MD 表格版）
# 用法: python apply_windows.py transcripts/p08.md << 'RAPPLY'
# 01202|改写后的文本……
# RAPPLY
import sys, re
path = sys.argv[1]
mapping = {}
for line in sys.stdin.read().split('\n'):
    if '|' in line:
        k, v = line.split('|', 1); mapping[k.strip()] = v
lines = open(path, encoding='utf-8').read().split('\n')
cur, n = None, 0
for i, l in enumerate(lines):
    m = re.search(r'img/p\d+/(\d+)\.jpg', l)
    if m: cur = f'{int(m.group(1)):05d}'
    if l.startswith('| ') and '【跳转到' in l and cur is not None:
        k = cur
        if k in mapping:
            newtext = mapping[k].replace('|', '\|')
            link_m = re.search(r' ?\[【跳转到[^\]]*\]\([^)]*\)', lines[i])
            link = link_m.group(0) if link_m else ''
            img_m = re.search(r'\| <img [^>]+> \|$', lines[i])
            lines[i] = f'| {newtext}{link} {img_m.group(0)[1:] if img_m else ""}'.rstrip()
            n += 1
        cur = None
open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
print('applied', n, 'of', len(mapping))
