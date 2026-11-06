# CRANE-X7 依存コードの取得元

2026-10-26 に `/home/kaito/ros2_ws` から移行しました。
依存コードは通常のファイルとして同梱し、各ディレクトリの LICENSE と著作権表示を保持しています。
チームのルート LICENSE とは別に、それぞれの利用条件が適用されます。

| ディレクトリ（リポジトリルート基準） | 取得元 | ベースコミット | ライセンス |
| --- | --- | --- | --- |
| `src/crane_x7_ros` | https://github.com/rt-net/crane_x7_ros | `3761ab179dbcbd7432b28968340e2225978006de` | Apache License 2.0（同梱LICENSE参照） |
| `src/crane_x7_description` | https://github.com/rt-net/crane_x7_description | `61865950f741f0d5a35e28eb0a7d2501cac86e7b` | RT Corporation 非商用使用許諾規約（同梱LICENSE参照） |

## ベースコミットからのローカル修正

`src/crane_x7_ros/crane_x7_control/launch/crane_x7_control.launch.py`:
`control_update_rate`引数を追加し、controller_managerの周期を起動時に上書き可能にした。
標準値200 Hzは維持する。実機用`hardware_activity.launch.py`では50 Hzを指定する。
2026-11-02の実機ログで読み取りが約11〜16 msかかり、200 Hzの5 ms周期を超過していたため。
コントローラの関節・インターフェースや実機ドライバのC++コードは変更していない。

`src/crane_x7_ros/crane_x7_gazebo/launch/crane_x7_with_table.launch.py`:
Gazebo のサーバーとGUIを別プロセスとしてlaunchから管理し、シェル経由の起動を廃止。
どちらかの終了時にlaunch全体を終了し、サーバーが残る問題を修正。
`gazebo_gui` 引数でGUI表示を切り替え可能にしました。

`crane_x7_description` にローカル修正はありません。
