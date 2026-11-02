# ocr_recognizer — OCR 認識

紙に印刷された**海外の文書（英語）を読み取る**担当パッケージ。
ArUco 班が出す「正対補正した紙の画像」を入力にして、読み取った文字列を次の工程（LLM での日本語への翻訳）へ渡す。

最終的な流れ（予定）:

```
カメラ（D435i）→ ArUco で紙を正対補正 → OCR（このパッケージ）→ LLM で翻訳・要約 → 音声でスピーカー出力
```

## いまの状況

- **OCR エンジンの比較は完了。** 結果は下の「これまでの結果」と [`benchmark/RESULTS.md`](benchmark/RESULTS.md)。
- **LLM（Claude）での翻訳・読み上げ文の生成は動作確認済み**（[`../ocr_ai/`](../ocr_ai/)）。Python 版に加えて Rust 版（`claude_rs`）も動く。
- **VOICEVOX での音声合成も動作確認済み**（[`../ocr_voicevox/`](../ocr_voicevox/)）。
- **正対補正は OCR 班でやることに決定**。カメラ画像を直接受け取り、ArUco の検出から補正まで OCR 側で行う（下の「これから」）。
- **ROS 2 パッケージ化した。** ノード `ocr_node` は、カメラ画像からカードを見つけて補正し、Claude で日本語の読み上げ文を作るところまで動く（合成画像で確認。下の「ROS 2 ノード」）。
- **読む紙は小さいカード（A5、ArUco ID 1〜4）に変更**（[`test_docs/card/`](test_docs/card/)）。

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
| `ocr_recognizer/ocr_node.py` `ocr_recognizer/prompt.py` | ROS 2 ノードの本体と、Claude への指示文 |
| `package.xml` `setup.py` `setup.cfg` `resource/` `test/` | ROS 2 パッケージの設定（`ros2 pkg create` で作ったもの） |

`.venv/`（Python 仮想環境）はどのフォルダでも **git 管理外**。各自が自分の PC で作る。

実験用のフォルダ（`benchmark/` `easyocr_test/` `paddleocr_test/`）には空のファイル `COLCON_IGNORE` を置いてある。
colcon が中の `.venv` などを ROS のパッケージと勘違いしないようにするため。

## ROS 2 ノード（`ocr_node`）

カメラ画像のトピック `/camera/camera/color/image_raw` を購読し、次の順に処理する（ここまでで OCR 班の担当分は一通りそろった）。

1. ArUco マーカー（ID 1〜4）を 4 つ探す
2. マーカーが「止まったまま 1 秒」見えたら、その紙を読むと決める（同じ紙は 1 回だけ。マーカーが見えなくなったらリセット）
3. 紙を真上から見た形に補正し、読む向きに 90 度回す（確認用に `/tmp/rectified.png` に保存）
4. 補正した画像を Claude に直接送り、`Reading`（種類・要点・全文・不明な点）を受け取ってログに出す
5. 要点を VOICEVOX で音声にしてスピーカーで鳴らす（話者はずんだもん、速さ 1.2 倍）。読めなかった所があれば「原本で確認してください」と付け足す
6. `/ocr/done`（`std_msgs/String`）を出す。中身は読み上げた要点。**途中で失敗したときも空の文字列で出す**（アームが待ち続けないように）

4〜6 は合わせて数十秒かかるので別スレッドで動かし、その間に届いた画像は無視する。

| ファイル | 中身 |
|---|---|
| `ocr_recognizer/ocr_node.py` | ノード本体。上の方の「設定」に、紙の寸法・安定判定の秒数・使うモデルをまとめてある |
| `ocr_recognizer/prompt.py` | Claude への指示文。`../ocr_ai/system_prompt.txt` を「入力が画像」向けに書き換えたもの |

### 読む紙（カード）

台紙は [`test_docs/card/corner0.pdf`](test_docs/card/corner0.pdf)（詳しくは [`test_docs/README.md`](test_docs/README.md)）。

- A4 の上半分（210 × 148.5 mm）を切り取って使う。**台紙の右端が、読むときの上**（読む向きでは A5 縦）
- ArUco `DICT_4X4_50` の **ID 1〜4**。台紙の向きで左上 1・右上 2・右下 3・左下 4
- 黒い四角は一辺 **30mm**、紙の端から 15.5mm（白い余白 7.5mm を含めると 8mm）

### 準備（最初の 1 回だけ）

ノードは Claude の SDK（`anthropic`）を使う。システムの Python には入っていないので、**ROS も使える仮想環境**を作って入れる。

```bash
cd ~/github/4s_robodesign_jubilant
python3 -m venv --system-site-packages .venv     # ROS・OpenCV もそのまま使える仮想環境
touch .venv/COLCON_IGNORE                         # colcon に中を探させない
.venv/bin/pip install anthropic "pydantic>=2" "brotli>=1.2"
sudo apt install ros-jazzy-image-publisher        # カメラなしで試すとき用
```

`setup.cfg` の `[build_scripts]` で、ノードは「そのとき有効な仮想環境の Python」で動くようにしてある。

### ビルドと実行

**必ずリポジトリのルートで** ビルドする（パッケージの中で実行すると、そこに `build/` `install/` `log/` ができてしまう）。

```bash
cd ~/github/4s_robodesign_jubilant
source .venv/bin/activate                              # 端末を開くたびに
source install/setup.bash                              # 端末を開くたびに（ビルド後）
read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY # 端末を開くたびに。キーは画面にも履歴にも残らない
# VOICEVOX のアプリを起動しておく（開いている間だけ http://localhost:50021 で音声合成が動く）
colcon build --packages-select ocr_recognizer
ros2 run ocr_recognizer ocr_node
```

### カメラなしで試す（画像をトピックに流す）

```bash
# 別の端末で。カードを斜めに撮った想定の合成画像を、カメラと同じトピック名で 1 秒に 2 回流す
ros2 run image_publisher image_publisher_node \
  src/ocr_recognizer/test_docs/card/sim_02_invoice.jpg \
  --ros-args -r image_raw:=/camera/camera/color/image_raw -p publish_rate:=2.0
```

- `sim_02_invoice.jpg` は `test_docs/card/02_invoice.pdf` を机の上に斜めに置き、D435i くらいの画質に落とした**合成画像**（本物の写真ではない）
- ノードのログに、約 1 秒後に `紙を見つけました`、10〜20 秒後に `要点:` が出れば OK。答え合わせは `test_docs/card/02_invoice.txt`（合計 $136.25・支払期限 12/15/2026）
- 終わったら、流している端末を **`Ctrl+C` で止める**。流しっぱなしだと、次にノードを起動したときにまた読んでしまう（Claude の料金がかかる）
- 流れているかの確認は `ros2 topic hz /camera/camera/color/image_raw`、画像を見るなら `ros2 run rqt_image_view rqt_image_view`
- 他の人のノードと混ざらないように試したいときは、両方の端末で `export ROS_DOMAIN_ID=77` のように同じ別の番号にする

### ハマりどころ（ROS 2 ノード）

- **`Package 'ocr_recognizer' not found`** → その端末で `source install/setup.bash` をしていない
- **`ModuleNotFoundError: No module named 'anthropic'`** → その端末で `source .venv/bin/activate` をしていない
- **`Claude につながりません ... process() takes no keyword arguments`** → 仮想環境の brotli が古い（apt の 1.1 が使われている）。`.venv/bin/pip install "brotli>=1.2"`。このエラーは**返事を受け取った後**に起きるので、Claude の料金はかかっている（SDK が自動で最大 3 回やり直す）
- **`ANTHROPIC_API_KEY が設定されていません`** → その端末で `read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY`
- **「画像を待っています」のまま** → 誰も画像を流していない。上の `image_publisher` を別の端末で動かす
- **`VOICEVOX につながりません`** → VOICEVOX のアプリが閉じている。開いてから、紙を置き直す（画像を流し直す）
- **音が出ない（`aplay が失敗`）** → スピーカーの出力先を確認。`aplay` の代わりに `pw-play` や `paplay` でも鳴らせる
- 読み上げた音声を人に聞かせるときは、**「VOICEVOX:ずんだもん」のようにクレジットを表示する**（話者を変えたらその名前）
- **`import cv2` や `cv_bridge` が numpy のエラーで落ちる** → `~/.local` に pip で入れた numpy 2.x が、システムの numpy 1.26 より優先されている。`~/.local/lib/python3.12/site-packages/` の `numpy` 関係を消す（`pip uninstall` には `--user` の指定がない）
- **Ubuntu 24.04 の OpenCV は 4.6** なので、`cv2.aruco.ArucoDetector`（4.7 以降）は使えない。`cv2.aruco.detectMarkers(gray, dictionary)` の書き方を使う
- **`colcon build --packages-select` の名前は `ocr_recognizer`**（アンダースコア）。`ocr-recognizer` だと無視される
- `package.xml` の `<depend>` は重複・大文字小文字の違いがあると、パッケージとして読み込まれない
- エラーが出たら、Python のエラーは**一番下の行**から読む。`/opt/ros/...` の行は ROS の内部なので読み飛ばしてよい

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
- Claude の結果（`summary`）を VOICEVOX に渡して、「文字列 → Claude → 音声」を通しで動かす。
- 正対補正は OCR 班で行う（決定）:
  - D435i のカラー画像（1920×1080）を直接購読し、`cv2.aruco` でマーカーを検出 → 補正（1mm = 10px）。[`benchmark/rectify.py`](benchmark/rectify.py) の処理を使う
  - ArUco 班が出しているのはマーカーの 3D の位置と姿勢（アーム用）なので、補正には使わず OCR 側で検出し直す（検出は数ミリ秒で済む）
  - 読むのは、4 つのマーカーが止まったまま 1 秒見えたとき（アームが止まって紙が安定したとき）に 1 回だけ。読み上げが終わったら `/ocr/done`（仮）で合図を出す
  - マーカーの仕様は ArUco 班と共通: カードの台紙 `test_docs/card/corner0.pdf`（DICT_4X4_50、ID 1〜4、一辺 30mm）
- `ocr_node` を段階的に作る（ROS 2 で正式に使える Python で書く）:
  1. ✅ 画像トピックを購読して受け取る
  2. ✅ ArUco の検出と補正（`rectify.py` の処理を OpenCV 4.6 の書き方で移した。カード用に、台紙の向きで補正してから 90 度回す）
  3. ✅ 安定判定（止まったまま 1 秒で 1 回だけ）と、補正した画像を Claude に直接渡して `Reading` を受け取る（OCR と翻訳を 1 回でまとめる。合成画像で 13 秒・数字は全部正解）
  4. ✅ `summary` を VOICEVOX で音声にして再生し、`/ocr/done` を出す（実機の VOICEVOX アプリで確認済み）
  - カードを印刷して、本物の D435i で撮った画像で確かめる
