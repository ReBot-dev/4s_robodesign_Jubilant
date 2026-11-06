# CRANE-X7 活動度・眠気度のシミュレーション確認

Gazebo の関節状態から `activity_monitor.py` で活動度を生成し、
`drowsiness_node.py` で眠気を更新する構成です。
手動確認ではGazebo・RViz・グラフを、headless確認ではGUIを使わずに
物理シミュレーション、ros2_control、関節状態配信、活動度・眠気ノードを起動します。
実機用ドライバは起動しません。このワークスペースはsymlink installのため、
起動ファイルの修正後も再ビルドは不要です。

## 手で操作して活動度を見る

既にこのワークスペースの操作用シミュレーションを起動している場合は、
その起動端末で Ctrl+C を押してから、以下を1つの端末で実行します。

```bash
cd /home/kaito/4s_robodesign_jubilant
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch ./src/arm_control/simulation/manual_activity.launch.py
```

Gazebo・RViz・活動度ノード・眠気ノード・2本のグラフを一括起動します。
グラフのウィンドウ名は `CRANE-X7 activity & drowsiness` です。
凡例の `/activity/data` が活動度、`/drowsiness/data` が眠気度です。
データが準備できるまで自動的に接続を再試行し、画面下部に現在値と受信数を表示します。
静止時の0の線も見えるよう、縦軸には余白を設けています。
グラフを別途開いている場合は末尾に `plot:=false` を付けられます。
活動度ノードをさらに別端末で起動する必要はありません。
眠気ノードも自動起動するので、追加の端末は不要です。

### 下を向いて小さく揺れる睡眠表現

`manual_activity.launch.py` は `sleep_expression.py` を自動起動します。
起動後に関節情報・Gazebo・MoveIt・コントローラが揃ったら、まず肩20°・肘−120°・
手首−80°の待機姿勢へMoveItで一度移動します。先端は下向きのまま、眠気が
しきい値未満の間は静止して待機します。睡眠姿勢との差は肩と手首の各10°です。
初期モデルの生成姿勢を変えるのではなく、準備完了後に待機位置へ移動する方式です。
眠気が **0.6以上** になると、MoveItで経路を計画してゆっくり頭を下げます。
睡眠姿勢の中心角度は肩10°・肘−120°・手首−70°で、ねじり軸は0°です。
肩・肘・手首のピッチ合計が−180°になるため、先端の+Z軸が真下を向きます。
土台の旋回角と先端のロール角は開始時の値を保持します。

睡眠姿勢に到達したら、肩を **±3°・6秒周期** で動かし、手首は逆向きに動かします。
先端を真下に向けたまま、約2 cmの範囲でゆっくり上下に揺れる動きです。

```python
delta = amplitude * math.sin(2 * math.pi * t / period)
shoulder = shoulder_center + delta
wrist = wrist_center - delta
```

眠気がしきい値未満になったら、現在の1往復を終え、MoveItで開始前の姿勢へ戻ります。
現在は外部刺激が未接続なので、眠気は自然には下がりません。
移動・揺れ・停止後0.3秒は `/expression_active=true` を配信します。
活動度は固定せず、表現ノードが `/expression_joint_velocity` で伝える指令角速度を実測から差し引きます。
そのため自動動作だけを見ている間、活動度のグラフは0のままで正常です。
グリッパーなど別の関節の動きや、指令を超える動きは表現中でも活動度に現れます。
RVizで活動度を確認するときは「Plan & Execute」を使います。「Plan」だけではGazeboのアームが動かず、0のままです。
入力が1秒途切れた場合は実行中の軌道をキャンセルします。
可動域と速度上限を検査し、揺れの各サンプルをMoveItの現在の計画シーンで衝突確認します。
Gazebo専用です。MoveItサービスがない場合は動作せず待機します。
手動操作が割り込んだら停止し、眠気が一度しきい値を下回るまで再開しません。

```bash
ros2 launch ./src/arm_control/simulation/manual_activity.launch.py nod_threshold:=0.6 nod_amplitude_deg:=3.0 nod_period:=6.0
```

手動操作や活動度・眠気だけを検証する場合は `nod:=false` を指定します（起動時の待機位置への移動も無効）。
既存の `drowsiness_expression.py` は以前の肩だけの往復動作として残しています。
headlessの `activity_check.launch.py` はMoveItを起動しないため、新しい睡眠表現の検証には
MoveIt付きの `crane_x7_with_table.launch.py` を使用します。

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m unittest discover -s simulation -p 'test_*.py'
# 専用domainでMoveIt付きGazeboを起動した後、同じdomainで実行：
python3 src/arm_control/simulation/verify_sleep_expression.py --ros-args -p use_sim_time:=true
```

検証スクリプトは専用のテスト眠気入力を使います。起動時の自動表現は `nod:=false` にして、
検証中はRVizなどからアームを操作しないでください。
結果は `results/sleep_summary.json` に保存します。
2026-10-26のGazebo実測で、先端の下向きを保持し、先端高さが約0.236〜0.256 m
（取り付け面基準）の範囲で上下することと、開始姿勢への復帰を確認しました。

RViz の MotionPlanning で Planning Group を `arm` にし、
Goal State を `home` に変更（Update ボタンがあれば押す）して、
目標のアームが曲がったことを確認してから Plan & Execute を押します。
動作中は活動度が上がり、停止すると0へ戻ります。
静止中は眠気が徐々に増え、動作中は眠気の増加が緩やかになります。
外部刺激は未接続なので、活動度によって眠気が下がることはありません。
以降はRVizの先端マーカーをドラッグして目標を変え、Plan & Execute で動かします。

この起動ファイルは ROS_DOMAIN_ID=87、起動ごとに異なる GZ_PARTITION と専用ROS_HOMEを
子プロセス全体に設定します。古いGazeboが別のROS domainで残っていると、
ロボット生成要求だけが古いサーバーに届き、コントローラが起動できない場合があります。
また、コントローラ起動時のロックはROS domainをまたいで競合するため、保存先も分離しています。
別端末でトピックを見る際は `export ROS_DOMAIN_ID=87` を設定します。
終了時は起動端末で Ctrl+C を押してください。
GazeboのGUIを閉じた場合も、サーバーを含む一式を終了します。
起動中にもう一度起動すると「シミュレーションは既に起動中です」と案内して終了し、
同じROS domain内の二重起動を防ぎます。

2026-10-26に、古いGazeboサーバーが残って次回起動のコントローラー初期化が
失敗する問題を修正しました。GazeboのサーバーとGUIを別々のプロセスとして
launchから直接管理し、シェル経由の起動を廃止しています。
GUI表示が不要な確認では `gazebo_gui:=false` を指定できます。

通常のrqt_plotは起動時のトピック追加に失敗すると自動再試行しないため、
この構成では同じ描画部品を使う `activity_plot.py` を起動します。
実際の往復動作と曲線の描画画像まで確認済みです。

2026-10-19 の接続修正後、MoveIt 経由で `home` への計画・実行にも成功しました。
`/activity` は最大1、停止3秒後に約0となり、既存の rqt_plot の購読接続も確認しています。
測定結果は `results/manual_moveit_summary.json` に保存しています。
確認後の姿勢が既に `home` の場合は、次の目標に `vertical` を選ぶと変化を確認できます。

## 眠気モデル

活動度 m は `/activity` から受信します。外部刺激の入力元はまだ指定せず、
計算上は0として扱います。`/wake_stimulus` などの刺激トピックは購読しません。

```text
dS/dt = k_up * (1 - alpha * m) * (1 - S) - k_down * external_stimulus
external_stimulus = 0  # 未接続
S_next = clip(S + dS/dt * dt, 0, 1)
```

`drowsiness_node.py` は `/activity`（std_msgs/Float32）を購読し、
20 Hz のタイマーで更新した S を `/drowsiness`（std_msgs/Float32）へ配信します。
初期値は S=0、活動度の入力前は m=0です。受信した活動度は0〜1に制限します。
シミュレーションでは `use_sim_time=true` を使い、Gazeboの時間に従って積分するため、
一時停止中に眠気は進みません。ノード起動時点でシミュレーション時刻が進んでいても、
起動前の時間は積分しません。

| パラメータ | 既定値 | 意味 |
| --- | --- | --- |
| `k_up` | 0.03 | 静止時の眠気の増加速度 [1/s] |
| `alpha` | 0.8 | 活動度による増加抑制の強さ（0〜1） |
| `k_down` | 0.1 | 将来の外部刺激による覚醒の強さ [1/s]。現在は刺激0のため効果なし |
| `update_rate` | 20.0 | 更新頻度 [Hz]（起動時のみ設定可能） |

m=0では `S(t)=1-(1-S0)*exp(-0.03*t)` となり、S0=0から約30.5秒で0.6に達します。
m=1では `dS/dt=0.006*(1-S)` となり、増加速度は同じSで静止時の1/5です。
S0=0から0.6に達するまで約153秒かかります。
活動度は眠気の増加を抑える項だけに使用し、眠気を下げる項には使いません。

起動中に別端末で係数を調整できます。

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=87
ros2 param set /drowsiness_node k_up 0.03
ros2 param set /drowsiness_node alpha 0.8
ros2 param set /drowsiness_node k_down 0.1
ros2 topic echo /drowsiness --once
```

数値テストは `source /opt/ros/jazzy/setup.bash` 後に
`python3 src/arm_control/simulation/test_drowsiness.py` で実行できます。
GUIまたはheadlessのシミュレーション起動後、同じROS環境で
`python3 src/arm_control/simulation/verify_drowsiness.py --ros-args -p use_sim_time:=true` を実行すると、
30秒の静止時増加と6秒のアーム動作による増加抑制を実測します。
この検証は既定係数での実行を想定し、結果を `results/drowsiness_summary.json` に保存します。

数値テスト6項目で、静止時の増加、動作時の増加抑制、外部刺激なしでは眠気が
低下しないこと、範囲制限、パラメータ検証、シミュレーション時刻の扱いを確認します。
外部刺激未接続でのGazebo実測も成功しています。30秒静止でS=0.245→0.693、
その後の6秒の往復動作でS=0.693→0.705となりました。
同じ6秒を静止していた場合の予測値は0.744で、活動度が増加を抑えることを確認しています。
最新の描画画像は `results/drowsiness_plot_verified.png` です。

## 起動

端末1:

```bash
cd /home/kaito/4s_robodesign_jubilant
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=87
export GZ_PARTITION=crane_x7_activity_check
export ROS_LOG_DIR=/tmp/crane_x7_activity_ros_logs
ros2 launch ./src/arm_control/simulation/activity_check.launch.py
```

端末2（自動確認。肩のパン関節を +0.3 rad、元の位置へと往復させます）:

```bash
cd /home/kaito/4s_robodesign_jubilant
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=87
export ROS_LOG_DIR=/tmp/crane_x7_activity_ros_logs
python3 src/arm_control/simulation/verify_activity.py --ros-args -p use_sim_time:=true
```

スクリプトは `/robot_description` のハードウェアが
`gz_ros2_control/GazeboSimSystem` であることを確認してから動作を送ります。
起動した Gazebo 専用の ROS domain で実行してください。
通常約25秒で終了し、全チェックに成功すると終了コード0になります。
シミュレーションの処理速度によって所要時間は変わります。

値だけ見る場合は、端末2と同じ ROS 環境で次を実行します。

```bash
ros2 topic echo /joint_states --once
ros2 topic echo /activity
```

確認後は端末1で Ctrl+C を押して終了します。
図形表示と手動操作が必要な場合は、この構成を停止してから、
上記の `manual_activity.launch.py` を使用してください。

## 2026-10-19 の実測結果

ROS 2 Jazzy、既存の table world と CRANE-X7 モデルを使用。
活動度の計算処理は変更せず、既定値
`vel_threshold=0.05 rad/s`、`smoothing=0.1` で確認しました。
終了時に ROS のシグナル処理と二重 shutdown になる問題が見つかったため、
終了処理のみ `rclpy.try_shutdown()` に修正しました。

| 確認項目 | 実測結果 |
| --- | --- |
| `/joint_states` | 約200 Hz（シミュレーション時刻基準） |
| 含まれるデータ | 9関節の name / position / velocity / effort |
| 静止時の `/activity` | 0 |
| 肩パン関節の移動量 | 約0.297 rad |
| 動作時の速度ノルム最大 | 約0.102 rad/s |
| 動作時の `/activity` 最大 | 1 |
| 停止から約3秒後の `/activity` | 約0（7.34e-28） |
| 表現動作中 | 約0.297 rad 動いても活動度は一定 |
| 動作アクション | 通常動作・表現動作とも成功 |

6項目の自動チェックがすべて成功しました。
9関節にはアーム7関節とグリッパー2関節（mimic側を含む）が含まれます。
速度が実際に配信されたため、位置差分へのフォールバック経路は今回未検証です。
表現フラグを解除した直後は残留速度を拾い、一時的に活動度が上がりますが、
停止後には減衰します。

結果ファイル（再実行時に上書き）:

- `results/activity_summary.json`: 関節データ例、区間ごとの集計、成功判定。
- `results/activity_samples.csv`: 時刻、区間、速度ノルム、活動度、全関節の位置・速度・effort。
  活動度は各関節状態の受信時点で最後に受け取った値です。

初回の活動度確認では、シミュレーションの関節データから活動度を生成するところまで検証しました。
追加した眠気ノードの仕様・確認方法は上の「眠気モデル」を参照してください。
実機の通信、微小な追従動作に適したしきい値、頭下げ動作、
RealSense の視野は別途確認が必要です。
Gazebo にはグリッパーの mimic constraint 未対応の警告が出ましたが、
今回のアーム関節の動作・データ受信チェックは成功しています。
