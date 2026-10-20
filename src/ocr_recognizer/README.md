# ocr_recognizer — OCR 認識

紙に印刷された**日本語の文字を読み取る**担当パッケージ。
ArUco 班が出す「正対補正した紙の画像」を入力にして、読み取った文字列を次の工程へ渡す。

最終的な流れ（予定）:

```
カメラ（D435i）→ ArUco で紙を正対補正 → OCR（このパッケージ）→ LLM で翻訳・要約 → 音声でスピーカー出力
```

## いまの状況

OCR エンジンを比べている段階。

- `easyocr_test/`・`paddleocr_test/`：EasyOCR と PaddleOCR を静止画で動かす実験
- `test_docs/`：比較用に作ったテスト文書 5 種類（PDF と正解テキスト）と、その撮影写真
- `benchmark/`：同じ写真を OSS の OCR 5 種類と Claude 4 モデルに読ませて採点する比較
  → 結果は [`benchmark/RESULTS.md`](benchmark/RESULTS.md)（英語・日本語とも。Claude がほぼ完璧、OSS では YomiToku が最良。ArUco での正対補正は必須）

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

- 比較結果（[`benchmark/RESULTS.md`](benchmark/RESULTS.md)）を見て、使うエンジンを決める。
- ArUco 班と、受け渡しの形（正対補正済みの画像を渡すか、生画像と 4 隅の座標を渡すか）とトピック名を決める。
- ROS 2 パッケージ化（`ros2 pkg create`）して、画像トピックを購読 → 読み取った文字列を publish する。
