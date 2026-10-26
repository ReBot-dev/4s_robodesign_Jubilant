# ocr_ai — Claude で日本語の読み上げ文にする

OCR で読み取った英語の文書を Claude に渡し、**日本語の読み上げ文**に変換する。
1 回の呼び出しで、次の 4 つを決まった形（構造化出力）で受け取る。

| 欄 | 中身 |
|---|---|
| `doc_type` | 文書の種類（請求書、お知らせ など） |
| `summary` | 要点の読み上げ文（30 秒程度） |
| `full` | 全文の読み上げ文（表は行ごとの文章に組み直す） |
| `unclear` | OCR の崩れで判断できなかった箇所のリスト（推測で埋めずにここへ書く） |

結果と評価は [`../ocr_recognizer/README.md`](../ocr_recognizer/README.md) の「LLM での翻訳・読み上げ文の生成」。

## ファイル

| ファイル | 中身 |
|---|---|
| `system_prompt.txt` | Claude への指示（読み上げ向けの書き方、推測しないこと など）。Python 版と Rust 版で共用 |
| `2test.py` | Python 版。`client.messages.parse()` で `Reading` 型として受け取る |
| `test.py` | 最初の試作（構造化出力なし、普通の文章で受け取る） |
| `test_inputs/` | OCR の失敗に見立てて 5 か所崩した請求書と、その答え合わせ |
| `claude_rs/` | Rust 版（下の「Rust 版」） |

## API キーの準備

Claude API のキー（`sk-ant-...`）が必要。**コードやファイルに書かず、コミットもしない。**
実行する端末で、毎回次を打つ（貼り付けても画面に出ず、履歴にも残らない）。

```bash
read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY
```

`export` はその端末の中だけで有効。別の端末で動かすときは打ち直す。

## Python 版

```bash
cd src/ocr_ai
python3 -m venv .venv                # 最初の 1 回だけ
source .venv/bin/activate
pip install anthropic pydantic
python 2test.py
```

`2test.py` は `test_inputs/02_invoice_broken.txt` を読み、`summary`・`full`・`unclear` を表示する。

## Rust 版（`claude_rs/`）

Claude には Rust 用の公式ライブラリがないので、`reqwest` で API に直接 HTTP リクエストを送っている。

- 送り先: `POST https://api.anthropic.com/v1/messages`
- ヘッダー: `x-api-key`（キー）、`anthropic-version: 2026-10-21`
- 本文に `output_config.format`（JSON Schema）を入れて、返事を `Reading` の形に固定する
- 返ってきた JSON を `serde_json::from_str` で構造体 `Reading` に変換する

```bash
cd src/ocr_ai/claude_rs
cargo run
```

- `cargo run` は `claude_rs/` で実行する（`../system_prompt.txt` などを相対パスで読むため）
- VOICEVOX のアプリを起動しておく（音声を作るところまで動く。[`../ocr_voicevox/README.md`](../ocr_voicevox/README.md)）
- 結果の音声は `test.wav`（git 管理外）

**いまの状態**: Claude から `Reading` を受け取るところまでは完成。VOICEVOX に渡す文字はまだ固定の「こんにちは」なので、次は `reading.summary` を渡す。

## ハマりどころ

- `Error: NotPresent` → その端末で `ANTHROPIC_API_KEY` を設定していない
- `Error: Os { code: 2, kind: NotFound ... }` → 読もうとしたファイルのパスが違う（`cargo run` した場所が基準）
- `json!` の中の `no rules expected ...` → 指された行の **1 つ前の行末のカンマ**が抜けている
- reqwest の blocking は何も指定しないと 30 秒で打ち切る。Claude は考える時間があるので、タイムアウトを延ばしてある（300 秒）
