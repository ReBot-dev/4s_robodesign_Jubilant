# CRANE-X7 インタラクション作業の指示

## 引き継ぐ文脈

作業開始時に、同じフォルダの `AGENT.md`、`HANDOFF_drowsiness.md`、`README.md` を読む。
詳細な検証手順が必要なときは `simulation/README.md` も読む。
日付付きの過去の記録よりも、現行コードと最新の追記を優先する。

- かいとさんの担当はインタラクション（内部状態管理・ジェスチャー認識）。目的はロボットに生命感を与えること。
- 合意済みの方針・目標の状態遷移・TODOは `AGENT.md` の「目標と合意事項」にある。
- 設計の軸は「状態 → パラメータ → 動作」。研究上の目標と実装済みの機能を区別する。
- 日本語で、操作の目的と仕組みを小さく説明し、一緒に理解しながら進める。
- 学習や説明の依頼では、完成コードを一方的に渡して先へ進めない。
- 具体的な実装・修正・移行の依頼があるときは、その依頼を尊重して作業する。
- ユーザーが完了したと確認していない学習課題や実機検証を、完了扱いにしない。

## 現行の構成

- 通常起動の睡眠表現は `sleep_expression.py`。`drowsiness_expression.py` は旧表現と共通処理。
- `/joint_states` → 活動度 → 眠気 → 表現動作。表現の指令角速度（`/expression_joint_velocity`）を活動度から差し引く。
- 活動度は眠気の増加を遅くする。現在は外部刺激による覚醒・手振り認識・書類追従は未実装。
- このフォルダ自体はまだ ament パッケージではない。Python スクリプトをlaunchから起動している。
- 通常の表現ノードはGazebo用の確認を行う。実機用は別の入口
  `hardware_sleep_expression.py` と `hardware_activity.launch.py` を使う。
  `HARDWARE_MOTION.md`を読む。ユーザー指定の公式D435取り付け図を前提に進めるが、
  実機ログで待機/睡眠姿勢への移動成功あり。揺れの修正後の実機確認は未完了。
- ユーザーから「動作指示は送らないで」と指定されている。
  エージェントは読み取り・ローカル修正/テストを行い、実機の起動/再起動や動作指令は送らない。

## 確認コマンド

以下はチームのリポジトリのルートを作業ディレクトリとする。

数値・軌道データのテスト（画面は起動しない。`OK` が成功）:

```bash
source /opt/ros/jazzy/setup.bash
python3 src/arm_control/simulation/test_drowsiness.py
python3 src/arm_control/simulation/test_drowsiness_expression.py
python3 src/arm_control/simulation/test_sleep_expression.py
```

画面で動作を見る場合:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch ./src/arm_control/simulation/manual_activity.launch.py
```

Gazebo・RViz・グラフが起動し、静止状態から約30秒で眠気がしきい値に達する。
別端末で通信を見るときは ROS 環境を読み込み、`export ROS_DOMAIN_ID=87` を設定する。
`simulation/verify_*.py` は起動済みGazeboで関節を動かす検証であり、単体テストとは異なる。

必要な変更に応じて上記テストやビルドを実行する。資料だけの変更ではリンク・パス・記載の整合性を確認する。
実行していないGUI・実機検証を、今回確認したと報告しない。

## 記録の維持

実装や合意が変わったら `AGENT.md` と `HANDOFF_drowsiness.md` の関連箇所を更新する。
依存コードの変更は `THIRD_PARTY.md` に記録し、元のライセンスを保持する。
