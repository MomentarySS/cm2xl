import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.cmm_filler.core.filler import CMMReportFiller, TEMPLATE_PATH, ITEM_PREFIXES

p = Path(r'C:\Users\terence\Desktop\test\WF-2026-08-27-002.PDF')
f = CMMReportFiller(str(TEMPLATE_PATH))
f.cache.clear()
data = f.extract_pdf_data(str(p))

c = Counter(m.get('item_key', str(m['num'])) for m in data['measurements'])
dups = sorted(k for k, v in c.items() if v > 1)
print(f'total={len(data["measurements"])} unique_keys={len(c)} dup_keys={dups}')
print('\n--- sub-numbered items ---')
for m in data['measurements']:
    if m.get('sub'):
        print(f"  {m.get('label')} | {m['desc'][:40]} | nom={m['nominal']} meas={m['measured']}")

# scan raw OCR for FAI patterns with sub-numbers
prefix = '|'.join(re.escape(x) for x in ITEM_PREFIXES)
pat = re.compile(rf'(?:{prefix})[_\s]*(\d+)-(\d+)', re.I)
imgs = f.pdf_to_all_images(str(p))
seen = []
for img in imgs:
    for line in f.ocr_image(img):
        if pat.search(line):
            seen.append(line.strip())
print(f'\n--- OCR lines with FAI_N-M pattern ({len(seen)}) ---')
for line in seen[:15]:
    print(' ', line[:80])
if len(seen) > 15:
    print(f'  ... +{len(seen)-15}')
