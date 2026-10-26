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
静止状態から約30秒で眠気が0.6に達し、MoveItで頭を下げます。
到達後は肩を±3°・6秒周期で揺らし、手首を逆向きに動かして先端を下向きに保ちます。
`nod:=false` で表現を無効化できます。終了は起動端末で Ctrl+C を押します。
実機用ドライバは起動しません。現在の表現ノードはGazebo専用です。

```text
/joint_states → activity_monitor.py → /activity → drowsiness_node.py → /drowsiness
                       ↑                                                  ↓
                /expression_active ← sleep_expression.py → MoveIt / 関節軌道
```

眠気は活動度が高いと増加が遅くなります。外部刺激による覚醒、手振り認識、書類追従は未実装です。
`drowsiness_expression.py` は以前の肩のみを動かす表現で、通常起動では `sleep_expression.py` を使います。

別端末で確認する場合は ROS 環境を読み込み、`export ROS_DOMAIN_ID=87` を設定してください。
詳細なパラメータ・GUIなしの起動・シミュレーション実測方法は
[simulation/README.md](simulation/README.md) にあります。

## テスト

ロボットを動かさずに実行できます。リポジトリのルートで実行してください。

```bash
source /opt/ros/jazzy/setup.bash
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
