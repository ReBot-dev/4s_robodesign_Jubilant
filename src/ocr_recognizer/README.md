# ocr_recognizer — OCR 認識

紙に印刷された**日本語の文字を読み取る**担当パッケージ。
最終的には ArUco 班が出す「正対補正した紙の画像」を入力にして、認識した文字列を他の班へ渡すことを目指す。

現在は `easyocr_test/` で、OCR ライブラリ **EasyOCR** が静止画で動くことを確認している段階。

## `easyocr_test/` の中身

| ファイル | 説明 |
|---|---|
| `ocrtest.py` | EasyOCR で画像から文字を読む実験スクリプト |
| `test_img.png` | テスト用の画像 |
| `requirements.txt` | 必要な Python パッケージ一覧（これで環境を再現する）|
| `.venv/` | Python 仮想環境（**git 管理外**。各自が自分で作る）|

## セットアップ（Python 仮想環境の作り方から）

「仮想環境(venv)」= この OCR 実験専用の、独立した Python パッケージの箱。
システムの Python を汚さずに、必要なものだけ入れられる。

```bash
cd src/ocr_recognizer/easyocr_test

# ① 箱を作る（最初の 1 回だけ）
python3 -m venv .venv

# ② 箱に入る（ターミナルを開くたびに毎回）
source .venv/bin/activate
#   → プロンプトの先頭に (.venv) が付けば成功

# ③ 必要なパッケージを箱の中に入れる
pip install --upgrade pip
pip install -r requirements.txt
```

`torch` などを含むので ③ は数分かかり、容量も大きい。
箱から出るときは `deactivate`。次回からは ① は不要で ② から始める。

## 実行

```bash
# .venv を有効化した状態で
python ocrtest.py
```

初回メモ:
- **最初の実行時に、日本語＋英語のモデルを自動ダウンロード**する（`~/.EasyOCR/` に保存）。
  ネット接続が必要で、少し時間がかかる（フリーズではない）。
- まずは確実に動く CPU で試すのがおすすめ。コードで `easyocr.Reader(['ja', 'en'], gpu=False)` とする。

## GPU について（あとで速くしたくなったら）

- 動作確認は `gpu=False`（CPU）で十分。静止画なら 1 枚数秒。
- C05 の **RTX 5070 は新しい世代**で、CUDA 12.6 以降に対応した新しい torch が必要（古いと `sm_120 not supported` で動かない）。
- 同じ C05 の **GTX 1660 Ti は枯れていて標準の torch で動く**ので、GPU で詰まったらこちらが確実。
- カードの選択は `CUDA_VISIBLE_DEVICES=0`（または `=1`）、確認は `nvidia-smi`。

## 注意：ROS 環境との干渉

`~/.bashrc` が毎回 ROS 2 を読み込む環境だと、ROS の Python パスが venv に漏れることがある。

- **`requirements.txt` を作り直すとき**は、ROS を読み込んでいないシェルで、または
  `env -u PYTHONPATH pip freeze > requirements.txt` とする。でないと ROS のパッケージが大量に混ざる。
- 実行時に **numpy 関連などの変なエラー**が出たら同じ原因。`env -u PYTHONPATH python ocrtest.py` で回避できる。

## これから

- 実際の事務書類（日本語・横書き）で精度を確認する。
- うまく読めないときの前処理（正対補正・二値化・文字の拡大）を足す。
- 固まってきたら ROS 2 パッケージ化（`ros2 pkg create`）して、画像トピックを購読 → 認識文字列を publish する。
