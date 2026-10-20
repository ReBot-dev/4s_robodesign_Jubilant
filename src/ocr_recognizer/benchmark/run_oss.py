"""OSS の OCR エンジンで、写真（raw）と正対補正画像（rect）を読み、結果を保存する。

使い方: <そのエンジンを入れた venv の python> run_oss.py <engine>
  engine = easyocr | paddleocr | tesseract | yomitoku | surya
出力: results/<engine>/{raw,rect}/<stem>.txt と results/<engine>/times.json（1 枚あたりの秒数、モデル読み込みは含まない）
各エンジンが標準で持つ向き補正は有効にしている（EasyOCR は raw のみ rotation_info を指定）。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import dataset

HERE = dataset.HERE
EN = dataset.NAME == 'en'
SETS = {
    'raw': sorted(dataset.PHOTOS.glob('*.jpg')),
    'rect': sorted(dataset.RECTIFIED.glob('*.png')),
    'd435': sorted((dataset.D435 / 'rectified').glob('*.png')),
}


def load(engine):
    if engine == 'easyocr':
        import easyocr
        reader = easyocr.Reader(['en'] if EN else ['ja', 'en'], gpu=False)

        def run(path, cond):
            kw = {'rotation_info': [90, 180, 270]} if cond == 'raw' else {}
            return [t for _, t, _ in reader.readtext(str(path), **kw)]
        return run

    if engine == 'paddleocr':
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang='en' if EN else 'japan', enable_mkldnn=False)

        def run(path, cond):
            return [t for res in ocr.predict(str(path)) for t in res['rec_texts']]
        return run

    if engine == 'tesseract':
        def run(path, cond):
            out = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng' if EN else 'jpn+eng', '--psm', '1'],
                                 capture_output=True, text=True, check=True).stdout
            return [l for l in out.splitlines() if l.strip()]
        return run

    if engine == 'yomitoku':
        # OCR クラスは読み順に並べないので、レイアウト解析と読み順推定を行う DocumentAnalyzer を使う
        import cv2
        from yomitoku import DocumentAnalyzer
        analyzer = DocumentAnalyzer(device='cpu', visualize=False)

        def run(path, cond):
            results, _, _ = analyzer(cv2.imread(str(path)))
            blocks = [(p.order, (p.contents or '').splitlines()) for p in results.paragraphs]
            for t in results.tables:
                rows = {}
                for c in sorted(t.cells, key=lambda c: (c.row, c.col)):
                    rows.setdefault(c.row, []).append((c.contents or '').replace('\n', ''))
                blocks.append((t.order, [' | '.join(r) for _, r in sorted(rows.items())]))
            return [l for _, ls in sorted(blocks, key=lambda b: b[0] if b[0] is not None else 1e9) for l in ls]
        return run

    if engine == 'surya':
        # surya-ocr 0.22 はページを VLM で読み、ブロックごとの HTML を返す。
        # llama.cpp の llama-server が必要（環境変数 LLAMA_CPP_BINARY で場所を渡す）。
        import html
        import re

        def html_lines(h):
            h = re.sub(r'</t[dh]>', ' | ', h)
            h = re.sub(r'<br\s*/?>|</(p|li|tr|h[1-6]|div)>', '\n', h)
            text = html.unescape(re.sub(r'<[^>]+>', '', h))
            return [l.strip().rstrip('|').strip() for l in text.splitlines() if l.strip()]

        def run(path, cond):
            with tempfile.TemporaryDirectory() as d:
                subprocess.run(['surya_ocr', str(path), '--output_dir', d],
                               capture_output=True, text=True, check=True)
                data = json.loads(next(Path(d).rglob('results.json')).read_text())
            blocks = [b for pages in data.values() for page in pages for b in page['blocks'] if not b['skipped']]
            blocks.sort(key=lambda b: b['reading_order'] if b['reading_order'] is not None else 1e9)
            return [l for b in blocks for l in html_lines(b['html'] or '')]
        return run

    raise SystemExit(f'unknown engine: {engine}')


def main():
    engine = sys.argv[1]
    only = sys.argv[2:]  # 省略時は全部。例: raw/01_flat や d435（条件名）
    run = load(engine)
    out_dir = dataset.RESULTS / engine
    times_path = out_dir / 'times.json'
    times = json.loads(times_path.read_text()) if times_path.exists() else {}
    for cond, paths in SETS.items():
        (out_dir / cond).mkdir(parents=True, exist_ok=True)
        for p in paths:
            key = f'{cond}/{p.stem}'
            if only and key not in only and cond not in only:
                continue
            out_txt = out_dir / cond / f'{p.stem}.txt'
            if key in times and out_txt.exists() and out_txt.stat().st_size > 1 and not os.environ.get('OCR_FORCE'):
                continue  # 済み（やり直すときは OCR_FORCE=1）
            t0 = time.perf_counter()
            try:
                lines = run(p, cond)
            except Exception as e:  # 1 枚の失敗で全体を止めない
                lines = []
                print(f'  {key}: ERROR {e!r}', flush=True)
            dt = time.perf_counter() - t0
            (out_dir / cond / f'{p.stem}.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            times[key] = round(dt, 2)
            times_path.write_text(json.dumps(times, indent=1, ensure_ascii=False))
            print(f'{engine} {key}: {len(lines)} 行, {dt:.1f} s', flush=True)


if __name__ == '__main__':
    main()
