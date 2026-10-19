# OCR 比較ベンチマーク

`test_docs/` の 5 種類のテスト文書を撮影した写真を、OSS の OCR と Claude の各モデルに読ませて、正解テキストで採点する。
結果のまとめは [`RESULTS.md`](RESULTS.md)。

## 画像の条件（3 通り）

| 条件 | フォルダ | 内容 |
|---|---|---|
| 写真のまま（raw） | `../test_docs/photos/` | スマホで撮った写真そのまま（4080×3072、横向き・逆さまもある） |
| 補正後（rect） | `rectified/` | 四隅の ArUco マーカーで正対補正した画像（`rectify.py`） |
| D435i 相当→補正（d435） | `d435/rectified/` | 写真を D435i のカラーカメラと同じ画素数（約 207 万画素）に縮小してから正対補正（`make_d435.py`） |

それぞれ 5 文書 × 2 枚（真上から `flat`／斜めから `angle`）＝ 10 枚。

## ファイル

| ファイル | 役割 |
|---|---|
| `rectify.py` | ArUco で正対補正する |
| `make_d435.py` | D435i 相当に縮小してから正対補正する |
| `run_oss.py` | OSS の OCR（EasyOCR / PaddleOCR / Tesseract / YomiToku / Surya）で読む |
| `score.py` | 正解と比べて採点する（`results/scores.csv` と表を出力） |
| `results/<エンジン>/<条件>/<画像名>.txt` | 読み取り結果 |
| `results/<エンジン>/times.json` | 1 枚あたりの処理時間（秒） |

## 使い方

```bash
python rectify.py && python make_d435.py         # 要 opencv（cv2.aruco）
<エンジンを入れた venv>/bin/python run_oss.py paddleocr   # エンジンごとに実行
python score.py                                  # 要 rapidfuzz
```

ROS の Python パスが混ざらないように、`env -u PYTHONPATH` を付けて実行するのが安全。

## Claude の読み取り方法

Claude Code のサブエージェントを、モデル（Haiku / Sonnet / Opus / Fable）ごとに起動して読ませた。
- 使ってよいツールは「画像を見る（Read）」と「結果を書く（Write）」だけ。正解ファイルは開いていないことを、実行ログで確認済み。
- **1 つのエージェントには、同じ文書の画像を 1 枚しか見せない**（条件 × 撮り方ごとに 5 文書ずつ）。
  同じ文書を続けて見せると、2 枚目以降は前の読み取りを写すだけになり、正しく比較できなかったため（1 回目の実行で判明）。
- 処理時間は「エージェント全体の所要時間 ÷ 5 枚」。API を直接呼ぶ場合とは異なる目安。
- Claude Code は大きい画像を縮小してからモデルに渡すため、API で解像度を指定する場合とは結果が変わりうる。
