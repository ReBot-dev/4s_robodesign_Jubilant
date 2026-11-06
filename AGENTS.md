# チームリポジトリの作業案内

このリポジトリは ROS 2 Jazzy を使用するチーム Jubilant のプロジェクトです。
全体の構成・分担は `README.md` を参照してください。

## 作業前に確認すること

- 現在のブランチと未コミット変更を確認し、既存の変更を保持する。
- `main` へ直接コミットせず、作業用ブランチを使用する。
- 作業対象の機能に関係する資料を読み、設計案・過去の記録・現行実装を区別する。
- 担当機能の範囲を意識し、他の班のコードを変更する場合は理由を説明する。

## CRANE-X7・活動度・眠気・インタラクションの作業

リポジトリのルートから作業する場合も、開始時に次を読むこと。

1. `src/arm_control/AGENTS.md` — 進め方と確認コマンド
2. `src/arm_control/AGENT.md` — 目標、実装、ユーザーと合意した進め方
3. `src/arm_control/HANDOFF_drowsiness.md` — 引き継ぎと未確認事項
4. `src/arm_control/README.md` — 移行後のセットアップと起動方法

自作コードとシミュレーションは `src/arm_control/`、依存コードは
`src/crane_x7_ros/` と `src/crane_x7_description/` にある。
依存コードを変更するときは `src/arm_control/THIRD_PARTY.md` も確認する。
元の `/home/kaito/ros2_ws` は移行元の控え。今後のこのリポジトリでの作業・起動・ビルドはここを基準にする。

`build/`、`install/`、`log/`、`__pycache__/`、生成された検証結果や認証情報をコミットしない。
