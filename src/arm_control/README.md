# CRANE-X7 の活動度・眠気・睡眠表現

関節の活動度から眠気を更新し、CRANE-X7 が下を向いてゆっくり揺れる ROS 2 シミュレーションです。
`ros2_ws` で開発していたコード・起動設定・検証スクリプトを移行しました。
自作ノードは Python スクリプトとして起動します。このフォルダ自体はまだ ament パッケージではありません。

## セットアップ

Ubuntu 24.04 / ROS 2 Jazzy と Gazebo、MoveIt 2 を使用します。
以下はチームのリポジトリのルートで実行してください。

```bash
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src/crane_x7_ros src/crane_x7_description --ignore-src -r -y
sudo apt install ros-jazzy-rqt-plot ros-jazzy-gz-ros2-control
colcon build --symlink-install
source install/setup.bash
```

CRANE-X7 の依存パッケージは `src/crane_x7_ros/` と `src/crane_x7_description/` に同梱しています。
追加のサブモジュール取得は不要です。取得元・固定コミット・ローカル修正は
[THIRD_PARTY.md](THIRD_PARTY.md) を参照してください。

## 起動

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch ./src/arm_control/simulation/manual_activity.launch.py
```

Gazebo、RViz、活動度・眠気ノード、グラフ、睡眠表現が起動します。
起動後、関節情報とMoveItの準備ができたら、睡眠姿勢に近い待機姿勢
（肩20°・肘−120°・手首−80°、先端は下向き）へ一度移動して待機します。
静止状態から約30秒で眠気が0.6に達し、MoveItで頭を下げます。
到達後は肩を±3°・6秒周期で揺らし、手首を逆向きに動かして先端を下向きに保ちます。
`nod:=false` で表現を無効化できます。終了は起動端末で Ctrl+C を押します。
実機用ドライバは起動しません。現在の表現ノードはGazebo専用です。

```text
/joint_states → activity_monitor.py → /activity → drowsiness_node.py → /drowsiness
                       ↑                                                  ↓
  /expression_active, /expression_joint_velocity ← sleep_expression.py → MoveIt / 関節軌道
```

眠気は活動度が高いと増加が遅くなります。外部刺激による覚醒、手振り認識、書類追従は未実装です。
`drowsiness_expression.py` は以前の肩のみを動かす表現で、通常起動では `sleep_expression.py` を使います。

別端末で確認する場合は ROS 環境を読み込み、`export ROS_DOMAIN_ID=87` を設定してください。
詳細なパラメータ・GUIなしの起動・シミュレーション実測方法は
[simulation/README.md](simulation/README.md) にあります。

## 実機の角度・活動度・眠気を観測する

`crane_x7_ros`で実機の睡眠表現を動かす準備と操作は
[実機動作の手順](HARDWARE_MOTION.md) を参照してください。
RealSenseはユーザー指定の公式D435取り付け図を前提とします。実機ログで待機/睡眠姿勢への
移動成功を確認しました。揺れ開始時の接続処理は修正済みですが、修正後の実機確認は未完了です。
起動後はユーザーが開始サービスを操作するまで待機します。

実機の関節情報から活動度・眠気だけを見る場合は
[実機の観測手順](HARDWARE_OBSERVATION.md) を参照してください。
このフォルダだけで実機から読み取る場合は次を使用します（ROS 2 JazzyとDYNAMIXEL SDKが必要）。

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=88
ros2 launch ./src/arm_control/hardware_readonly.launch.py port:=/dev/ttyUSB0
# 実機なしで試す場合は末尾に source:=mock を追加
```

通常の制御ドライバは起動せず、読み取り専用接続→活動度→眠気の3ノードを起動します。
トルク・位置指令・設定の書き換えを行いません。事前の支持・接続確認は上記手順書を参照。
すでに配信中の関節情報だけを受け取る場合は `hardware_observation.launch.py` を使用します。
実機試験は未実施です。

## テスト

ロボットを動かさずに実行できます。リポジトリのルートで実行してください。

```bash
source /opt/ros/jazzy/setup.bash
python3 -m unittest discover -s src/arm_control/tests -v
python3 src/arm_control/simulation/test_drowsiness.py
python3 src/arm_control/simulation/test_drowsiness_expression.py
python3 src/arm_control/simulation/test_sleep_expression.py
```

`simulation/verify_*.py` は起動中のGazeboで関節を動かす検証です。
生成される `simulation/results/`、ワークスペースの `build/`・`install/`・`log/` はコミット対象外です。

## 引き継ぎ資料

- [HANDOFF_drowsiness.md](HANDOFF_drowsiness.md): 実装・検証の引き継ぎ
- [AGENT.md](AGENT.md): 設計方針・学習の進め方の記録（一部は以前の表現の説明）
- [README_ros2_ws.md](README_ros2_ws.md): 移行前のREADMEの記録

## エージェントと作業を続ける

Codexでチームのリポジトリを作業フォルダとして開いてください。
ルートの `AGENTS.md` が、アーム作業の指示・設計・引き継ぎ資料への入口です。
`src/arm_control/` から開始する場合も、そのフォルダの `AGENTS.md` に同じ案内があります。
保存した設計・進め方は資料で引き継ぎます。チャット全文や、このチャットの作業フォルダの設定はファイルコピーでは移りません。
