"""Gemini（API）で写真（raw）・正対補正画像（rect）・D435i 相当（d435）を読み、結果を保存する。

使い方: OCR_DATASET=en <google-genai を入れた venv の python> run_gemini.py <モデル名>
  例: run_gemini.py gemini-3.8-flash
API キーは環境変数 GEMINI_API_KEY か ~/.config/gemini/api_key から読む。
出力: results/gemini-<モデル名>/{raw,rect,d435}/<stem>.txt と times.json（1 枚あたりの API 応答時間）
指示文は Claude のエージェントに渡したものと同じ。1 枚ずつ独立に呼ぶので、前の画像の影響は受けない。
無料枠の回数制限（429）に当たったら待って再試行し、済んだ画像は飛ばす。
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

import dataset

PROMPT = """You are one contestant in an OCR benchmark. Transcribe this image of a printed document exactly as printed, using only your own vision.

Format:
- Copy characters exactly as printed; do not correct, normalize, translate, summarize or add anything. Keep symbols as seen ($ % – — “ ” • ± μ ° ≤ × − ¥ 〒 etc.).
- One printed line per output line, natural reading order (top to bottom; in a two-column area, whole left column first, then right column).
- Tables: one row per line, cells separated by " | ".
- Ignore the four black-and-white square markers in the corners.
- Unreadable character → 〓. Never invent text you cannot see.
- Output only the transcription (no commentary, no code fences)."""

SETS = {
    'raw': sorted(dataset.PHOTOS.glob('*.jpg')),
    'rect': sorted(dataset.RECTIFIED.glob('*.png')),
    'd435': sorted((dataset.D435 / 'rectified').glob('*.png')),
}


def api_key():
    key = os.environ.get('GEMINI_API_KEY')
    return key or Path('~/.config/gemini/api_key').expanduser().read_text().strip()


def main():
    model = sys.argv[1]
    client = genai.Client(api_key=api_key())
    out_dir = dataset.RESULTS / f'gemini-{model.removeprefix("gemini-")}'
    times_path = out_dir / 'times.json'
    times = json.loads(times_path.read_text()) if times_path.exists() else {}
    for cond, paths in SETS.items():
        (out_dir / cond).mkdir(parents=True, exist_ok=True)
        for p in paths:
            key = f'{cond}/{p.stem}'
            out_txt = out_dir / cond / f'{p.stem}.txt'
            if key in times and out_txt.exists() and out_txt.stat().st_size > 1:
                continue
            image = types.Part.from_bytes(data=p.read_bytes(),
                                          mime_type='image/jpeg' if p.suffix == '.jpg' else 'image/png')
            for attempt in range(12):
                t0 = time.perf_counter()
                try:
                    r = client.models.generate_content(model=model, contents=[image, PROMPT])
                    break
                except Exception as e:
                    msg = str(e)
                    busy = '503' in msg or 'UNAVAILABLE' in msg  # 無料枠の混雑
                    if not (busy or '429' in msg) or attempt == 11:
                        raise
                    m = re.search(r"retry in ([\d.]+)s|'retryDelay': '(\d+)s'", msg)
                    if m:
                        wait = float(next(g for g in m.groups() if g)) + 2
                    else:
                        wait = min(30 * 2 ** attempt, 600)
                    print(f'  {key}: {"混雑" if busy else "回数制限"}、{wait:.0f} 秒待つ', flush=True)
                    time.sleep(wait)
            dt = time.perf_counter() - t0
            text = (r.text or '').strip()
            text = re.sub(r'^```\w*\n|\n```$', '', text)  # 念のためコードブロックの囲みを外す
            out_txt.write_text(text + '\n', encoding='utf-8')
            times[key] = round(dt, 2)
            times_path.write_text(json.dumps(times, indent=1, ensure_ascii=False))
            print(f'{model} {key}: {len(text.splitlines())} 行, {dt:.1f} s', flush=True)


if __name__ == '__main__':
    main()
