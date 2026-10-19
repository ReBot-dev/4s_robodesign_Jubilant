"""results/ の読み取り結果を test_docs/*.txt の正解と比べて採点する。

使い方: python score.py   （要 rapidfuzz）
出力: results/scores.csv（1 枚ごと）と、標準出力に エンジン×条件 の平均表（Markdown）

指標（すべて正規化した文字列で比較）
- 行の再現率    : 正解の各行が、読み取り結果のどこかに 80% 以上の類似度で見つかった割合
- 完全一致行    : 正解の各行が、読み取り結果に一字一句そのまま含まれていた割合
- 数字・記号    : 数字や ¥ % μ ± ° ≦ × ℃ を含む語（金額・日付・型番・単位など）が、そのまま含まれていた割合
- 文字誤り率CER : 全文の編集距離 ÷ 正解の文字数（読む順番が違っても誤りとして数える）
- 元に無い行    : 読み取り結果の行のうち、正解のどこにも似ていない行の数（でっち上げ・ゴミ）
正規化: NFKC、空白と表の区切り「|」を除去、ダッシュ類→「-」、波ダッシュ類→「~」
"""
import csv
import json
import re
import statistics
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

HERE = Path(__file__).resolve().parent
GT_DIR = HERE.parent / 'test_docs'
RESULTS = HERE / 'results'

DASHES = dict.fromkeys(map(ord, '‐‑‒–—―−－'), '-')
WAVES = dict.fromkeys(map(ord, '〜～'), '~')
KEY_TOKEN = re.compile(r'[0-9A-Za-z¥%μ±°≦×@/:.,\-~]+')
KEY_MARK = re.compile(r'[0-9¥%μ±°≦×]')


def norm(s):
    s = unicodedata.normalize('NFKC', s).translate(DASHES).translate(WAVES)
    return re.sub(r'[\s|]', '', s)


def score(gt_text, ocr_text):
    gt_lines = [norm(l) for l in gt_text.splitlines() if len(norm(l)) >= 2]
    ocr_lines = [norm(l) for l in ocr_text.splitlines() if norm(l)]
    gt_all, ocr_all = ''.join(gt_lines), ''.join(ocr_lines)
    found = sum(fuzz.partial_ratio(g, ocr_all) >= 80 for g in gt_lines) if ocr_all else 0
    exact = sum(g in ocr_all for g in gt_lines)
    keys = [t for t in KEY_TOKEN.findall(gt_all) if KEY_MARK.search(t) and len(t) >= 2]
    key_ok = sum(t in ocr_all for t in keys)
    extra = sum(len(o) >= 3 and fuzz.partial_ratio(o, gt_all) < 60 for o in ocr_lines)
    return {
        'recall': found / len(gt_lines),
        'exact': exact / len(gt_lines),
        'keys': key_ok / len(keys) if keys else 1.0,
        'cer': Levenshtein.distance(gt_all, ocr_all) / len(gt_all),
        'extra': extra,
    }


COND_LABEL = {'rect': '補正後', 'd435': 'D435i相当→補正', 'raw': '写真のまま'}


def main():
    rows = []
    for engine_dir in sorted(p for p in RESULTS.iterdir() if p.is_dir()):
        times_path = engine_dir / 'times.json'
        times = json.loads(times_path.read_text()) if times_path.exists() else {}
        for cond in ('rect', 'd435', 'raw'):
            for f in sorted((engine_dir / cond).glob('*.txt')):
                doc = f.stem.split('_')[0]
                gt = next(GT_DIR.glob(f'{doc}_*.txt')).read_text(encoding='utf-8')
                s = score(gt, f.read_text(encoding='utf-8'))
                rows.append({'engine': engine_dir.name, 'cond': cond, 'image': f.stem, **s,
                             'sec': times.get(f'{cond}/{f.stem}')})
    with open(RESULTS / 'scores.csv', 'w', newline='', encoding='utf-8') as fp:
        w = csv.DictWriter(fp, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    print('| エンジン | 画像 | 行の再現率 | 完全一致行 | 数字・記号 | 文字誤り率 | 元に無い行(計) | 秒/枚 |')
    print('|---|---|---|---|---|---|---|---|')
    groups = {}
    for r in rows:
        groups.setdefault((r['engine'], r['cond']), []).append(r)
    COND_ORDER = {'rect': 0, 'd435': 1, 'raw': 2}
    order = sorted(groups, key=lambda k: (COND_ORDER[k[1]], -statistics.mean(r['recall'] for r in groups[k])))
    for engine, cond in order:
        g = groups[(engine, cond)]
        m = lambda k: statistics.mean(r[k] for r in g)
        secs = [r['sec'] for r in g if r['sec'] is not None]
        print(f"| {engine} | {COND_LABEL[cond]} | {m('recall'):.0%} | {m('exact'):.0%} | "
              f"{m('keys'):.0%} | {m('cer'):.1%} | {sum(r['extra'] for r in g)} | "
              f"{statistics.mean(secs):.1f} |" if secs else '— |')


if __name__ == '__main__':
    main()
