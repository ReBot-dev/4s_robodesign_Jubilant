"""OSS の OCR エンジンで、写真（raw）と正対補正画像（rect）を読み、結果を保存する。

使い方: <そのエンジンを入れた venv の python> run_oss.py <engine>
  engine = easyocr | paddleocr | tesseract | yomitoku | surya
出力: results/<engine>/{raw,rect}/<stem>.txt と results/<engine>/times.json（1 枚あたりの秒数、モデル読み込みは含まない）
各エンジンが標準で持つ向き補正は有効にしている（EasyOCR は raw のみ rotation_info を指定）。
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = {
    'raw': sorted((HERE.parent / 'test_docs' / 'photos').glob('*.jpg')),
    'rect': sorted((HERE / 'rectified').glob('*.png')),
    'd435': sorted((HERE / 'd435' / 'rectified').glob('*.png')),
}


def load(engine):
    if engine == 'easyocr':
        import easyocr
        reader = easyocr.Reader(['ja', 'en'], gpu=False)

        def run(path, cond):
            kw = {'rotation_info': [90, 180, 270]} if cond == 'raw' else {}
            return [t for _, t, _ in reader.readtext(str(path), **kw)]
        return run

    if engine == 'paddleocr':
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang='japan', enable_mkldnn=False)

        def run(path, cond):
            return [t for res in ocr.predict(str(path)) for t in res['rec_texts']]
        return run

    if engine == 'tesseract':
        def run(path, cond):
            out = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'jpn+eng', '--psm', '1'],
                                 capture_output=True, text=True, check=True).stdout
            return [l for l in out.splitlines() if l.strip()]
        return run

    if engine == 'yomitoku':
        import cv2
        from yomitoku import OCR
        ocr = OCR(device='cpu', visualize=False)

        def run(path, cond):
            results, _ = ocr(cv2.imread(str(path)))
            return [w.content for w in results.words]
        return run

    if engine == 'surya':
        def run(path, cond):
            with tempfile.TemporaryDirectory() as d:
                subprocess.run(['surya_ocr', str(path), '--output_dir', d],
                               capture_output=True, text=True, check=True)
                data = json.loads(next(Path(d).rglob('results.json')).read_text())
            return [line['text'] for pages in data.values() for page in pages for line in page['text_lines']]
        return run

    raise SystemExit(f'unknown engine: {engine}')


def main():
    engine = sys.argv[1]
    only = sys.argv[2:]  # 省略時は全部。例: raw/01_flat や d435（条件名）
    run = load(engine)
    out_dir = HERE / 'results' / engine
    times_path = out_dir / 'times.json'
    times = json.loads(times_path.read_text()) if times_path.exists() else {}
    for cond, paths in SETS.items():
        (out_dir / cond).mkdir(parents=True, exist_ok=True)
        for p in paths:
            key = f'{cond}/{p.stem}'
            if only and key not in only and cond not in only:
                continue
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
