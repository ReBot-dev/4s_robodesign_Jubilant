# 実機の関節情報から活動度・眠気を確認する

通常の実機制御ドライバなしで、このフォルダの読み取り専用ノードから実機の
角度・速度を取得し、活動度・眠気を表示できます。
位置指令・トルク変更・PID変更・動作モード変更・再起動の命令は送りません。
起動時・終了時もサーボの設定を変更しません。
ROS 2 JazzyとDYNAMIXEL SDKを使用し、`install/`や移行元の`ros2_ws`は不要です。
このフォルダ自体はROSパッケージではないため、スクリプトを直接launchします。

## このフォルダだけで確認する（推奨）

依存ライブラリがない場合は一度インストールします。

```bash
sudo apt install ros-jazzy-dynamixel-sdk
```

### 実機なしで起動を試す

```bash
cd /home/kaito/4s_robodesign_jubilant
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=88
ros2 launch ./src/arm_control/hardware_readonly.launch.py source:=mock
```

`MOCK`と明示して、角度・活動度・眠気を端末に1秒ごとに表示します。
USBポートは開きません。模擬入力は10秒ずつ静止→動作→静止を繰り返します。
活動度は動作区間で上下し、眠気は増え続けます。実機の確認結果とは区別してください。
終了は Ctrl+C です。

### 実機の角度を読む

標準CRANE-X7（アーム7軸、ID 2〜8、XM430-W350 / 肩のみXM540-W270、
Protocol 2.0、3 Mbps）向けです。グリッパーは今回読みません。
別のID・機種へ変更してある場合はそのまま使えません。
起動時にモデル番号を読み、標準構成と異なる場合は終了します。

1. 通常の実機ドライバ、DYNAMIXEL Wizard、ほかのシリアル接続ソフトを終了します。
   シミュレーションと睡眠表現も終了します。このlaunch以外から動作させないでください。
2. 電源投入でトルクが入るとは限らないので、アームが倒れない姿勢・支持を確保して、
   実機の電源とUSB通信を接続します。このノードは姿勢を保持するトルクを有効にしません。
3. ポート名を確認します。可能なら抜き差しで変わりにくい `/dev/serial/by-id/` のパスを使います。

```bash
ls -l /dev/serial/by-id/
ls -l /dev/ttyUSB*
```

実機なしの確認を終了してから、次を実行します。

```bash
cd /home/kaito/4s_robodesign_jubilant
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=88
ros2 launch ./src/arm_control/hardware_readonly.launch.py port:=/dev/ttyUSB0
```

ポート名が異なる場合は置き換えます。必要なら`baudrate:=3000000 rate:=10.0`も指定できます。
baudrateはPC側の通信速度であり、サーボ側の設定値は書き換えません。
ポートの権限がない場合は`groups`と`ls -l`で所有グループを確認し、
通常は`sudo usermod -aG dialout "$USER"`の後にログインし直します。
ROS全体をsudoで起動したり、デバイスを全ユーザー書き込み可にする必要はありません。

表示の`SERIAL angles[deg]=[...]`が7関節の取得角度です。
標準の2048パルスを0°、4096パルスを1回転として換算しています。
取り付け・Homing Offset変更後の校正は行わず、姿勢制御用の値としては使いません。
活動度には、同時に読み取った実測速度（rad/s）を渡します。
`existing torque enabled`は起動時に読んだ各軸の状態で、変更はしません。

```text
実機USB → readonly_joint_states → /hardware_observation/joint_states
                                              ↓
                                      activity_monitor
                                              ↓
                              /hardware_observation/activity
                                              ↓
                                      drowsiness_node
                                              ↓
                            /hardware_observation/drowsiness
```

静止中は活動度がほぼ0で、眠気が徐々に増えます。眠気0.6を超えても動作は起きません。
最初は`waiting`と表示される場合があります。続く場合や`STALE`の場合は通信確認が必要です。
起動失敗・読み取り失敗・不完全な応答・サーボエラーはログに出し、3ノード全体を終了します。
再接続・トルク変更・通信設定の書き換えによる自動復旧はしません。
終了は Ctrl+C。終了してもトルク状態は変わりません。

値を別端末で見る場合は同じROS環境とdomainを設定します。

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=88
ros2 topic echo /hardware_observation/joint_states --once --qos-reliability best_effort
ros2 topic echo /hardware_observation/activity
# Ctrl+Cで表示を止めてから
ros2 topic echo /hardware_observation/drowsiness
```

## 既存の実機ドライバが配信している情報だけを観測する場合

以下は以前の2ノード構成です。実機のシリアルポートへは接続せず、
すでに存在する `/joint_states` を受け取ります。
`hardware_readonly.launch.py`と同時に起動しないでください。

## 1. 関節情報の配信元を確認する

実機から `/joint_states` がすでに配信されている環境で使います。
まだ配信されていない場合はここで止め、実機担当者とドライバの起動方法を確認してください。
同梱の実機ドライバは `on_activate()` で現在位置を書き込み、トルクを有効にします。
通常の実機launchやdemoを「情報を読むだけ」のつもりで起動しないでください。
この確認用launchは、別プロセスによる動作を止めるものではありません。

シミュレーションと睡眠表現は終了しておき、実機ドライバと同じROS domainを使います。
以下は実機側がdomain 0の場合の例です。実機が別の値なら、両端末の `0` をその値に置き換えます。
シミュレーション用の `87` は自動設定しません。

```bash
cd /home/kaito/4s_robodesign_jubilant
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic info -v /joint_states
ros2 topic echo /joint_states --once --qos-reliability best_effort
ros2 topic hz /joint_states
```

publisherが実機の配信元であり、Gazebo・mock・joint_state_publisherではないことを確認します。
`name` と `position` にCRANE-X7の関節情報があり、継続して受信できることを確認します。
`hz` は数秒見た後 Ctrl+C で終了します。配信元が不明・複数なら先に構成を整理します。
名前空間付きの関節トピックを使っている場合は、以降の `/joint_states` もその名前に置き換えます。

## 2. 観測ノードだけ起動する（端末1）

```bash
ros2 launch ./src/arm_control/hardware_observation.launch.py
```

関節トピック名が異なる場合は `joint_states_topic:=/robot/joint_states` のように指定できます。
実時間を使い、活動度と眠気は次の専用トピックへ配信します。

```text
/joint_states → activity_monitor → /hardware_observation/activity
                                          ↓
                                  drowsiness_node
                                          ↓
                            /hardware_observation/drowsiness
```

`/expression_active` も専用の名前へ変更しているため、通常の表現フラグの影響は受けません。
既存の `/activity`・`/drowsiness` へは配信しません。

## 3. 接続と値を確認する（端末2）

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
ros2 node info /hardware_observation/activity_monitor
ros2 node info /hardware_observation/drowsiness_node
ros2 topic echo /hardware_observation/activity
```

活動度の表示を Ctrl+C で止め、眠気を見ます。

```bash
ros2 topic echo /hardware_observation/drowsiness
```

静止中の目安は活動度がほぼ0、眠気が起動時の0から徐々に増えて約30秒で0.6です。
0.6を超えても、このlaunchから動作は起きません。終了は両端末で Ctrl+C です。
再起動すると眠気は0から始まります。

**眠気が増えることだけでは、実機入力の確認になりません。**
眠気ノードは関節情報が未受信・途絶中でも、最後の活動度（初期値0）で計算を続けます。
関節情報の継続受信と活動度の更新を必ず併せて確認してください。
活動度は関節情報が途絶えると新しい値を配信しません。

`node info` で活動度ノードの購読先が実機の関節トピック、
眠気ノードの購読先が `/hardware_observation/activity` であることも確認します。
観測ノードから軌道アクションや関節指令トピックへの接続はありません。

## 今回確認できる範囲

- 実機の関節情報を受信できること。
- 静止時の活動度と眠気の計算・通信がつながること。

動作中の活動度の反応は、この静止確認だけでは確認できません。
アームを手で押したり、トルクを切ったりして入力を作らず、動作試験は別途扱います。
現行の活動度は `velocity` があればそれを採用し、空のときだけ `position` の差分を使います。
速度配列が常に0で埋まる配信元では、位置が変わっても活動度は上がりません。
関節情報の購読にはsensor data QoS（best effort）を使い、reliableとbest effortの
どちらの配信元にも接続できるようにしています。

## テスト

実機を接続せずに実行できます。

```bash
source /opt/ros/jazzy/setup.bash
python3 -m unittest discover -s src/arm_control/tests -v
python3 src/arm_control/simulation/test_drowsiness.py
python3 src/arm_control/simulation/test_drowsiness_expression.py
python3 src/arm_control/simulation/test_sleep_expression.py
```

通信テストは実際のSDKで生成する命令がREADのみであること、符号・単位の換算、
異機種・通信エラー・不完全な応答での終了、ポート解放を実機なしで確認します。
制御テーブルの出典はROBOTISの
[XM430-W350](https://emanual.robotis.com/docs/en/dxl/x/xm430-w350/)、
[XM540-W270](https://emanual.robotis.com/docs/en/dxl/x/xm540-w270/)、
[Python PacketHandler](https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/api_reference/python/python_packethandler/)
です。

2026-11-02の追加確認では、通信部の5テストと既存17テストが成功しました。
localhost通信を使ったmock起動でも、7関節の配信、活動度の静止→上昇→減衰、
眠気の増加、専用トピックへの接続、動作指令接続がないことを確認しました。
存在しないテスト用ポートを指定し、起動失敗時にlaunch全体が終了することも確認しました。
終了時に活動度ノードがSIGINTで終了せず、launchが5秒後にSIGTERMで終了させる例がありました。
実機への接続、実測角度・速度の妥当性、電源投入時の姿勢保持は未検証です。

## 準備時の確認（2026-11-02、既存情報を受け取る構成）

既存の数値・軌道テスト17件、launch引数の読み込み、2プロセスのみの起動構成、
実時間設定、カスタム関節トピックと専用出力へのremap展開を確認しました。
この作業環境ではDDSのソケット作成が `Operation not permitted` となったため、
模擬入力によるノード間通信は未確認です。実機接続・GUI・実機動作も未確認です。
