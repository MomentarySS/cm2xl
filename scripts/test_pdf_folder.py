"""对指定文件夹的 PDF 做端到端提取测试。"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.cmm_filler.core.pdf_extract import detect_pdf_type
from modules.cmm_filler.core.filler import CMMReportFiller, TEMPLATE_PATH


def main():
    pdf_dir = Path(r'C:\Users\terence\Desktop\test')
    out_dir = pdf_dir / 'output'
    out_dir.mkdir(exist_ok=True)

    pdfs = sorted({p.resolve(): p for p in pdf_dir.glob('*.[pP][dD][fF]')}.values(), key=lambda p: p.name)
    print(f'找到 {len(pdfs)} 个 PDF')
    for p in pdfs:
        print(f'  {p.name}: 类型={detect_pdf_type(p)}')

    print('\n初始化 OCR 引擎...')
    t0 = time.time()
    filler = CMMReportFiller(str(TEMPLATE_PATH), dpi=300)
    print(f'引擎就绪 ({time.time() - t0:.1f}s)\n')

    results = []
    for p in pdfs:
        t1 = time.time()
        print(f'--- {p.name} ---')
        try:
            data = filler.extract_pdf_data(str(p))
            ms = data.get('measurements', [])
            low = sum(1 for m in ms if m.get('low_confidence'))
            ng = sum(1 for m in ms if m.get('ng'))
            part = data.get('part_name') or '(none)'
            date = data.get('date') or '(none)'
            print(f'  来源: {data.get("_source")}')
            print(f'  零件: {part}')
            print(f'  日期: {date}')
            print(f'  测量项: {len(ms)}, NG: {ng}, 低置信: {low}')
            for m in ms[:8]:
                flags = []
                if m.get('ng'):
                    flags.append('NG')
                if m.get('low_confidence'):
                    flags.append('LOW_CONF')
                flag = f' [{",".join(flags)}]' if flags else ''
                desc = (m.get('desc') or '')[:24]
                lbl = m.get('label') or f"FAI_{m['num']:02d}"
                print(f'    {lbl} {desc} nom={m["nominal"]} meas={m["measured"]}{flag}')
            if len(ms) > 8:
                print(f'    ... +{len(ms) - 8} more')
            results.append({
                'file': p.name, 'ok': True, 'count': len(ms), 'ng': ng,
                'low_conf': low, 'source': data.get('_source'),
                'part': part, 'date': date,
            })
        except Exception as e:
            print(f'  FAILED: {e}')
            results.append({'file': p.name, 'ok': False, 'error': str(e)})
        print(f'  elapsed: {time.time() - t1:.1f}s\n')

    print('=== NG export ===')
    summary = filler.export_ng_analysis(str(pdf_dir), str(out_dir))
    print(f'output: {summary.get("output_file")}')
    print(f'reports: {summary.get("processed_pdfs")}/{summary.get("total_pdfs")}')
    print(f'NG total: {summary.get("ng_count")}, FAI: {summary.get("fai_count")}')
    for r in summary.get('top_ng', []):
        lbl = r.get('label') or f"FAI_{r['num']:02d}"
        print(f'  {lbl}: NG {r["ng_count"]} ({r["ng_rate"]:.1%})')

    out_json = out_dir / 'extract_summary.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump({'pdfs': results, 'ng': {k: v for k, v in summary.items() if k != 'top_ng'}, 'top_ng': summary.get('top_ng')}, f, ensure_ascii=False, indent=2)
    print(f'\nJSON: {out_json}')


if __name__ == '__main__':
    main()
