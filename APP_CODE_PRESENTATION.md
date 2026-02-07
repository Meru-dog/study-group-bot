# app.py コード解説 発表資料

この資料は、`app.py` の実装を発表用に説明するためのドキュメントです。  
（全体の流れは `IMPLEMENTATION_STEPS.md`、Slack 連携手順は `SLACK_SETUP_DETAILED.md` を参照）

---

## 1. 発表のゴール

- `app.py` が **何を責務として持つか**を理解する
- イベント駆動（Slack）とバッチ駆動（Scheduler）の流れを理解する
- Google Sheets 連携の設計（通常 / フォールバック）を説明できるようになる

---

## 2. 全体アーキテクチャ（1枚で説明）

`app.py` は以下のレイヤで構成されます。

1. **設定層**: `Settings`（環境変数）
2. **状態層**: `LocalState`（宣言投稿ts・発表希望状態の保持）
3. **永続層**: `SheetRepository` / `NoopSheetRepository`
4. **業務ロジック層**: `StudyGroupBot`
5. **公開層**: Flask エンドポイント（`/slack/events`, `/healthz`）

ポイント:
- Slackイベントは `StudyGroupBot` で処理
- 定時実行も `StudyGroupBot` が管理
- Web公開は Flask 側が担当

---

## 3. 定数・設定（Config）

### 3-1. 主要定数

- 参加区分絵文字マッピング
- 発表者絵文字（🎤）
- テーマプレフィックス（`テーマ：`）
- 日付フォーマット
- 手動トリガーコマンド（`参加宣言投稿`）

### 3-2. `Settings.from_env()`

- 必須環境変数:
  - `SLACK_BOT_TOKEN`
  - `SLACK_SIGNING_SECRET`
  - `SLACK_CHANNEL_ID`
  - `MEET_URL`
  - `GOOGLE_SPREADSHEET_ID`
- 未設定時は明確にエラーを出す

発表での要点:
- **「起動時に fail-fast する設計」**
- ただし Flask 側で graceful に受ける導線も用意

---

## 4. `LocalState`（ローカル状態管理）

### 役割

- 宣言投稿メッセージ（channel/ts）を日付キーで管理
- 発表希望（🎤）の押下/解除を管理
- 先着2名ロジックの基礎データを保持

### 実装ポイント

- `threading.Lock` で排他
- JSON ファイルへ永続化
- `event_ts` で時系列ソートし先着順を確定

発表での要点:
- DB を使わない MVP における「最小構成の状態管理」

---

## 5. Google Sheets 層

## 5-1. `SheetRepository`

### 認証フロー

1. `GOOGLE_SERVICE_ACCOUNT_JSON` があればそれを使用
2. なければ ADC を試行

### 主な操作

- ヘッダ検証 (`_ensure_headers`)
- 日付+参加者で行検索 (`_find_row`)
- 参加情報 upsert
- 発表フラグ更新
- テーマ更新

## 5-2. `NoopSheetRepository`

- 認証不可時のフォールバック
- 書き込み処理はスキップ（warning ログ）
- 読み込みは空配列

発表での要点:
- **可用性優先**: Sheets が死んでも bot 本体は止めない

---

## 6. `StudyGroupBot`（中核ロジック）

### 6-1. 初期化

- Slack Bolt App 構築
- SlackRequestHandler 準備
- `LocalState` / `SheetRepository(or Noop)` 準備
- ハンドラ登録
- Scheduler 登録

### 6-2. 定時ジョブ

- Mon/Wed/Fri 09:00: 参加宣言投稿
- Mon/Wed/Fri 15:00: 一次確定サマリ
- Mon/Wed/Fri 17:00: 開始通知

### 6-3. 手動投稿

- `参加宣言投稿` メッセージで宣言投稿を即時実行

発表での要点:
- 「運用時は定時、検証時は手動」両対応

---

## 7. イベント処理詳細

### 7-1. `reaction_added` / `reaction_removed`

- 対象が当日の宣言投稿かチェック
- 参加リアクション（✅/💻/💤）で参加区分更新
- 🎤 の追加/解除で発表者再計算

### 7-2. `message` イベント

- 手動コマンドを判定
- スレッド投稿（`テーマ：`）を判定
- 発表者本人のテーマのみ更新

発表での要点:
- **対象メッセージの厳密一致（channel+ts）** で誤更新を防いでいる

---

## 8. 投稿メッセージ系ロジック

### 8-1. 参加宣言投稿

- 参加方法・発表希望・テーマ入力ルールをまとめて案内
- 投稿 ts を保存し、その後のイベントをこの投稿に紐づける

### 8-2. 15:00 サマリ

- 対面/オンライン/欠席を集計
- 発表者一覧を出力

### 8-3. 17:00 開始通知

- `@channel` 付きで開始通知
- 当日の発表者・テーマを再掲

---

## 9. Flask 公開層

### 9-1. `create_flask_app()`

- `Settings` の読み込みを try/except
- `StudyGroupBot` 初期化も try/except
- 失敗時も HTTP を返せるよう fallback endpoint を作る

### 9-2. エンドポイント

- `POST /slack/events`: Slack リクエストを Bolt に委譲
- `GET /healthz`: 稼働確認

### 9-3. エントリポイント

- `app = create_flask_app()` を公開
- buildpack/gunicorn の既定解決 (`app:app`) に対応

発表での要点:
- **起動失敗を「見える化」する設計**（500/503で原因確認）

---

## 10. つまずきポイントと設計上の対策

1. **Slack token 不正 (`invalid_auth`)**
   - 起動時に検出し、ログで原因を明示
2. **Google 認証情報不足**
   - `NoopSheetRepository` にフォールバック
3. **Event URL 検証失敗**
   - `/slack/events` を必須化
4. **チャンネル指定ミス**
   - `SLACK_CHANNEL_ID` は `C...` 前提へ単純化

---

## 11. デモシナリオ（発表用）

1. `#attendance` で `参加宣言投稿`
2. bot が宣言投稿
3. 参加者が ✅ / 💻 / 💤 を押す
4. 発表希望者が 🎤 を押す（先着2名）
5. 発表者がスレッドで `テーマ：...`
6. シート更新（または Noop 時はログ確認）

---

## 12. 今後の改善候補（発表締め）

- 単体テスト追加（特にイベントハンドラ）
- 永続層を DB 化（state.json から移行）
- 権限不足時の管理画面通知
- 監視（Sentry/Cloud Loggingアラート）
- マルチチャンネル対応

---

## 13. 1分まとめ

- `app.py` は「Slackイベント処理」「定時投稿」「Sheets連携」「運用時の耐障害性」を1つにまとめた中核実装。
- MVP でも運用に耐えるよう、起動失敗時のフォールバックとログ重視で設計。
- 今後はテスト整備と永続化強化で安定性をさらに高められる。

