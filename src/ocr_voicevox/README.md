# ocr_voicevox — VOICEVOX で音声を作る

日本語の読み上げ文を、[VOICEVOX](https://voicevox.hiroshiba.jp/) で音声（wav）にする実験。
VOICEVOX はネットなしで動き、無料で使える。

## 準備

1. VOICEVOX のアプリを入れて起動する（0.26.0 で確認）
2. **アプリを開いている間だけ**、音声合成のサーバー（ENGINE）が `http://localhost:50021` で動く。
   アプリを閉じると `Connection refused` になる

## 仕組み（2 回の HTTP リクエスト）

1. `POST /audio_query?text=...&speaker=3` … 文章から「読み方のデータ」（アクセント・長さなど）を作ってもらう
2. `POST /synthesis?speaker=3`（本文に 1. の結果）… 音声（wav）を作ってもらう

## ファイル

| ファイル | 中身 |
|---|---|
| `test.py` | Python 版（`requests`） |
| `voicevox_rs/` | Rust 版（`reqwest`、`query` 機能が必要）。練習用で、同じ処理は [`../ocr_ai/claude_rs/`](../ocr_ai/claude_rs/) に組み込み済み |

```bash
# Python 版（requests が入った venv で。例: ../ocr_ai/.venv）
python test.py

# Rust 版
cd voicevox_rs && cargo run
```

どちらも `test.wav` を作る（git 管理外）。`aplay test.wav` で再生できる。

## 話者（speaker）の番号

| 番号 | キャラクター |
|---|---|
| 2 | 四国めたん |
| 3 | ずんだもん |
| 8 | 春日部つむぎ |
| 9 | 波音リツ |
| 11 | 玄野武宏 |
| 13 | 青山龍星 |

全員の一覧は、アプリ起動中に `curl http://localhost:50021/speakers` で取れる。

## 注意

- 作った音声を使うときは、**「VOICEVOX:ずんだもん」のようにクレジットを表記する**（キャラクターごとの利用規約も確認する）
- 長い文章を一度に渡すと、音声を作るのに時間がかかる。全文（`full`）を読むときは `。` で区切って 1 文ずつ渡すとよい
