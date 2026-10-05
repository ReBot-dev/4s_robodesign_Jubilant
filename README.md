# 4s_robodesign_jubilant

2026 ロボットデザイン チーム Jubilant のリポジトリ。

D435（RGB-D カメラ）を取り付けたロボットアームで、**四隅に ArUco マーカーが印刷された紙**を検出し、
その紙に書かれた**日本語の文字を OCR で読み取る**ことを目指すプロジェクトです。

## チーム分担とディレクトリ構成

機能ごとに ROS 2 パッケージを分け、各自が自分のパッケージの中だけを担当します。
こうすると別々のフォルダを触るので、**お互いの変更がぶつかりにくく**なります。

| パッケージ（`src/` 配下） | 担当 | 役割 |
|---|---|---|
| `aruco_detector` | ArUco 班 | 紙の四隅の ArUco を検出し、紙の位置・姿勢を出す |
| `ocr_recognizer` | OCR 班 | 紙の日本語文字を読み取る（詳細 → [`src/ocr_recognizer/README.md`](src/ocr_recognizer/README.md)）|
| `arm_control` | アーム班 | アームの軌道生成・ロボットの動作 |
| `msg_interfaces` | 共通 | 班どうしで受け渡すメッセージ型（`.msg`）の置き場 |
| `bringup` | 共通 | 全部をまとめて起動する launch ファイル（最後の「合体」用）|

> カメラ固定パーツ（ハードウェア設計）は CAD ファイルが大きいので、このリポジトリとは別で管理します。

## 開発環境

- Ubuntu / Pop!_OS + **ROS 2 Jazzy**
- `git`, Python 3.12

## はじめに：リポジトリを手元に持ってくる（最初の 1 回だけ）

「クローン(clone)」= GitHub 上のリポジトリを自分の PC にコピーすること。

```bash
cd ~/github                 # 置きたい場所へ（どこでもよい）
git clone https://github.com/ReBot-dev/4s_robodesign_jubilant.git
cd 4s_robodesign_jubilant
```

初めて git を使う人は、最初に名前とメールを設定しておきます（コミットに記録されます）。

```bash
git config --global user.name  "あなたの名前"
git config --global user.email "あなたのメール"
```

## 毎回の開発の流れ（GitHub 初心者向け・ここが一番大事）

ルール: **`main` ブランチで直接作業しない。** 自分用の「ブランチ」を切って作業し、
できたら「プルリクエスト(PR)」で `main` に取り込みます。

```bash
# 1. 最新を取り込む（他の人の変更を反映）
git checkout main
git pull

# 2. 作業用ブランチを main から切る（名前は 担当/内容 が分かりやすい）
git checkout -b ocr/easyocr-test

# 3. ファイルを編集したら、変更を記録(commit)する
git add <変更したファイル>        # 例: git add src/ocr_recognizer/
git commit -m "何をしたかの説明"

# 4. GitHub に自分のブランチを上げる(push)
git push -u origin ocr/easyocr-test
```

5. ブラウザで GitHub のリポジトリを開くと「Compare & pull request」ボタンが出るので、
   それを押して **Pull Request** を作成。他のメンバーが確認してから `main` に Merge します。

用語メモ:
- **commit** … 変更の「セーブポイント」を作ること（まだ自分の PC の中だけ）
- **push** … セーブした変更を GitHub に送ること
- **Pull Request (PR)** … 「この変更を main に入れていい？」とチームに出す提案

## ビルドと実行（ROS 2 / colcon）

各パッケージの中身が揃ったら、リポジトリのルートでビルドします。

```bash
cd ~/github/4s_robodesign_jubilant
colcon build
source install/setup.bash
```

> まだ各パッケージの中身を作っている段階です。自分のフォルダを ROS 2 パッケージにするには、
> `src/` の中で `ros2 pkg create <パッケージ名> --build-type ament_python`（Python の場合）を使います。

## コミットしてはいけないもの（設定済み）

次のものは `.gitignore` で除外済みなので、`git add` しても上がりません（上げると壊れる・肥大するため）。

- `build/` `install/` `log/` … colcon が自動生成する
- `.venv/` `__pycache__/` … Python の仮想環境・中間ファイル

## 困ったとき

- **push したら main に拒否された** → ルール通りです。ブランチを切ってから push し、PR で取り込みましょう。
- **他の人の変更とぶつかった(conflict)** → 慌てず `git pull` してから落ち着いて解消。分からなければチームで相談。
