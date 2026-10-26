# ocr_recognizer — OCR 認識

紙に印刷された**海外の文書（英語）を読み取る**担当パッケージ。
ArUco 班が出す「正対補正した紙の画像」を入力にして、読み取った文字列を次の工程（LLM での日本語への翻訳）へ渡す。

最終的な流れ（予定）:

```
カメラ（D435i）→ ArUco で紙を正対補正 → OCR（このパッケージ）→ LLM で翻訳・要約 → 音声でスピーカー出力
```

## いまの状況

- **OCR エンジンの比較は完了。** 結果は下の「これまでの結果」と [`benchmark/RESULTS.md`](benchmark/RESULTS.md)。
- **LLM（Claude）での翻訳・読み上げ文の生成は動作確認済み**（[`../ocr_ai/`](../ocr_ai/)）。
- 次は音声出力（VOICEVOX）。

## これまでの結果

### 1. OCR エンジンの比較

英語のテスト文書 5 種類（お知らせ・請求書・時間割・チラシ・データシート）を印刷して撮影し、
OSS の OCR 5 種類と Claude 4 モデルに読ませて、正解テキストで採点した。
下の表は、本番に一番近い条件（**D435i 相当の画質 → ArUco で正対補正**）の結果。

| エンジン | 行の再現率 | 数字・記号 | 文字誤り率 | 1 枚あたり |
|---|---|---|---|---|
| Claude Opus | 100% | 100% | 0.0% | 6.5 秒 |
| Claude Haiku | 100% | 100% | 0.1% | 5.9 秒 |
| Claude Sonnet | 100% | 100% | 0.5% | 5.9 秒 |
| Claude Fable | 100% | 100% | 0.9% | 11.4 秒 |
| Gemini 3.8 Flash | 100% | 100% | 0.1% | 255 秒（無料枠・混雑） |
| Gemini 3.5 Flash-Lite | 100% | 100% | 0.6% | 5.1 秒 |
| Surya | 100% | 100% | 1.1% | 306 秒（CPU） |
| YomiToku | 100% | 100% | 7.1% | 25 秒 |
| EasyOCR | 96% | 70% | 15.1% | 19 秒 |
| PaddleOCR | 92% | 99% | 16.9% | 55 秒 |
| Tesseract | 71% | 65% | 33.9% | 1.4 秒 |

- **精度は Claude が一番。** 文字の読み間違いはほぼゼロで、残った誤りは左右に並んだ欄を読む順番だけ。Haiku で十分。
- **無料で使うなら Gemini 3.5 Flash-Lite**（無料枠は 1 日 500 回。3.8 Flash は 1 日 20 回までで遅い）。
- **ネットなしで動かすなら YomiToku**（読み順を推定する `DocumentAnalyzer` を使うこと）。
- **ArUco での正対補正は必須。** 写真のままだと OSS は大きく崩れる。補正すれば D435i 程度の画質でも精度はほとんど落ちない。
- 日本語の文書でも同じ傾向だった。条件ごとの数字、指標の意味、注意点は [`benchmark/RESULTS.md`](benchmark/RESULTS.md)。

### 2. LLM での翻訳・読み上げ文の生成（`../ocr_ai/`）

OCR の結果（英語）を Claude に渡し、日本語の読み上げ文に変換する。
1 回の呼び出しで、次の 3 つを決まった形（構造化出力）で受け取る。

| 欄 | 中身 |
|---|---|
| `summary` | 要点の読み上げ文（30 秒程度。誰から誰への何の文書か → 日時・金額・期限などを先に） |
| `full` | 全文の読み上げ文（表は行ごとの文章に組み直す） |
| `unclear` | OCR の崩れで判断できなかった箇所（推測で埋めずにここへ書く） |

読み上げ向けに、日付は「2026 年 10 月 19 日」、金額は「243 ドル 80 セント」、固有名詞はカタカナ、型番は区切って読める形にするようプロンプトで指示している。

**結果（請求書）**：正解テキストを入力にすると、品番・数量・単価・金額・税・合計・口座番号まですべて正しく、読み上げ向けの日本語になった。

**でっち上げ対策のテスト**：OCR の失敗に見立てて請求書を 5 か所崩した入力（[`../ocr_ai/test_inputs/`](../ocr_ai/test_inputs/)）でも、**5 か所すべて合格**。

| 崩した箇所 | Claude の動き |
|---|---|
| 明らかな誤読（`Aluminurn`・`Sa1es`） | 正しく直して訳した |
| 合計金額の 1 桁が欠け（計算すれば分かる） | 「読み取れないが、内訳を足すと 243 ドル 80 セント」と、計算した値だと分かる言い方にし、`unclear` にも記載 |
| 単価が空欄（計算すれば分かる） | 計算で埋めず「単価の欄は空欄」と伝え、`unclear` にも記載 |
| 支払期限の月が欠け（決められない） | 月を推測せず「月の部分が読み取れない、原本で確認を」と伝え、`unclear` にも記載 |

読めた値と計算した値を言い分け、決められない所は推測しない。読み上げを聞く人は原文を見られないので、ここが一番大事な性質。

## フォルダ構成

| フォルダ | 中身 |
|---|---|
| `easyocr_test/` | EasyOCR の実験（`ocrtest.py`、`requirements.txt`） |
| `paddleocr_test/` | PaddleOCR の実験（`test.py`、`requirements.txt`） |
| `test_docs/` | テスト文書と撮影写真（[`test_docs/README.md`](test_docs/README.md)） |
| `benchmark/` | 比較ベンチマーク（[`benchmark/README.md`](benchmark/README.md)） |

`.venv/`（Python 仮想環境）はどのフォルダでも **git 管理外**。各自が自分の PC で作る。

## セットアップ（Python 仮想環境の作り方から）

「仮想環境(venv)」= その実験専用の、独立した Python パッケージの箱。
システムの Python を汚さずに、必要なものだけ入れられる。EasyOCR と PaddleOCR は依存パッケージがぶつかりやすいので、**箱は実験フォルダごとに分ける**。

```bash
cd src/ocr_recognizer/paddleocr_test     # または easyocr_test

# ① 箱を作る（最初の 1 回だけ）
python3 -m venv .venv

# ② 箱に入る（ターミナルを開くたびに毎回）
source .venv/bin/activate
#   → プロンプトの先頭に (.venv) が付けば成功。`which pip` が .venv の中を指していれば OK

# ③ 必要なパッケージを箱の中に入れる
pip install --upgrade pip
pip install -r requirements.txt
```

③ は数分かかり、容量も大きい（PyTorch や PaddlePaddle を含むため）。
箱から出るときは `deactivate`。次回からは ① は不要で ② から始める。

## 実行

どちらも、箱（.venv）に入った状態で実行する。

```bash
cd easyocr_test   && python ocrtest.py     # EasyOCR
cd paddleocr_test && python test.py        # PaddleOCR
```

- **初回は、日本語のモデルを自動でダウンロードする**（EasyOCR は `~/.EasyOCR/`、PaddleOCR は `~/.paddlex/` に保存）。
  ネット接続が必要で、少し時間がかかる（フリーズではない）。
- **PaddleOCR を CPU で動かすときは `enable_mkldnn=False` が必須**。
  付けないと `NotImplementedError: ... ConvertPirAttribute2RuntimeAttribute not support` で止まる
  （CPU 向け高速化ライブラリ oneDNN が、新しいモデル PP-OCRv6 に未対応のため）。
  ```python
  ocr = PaddleOCR(lang='japan', enable_mkldnn=False)
  result = ocr.predict('test_img.png')   # PaddleOCR 3.x は predict()。2.x は ocr.ocr()
  ```
- EasyOCR も、まずは確実に動く CPU で試す：`easyocr.Reader(['ja', 'en'], gpu=False)`

## ハマりどころ

- **venv はフォルダを移動すると壊れる。**
  作ったときの場所が中に書き込まれているため、移動後は `(.venv)` が表示されていても実際にはシステムの pip が動き、
  `error: externally-managed-environment` で止まる。移動したら `rm -rf .venv` して作り直す。
- **ROS の Python パスが venv に混ざる。**
  `~/.bashrc` で ROS 2 を読み込んでいると起きる。
  - `requirements.txt` を作り直すときは `env -u PYTHONPATH pip freeze > requirements.txt`（でないと ROS のパッケージが大量に混ざる）
  - 実行時に numpy 関連などの変なエラーが出たら `env -u PYTHONPATH python test.py`

## GPU について（あとで速くしたくなったら）

- 静止画の動作確認は CPU で十分。
  ただし PaddleOCR は CPU だと、スマホ写真（約 1200 万画素）で 1 枚 90 秒前後、D435i 相当の画像でも 40〜50 秒かかる。
- カードの選択は `CUDA_VISIBLE_DEVICES=0`（または `=1`）、確認は `nvidia-smi`。

## これから

- 読み取りは Claude（Haiku）を本命、ネットなしの代わりに YomiToku、という方向で決める。
- 音声出力（VOICEVOX）をつなぎ、「文字列 → Claude → 音声」を通す。
- ArUco 班と、受け渡しの形（正対補正済みの画像を渡すか、生画像と 4 隅の座標を渡すか）とトピック名を決める。
- ROS 2 パッケージ化（`ros2 pkg create`）して、画像トピックを購読 → 読み取った文字列を publish する。
