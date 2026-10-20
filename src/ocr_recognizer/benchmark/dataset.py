"""どのテスト文書セットを使うか（環境変数 OCR_DATASET = ja | en、既定は ja）と、そのパス。

ja: test_docs/ の日本語版。結果は benchmark/ 直下
en: test_docs/en/ の英語版。結果は benchmark/en/ 以下
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = os.environ.get('OCR_DATASET', 'ja')
if NAME not in ('ja', 'en'):
    raise SystemExit(f'OCR_DATASET は ja か en: {NAME}')

_DOCS = HERE.parent / 'test_docs'
GT_DIR = _DOCS / 'en' if NAME == 'en' else _DOCS
PHOTOS = GT_DIR / 'photos'
ROOT = HERE / 'en' if NAME == 'en' else HERE
RECTIFIED = ROOT / 'rectified'
D435 = ROOT / 'd435'
RESULTS = ROOT / 'results'
