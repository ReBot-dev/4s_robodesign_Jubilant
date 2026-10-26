# 引き継ぎ：眠気（内部状態）と活動度の実装

## プロジェクト概要

- 授業「ロボットデザイン3」（知能コース）の CRANE-X7 プロジェクト
- ライトを持ったアームが書類を追従し、時間経過で眠気を表現し、手振りで覚醒するインタラクションシステム
- 担当範囲：インタラクション（内部状態管理・ジェスチャー認識）
- 設計方針：「状態 → パラメータ → 動作」。表現はキーフレームではなく、連続的な内部状態（眠気 S ∈ [0, 1]）からパラメトリックに生成する
- ROS ノードは機能単位で分離する（状態管理／ジェスチャー認識／動作制御）

## 環境

- Ubuntu 24.04 / ROS 2 / Python 3.12
- CRANE-X7（`crane_x7_ros`、ros2_control + Dynamixel）、MoveIt
- RealSense はアーム先端に取り付け
- 手振り検出：MediaPipe Hands（1.5 秒以内に左右切り返し 2 回以上、かつ振れ幅一定以上）＋ RealSense 深度で誤検出防止
- 注意：Ubuntu 24.04 / Python 3.12 で MediaPipe と ROS 2 の Python バインディングが衝突する可能性あり

## 今回の小ゴール

> 2026-10-26 追記：現在の睡眠表現は `sleep_expression.py`。
> 眠気0.6以上で先端を真下に向ける姿勢（肩10°・肘−120°・手首−70°）へMoveItで移動し、
> その姿勢を中心に肩±3°・6秒周期で小さく揺れる。手首を逆向きに補償するため先端の向きは下向きを保つ。
> しきい値未満で元の姿勢へ復帰。manual launchの既定動作をこの表現に変更済み。
> `simulation/verify_sleep_expression.py` と `results/sleep_summary.json` に実測・検証あり。

> 2026-10-19 追記：最新の会話で「根元側の上下関節をsin波で往復し、眠気がしきい値以上なら開始」に変更。
> `drowsiness_expression.py` に肩tiltの±5°・4秒周期を実装。しきい値は0.6。
> 手首を下げるだけという以下の旧仕様に優先する。手動launchで自動起動し、`nod:=false` で無効化できる。
> Gazebo専用。詳細と検証方法は `simulation/README.md` を参照。

1. アームが動いているときは眠気を増えにくくする
2. 内部状態（眠気 S）から「うとうと」させる

「うとうと」は **頭（手首ピッチ）が下がるだけ** の動作。船漕ぎなどは不要。
動作量は **ざっくり動いているかどうか** が分かれば十分。

## 眠気モデル

```
dS/dt = k_up · (1 − α·m) · (1 − S)  −  k_down · 外部刺激
```

| 記号 | 意味 | 初期値 |
|---|---|---|
| S | 眠気 (0〜1) | 0 |
| k_up | 眠くなる基本速度 [1/s] | 0.03 |
| α | 動作による眠気抑制の強さ (0〜1) | 0.8 |
| m | アーム活動度 (0〜1)、`/activity` | — |
| k_down | 将来の外部刺激による覚醒の強さ [1/s] | 0.1（外部刺激が未接続のため現在は効果なし） |
| 外部刺激 | 入力元は未指定 | 0（未接続） |

- 最新のユーザー指定により、mは活動度、外部刺激の入力元は未指定とする。
  現在は外部刺激=0として計算し、刺激トピックは購読しない。
- 項の役割：k_up＝基本速度、(1 − α·m)＝動作ブレーキ、(1 − S)＝上限で飽和、k_down·外部刺激＝将来の覚醒
- 外部刺激なし・一定mでの解析解：`S(t) = 1 − (1 − S0)·exp(−k_up·(1 − α·m)·t)`
- 目標：静止から約 30 秒で頭を下げ始める → しきい値 S_th = 0.6 として `k_up = −ln(0.4)/30 ≈ 0.03`
  - 動作中（m=1）は `dS/dt=0.006*(1-S)` となり、増加速度が1/5になる。
    S=0から0.6までは約153秒。活動度では眠気を下げない。
- 実装はオイラー法。**更新後に S を [0, 1] にクリップする**（覚醒項にストッパーがないため）

```python
external_stimulus = 0.0  # 入力元は未指定
dS = k_up * (1 - alpha * m) * (1 - S) - k_down * external_stimulus
S = min(max(S + dS * dt, 0.0), 1.0)
```

- 状態切り替えはヒステリシスで安定化する方針（例：S > 0.6 で下げ始め、S < 0.4 で戻す。値は要調整）

## ノード構成

```
/joint_states ──▶ [activity_monitor] ──/activity──▶ [drowsiness_node] ──/drowsiness──▶ [表現ノード]
                         ▲                                                               │
                         └──────────────── /expression_active ───────────────────────────┘
```

| トピック                 | 型                      | 内容                 |
| -------------------- | ---------------------- | ------------------ |
| `/joint_states`      | sensor_msgs/JointState | CRANE-X7 の関節状態     |
| `/activity`          | std_msgs/Float32       | 活動度 m (0〜1)        |
| `/expression_active` | std_msgs/Bool          | 表現動作（頭を下げる）中は True |
| `/drowsiness`        | std_msgs/Float32       | 眠気 S (0〜1)         |

### 設計上の注意：表現動作で自分を起こすループ

頭を下げる動作も `/joint_states` に速度として出るため、そのままだと
「頭が下がる → 動いていると判定 → 眠気が増えにくくなる」というループが起きる。
対策として、表現ノードは表現動作中に `/expression_active = True` を出し、
`activity_monitor` はその間 m を更新しない（機能動作だけを活動度として数える）。

## 実装状況

### 完了：`activity_monitor.py`

- `/joint_states` の角速度ノルムをしきい値判定 → ローパスで 0〜1 の活動度にして `/activity` に publish
- `velocity` が空なら `position` の差分から角速度を計算
- `/expression_active` が True の間は活動度を凍結
- パラメータ：`vel_threshold`（既定 0.05 rad/s）、`smoothing`（既定 0.1）
- 2026-10-19 に Gazebo で検証済み。静止時0、動作時1、停止後ほぼ0、表現動作中の凍結を確認。
- 再実行手順：`simulation/README.md`。測定結果：`simulation/results/activity_summary.json` と `activity_samples.csv`。
- `/joint_states` は約200 Hz（シミュレーション時刻基準）。9関節の位置・速度・effort を取得できた。
- 既定しきい値0.05 rad/sで約0.1 rad/sの肩パン動作を検出。実機・微小追従動作・位置差分経路は未検証。
- Ctrl+C終了時の二重shutdownエラーを避けるため、終了処理を `rclpy.try_shutdown()` に修正。
- 手動確認は `ros2 launch ./src/arm_control/simulation/manual_activity.launch.py` でGUI・活動度・グラフを一括起動。
  古いGazeboとROS domainが混在するとデータが来ないため、専用GZ_PARTITIONとROS_HOMEも設定して起動する。
- GUI構成でもMoveIt経由のhome姿勢への実行と活動度0→1→ほぼ0を確認済み。
  結果：`simulation/results/manual_moveit_summary.json`。
- グラフは `simulation/activity_plot.py` でトピック接続を再試行し、現在値・受信数も表示する。
  起動直後のrqt_plot未購読とシミュレーション重複による停止を修正。手動launchは二重起動を防止する。

### 完了：`drowsiness_node.py`

- `/activity` を式中の m に使用し、20 Hz のタイマーでオイラー積分する。
- 外部刺激は未接続の0。活動度は増加抑制だけに使い、眠気を下げる項には使わない。
- `/drowsiness`（std_msgs/Float32）に0〜1の眠気度を配信する。初期値0。
- パラメータ：`k_up=0.03`、`alpha=0.8`、`k_down=0.1`、`update_rate=20.0`。
  係数は実行中に変更可能、update_rateは起動時のみ。
- シミュレーションの時刻を使用し、初回受信時の大きなdtと時刻巻き戻りを考慮する。
- 手動・headless両launchに組み込み済み。グラフに活動度・眠気度の2本を表示する。
- 数値テスト：`python3 src/arm_control/simulation/test_drowsiness.py`（6項目）。
- 外部刺激未接続のGazebo実測済み：30秒静止でS=0.245→0.693、6秒の動作で
  S=0.693→0.705（同時間を静止する場合の予測0.744）。眠気を下げず増加だけを抑える。
  結果：`simulation/results/drowsiness_summary.json`。

## 次のタスク

1. **`activity_monitor` の動作確認**
   - Gazeboでの基本確認は完了（2026-10-19、6項目成功）。
   - 追従中の小刻みな動きを拾えるよう `vel_threshold` を調整
   - パッケージ化（setup.py の entry_points 登録）
2. **`drowsiness_node` の係数調整**
   - 実装済み。活動度による増加抑制と、静止時の眠気増加速度を調整する。
3. **表現ノード（頭を下げる）**
   - S に比例して手首ピッチを下げる（ゆっくり動かす）
   - 動作中は `/expression_active` を True にする
4. **カメラ視野の確認**
   - RealSense がアーム先端にあるため、頭を下げるとカメラも下を向く
   - 頭を下げた状態でも手振りが視野に入るよう、下げる角度の上限を実測して決める

## 未決事項

- 外部刺激の入力元とk_downの最終調整値（現在は刺激未接続、係数0.1）。
- ヒステリシスのしきい値
- 頭を下げる角度の上限（カメラ視野の確認結果次第）
