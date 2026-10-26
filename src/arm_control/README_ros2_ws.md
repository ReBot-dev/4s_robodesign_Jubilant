> 移行前の構成・実装の記録です。現在の起動方法は [README.md](README.md) を参照してください。

# RS3 — CRANE-X7 の活動度と眠気表現

CRANE-X7 にライトを持たせて書類を追従させ、時間とともにうとうとし、手振りで起きるインタラクションを目指す ROS 2 プロジェクトです。「状態 → パラメータ → 動作」を軸に、連続的な内部状態から動きを生成します。

現在は **Gazebo 上での活動度計測・眠気の更新・うなずき表現** を実装しています。書類追従、MediaPipe Hands / RealSense による手振り認識、外部刺激による覚醒は未実装です。

## 動作環境

- Ubuntu 24.04 / ROS 2 Jazzy
- Gazebo、ros2_control、MoveIt 2、RViz 2
- Python 3、rclpy、rqt_plot、python_qt_binding
- GUI 表示環境（手動操作の場合）

CRANE-X7 の実機を接続せずにシミュレーションを実行できます。

## セットアップ

ROS 2 Jazzy、rosdep、colcon を導入した環境で実行してください。

```bash
git clone --recurse-submodules https://github.com/robotKR/RS3.git
cd RS3
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
sudo apt install ros-jazzy-rqt-plot ros-jazzy-gz-ros2-control
colcon build --symlink-install
source install/setup.bash
```

通常の clone を実行した場合は、ビルド前に `git submodule update --init --recursive` で依存パッケージを取得してください。依存パッケージは、このワークスペースで使用しているコミットに固定しています。

## シミュレーションを起動する

リポジトリのルートで実行します。

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch ./src/arm_control/simulation/manual_activity.launch.py
```

Gazebo、RViz、活動度・眠気ノード、グラフ、うなずき表現が起動します。眠気が 0.6 に達すると、開始時の姿勢を中心に肩の上下軸が ±5°・4秒周期で動きます。終了するには起動端末で Ctrl+C を押します。

RViz の MotionPlanning で Planning Group を `arm` にし、Goal State を `home` または `vertical` に変更して Plan & Execute を実行すると、動作に伴う活動度の変化を確認できます。手動操作中にうなずかせない場合は、次のように起動します。

```bash
ros2 launch ./src/arm_control/simulation/manual_activity.launch.py nod:=false
```

起動ファイルは ROS_DOMAIN_ID=87 を設定します。別端末でトピックを確認する場合は、ROS 環境を読み込み、同じ値を設定してください。

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=87
ros2 topic echo /activity
# 眠気を見る場合: ros2 topic echo /drowsiness
```

## ノードとトピック

| ノード / ファイル | 入力 | 出力 / 役割 |
| --- | --- | --- |
| `activity_monitor.py` | `/joint_states`、`/expression_active` | `/activity`（Float32、0〜1） |
| `drowsiness_node.py` | `/activity` | `/drowsiness`（Float32、0〜1） |
| `drowsiness_expression.py` | `/drowsiness`、関節状態、ロボット記述 | 関節軌道アクション、`/expression_active`（Bool） |
| `simulation/activity_plot.py` | `/activity`、`/drowsiness` | 2本の時系列グラフ |

活動度は関節角速度のノルムをしきい値で判定し、ローパスフィルタで平滑化します。現在の実装は `JointState.velocity` があればそれを使い、空の場合に位置差分へフォールバックします。「常に位置差分を使う」という設計上の合意は、まだ反映されていません。

眠気 S は次の式を時間積分し、0〜1 に制限します。

```text
dS/dt = k_up * (1 - alpha * m) * (1 - S) - k_down * external_stimulus
m = 活動度
external_stimulus = 0（現在は未接続）
```

既定値は `k_up=0.03`、`alpha=0.8`、`k_down=0.1`、更新頻度 20 Hz です。静止時は約30.5秒で S=0.6 に達します。活動度は眠気の増加を遅らせますが、現在は眠気を低下させません。表現中は `/expression_active` によって活動度を固定します。

現在の表現は sin 波による反復上下動です。設計上の「頭が下がるだけ」の表現とは区別してください。表現ノードは Gazebo のハードウェア記述を確認して動作しますが、衝突回避計画は行いません。まず既定の垂直姿勢で確認してください。

## 検証

ROS ノードやロボットを動かさずに、数値モデルと表現制御のテストを実行できます。

```bash
source /opt/ros/jazzy/setup.bash
python3 src/arm_control/simulation/test_drowsiness.py
python3 src/arm_control/simulation/test_drowsiness_expression.py
```

GUI を使わない検証用の起動ファイルもあります。

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=87
export GZ_PARTITION=crane_x7_activity_check
ros2 launch ./src/arm_control/simulation/activity_check.launch.py
```

別端末で同じ ROS 環境と ROS_DOMAIN_ID を設定し、以下の検証を1つずつ実行します。検証スクリプトはシミュレーションの関節を動かすため、実行中は RViz から操作しないでください。

```bash
python3 src/arm_control/simulation/verify_activity.py --ros-args -p use_sim_time:=true
python3 src/arm_control/simulation/verify_drowsiness.py --ros-args -p use_sim_time:=true
python3 src/arm_control/simulation/verify_drowsiness_expression.py --ros-args -p use_sim_time:=true
```

詳細な起動手順、パラメータ、2026-10-19 の検証記録は [simulation/README.md](simulation/README.md) を参照してください。検証結果は `simulation/results/` に生成されます。

## ディレクトリ構成

```text
.
├── activity_monitor.py          # 活動度の生成
├── drowsiness_node.py           # 眠気の積分
├── drowsiness_expression.py     # 眠気に応じた関節動作
├── simulation/                  # 起動・描画・テスト・検証スクリプト
├── src/crane_x7_ros/            # RT製ROS 2パッケージ（サブモジュール）
├── src/crane_x7_description/    # RT製モデル（サブモジュール）
├── AGENT.md                     # 設計上の合意と進め方
└── HANDOFF_drowsiness.md        # 引き継ぎ資料
```

`build/`、`install/`、`log/`、Python キャッシュ、生成された検証結果は Git 管理対象外です。既存の資料には作業環境固有の `/home/kaito/4s_robodesign_jubilant` が記載されています。別の場所へ clone した場合はリポジトリのルートに読み替えてください。

## 依存パッケージのライセンス

- [crane_x7_ros](https://github.com/rt-net/crane_x7_ros): Apache License 2.0
- [crane_x7_description](https://github.com/rt-net/crane_x7_description): RT Corporation の NON-COMMERCIAL LICENSE

それぞれのサブモジュール内の LICENSE を確認してください。本プロジェクト独自部分のライセンスは未設定です。
