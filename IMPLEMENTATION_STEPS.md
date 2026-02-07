# study-group-bot 実装・導入ログ（段階別）

このドキュメントは README とは別に、今回の Slack 勉強会 Bot 実装〜運用開始までを段階ごとに整理した記録です。

## 0. 目的

- 勉強会の参加宣言・発表者管理を Slack で完結させる。
- 参加情報を Google スプレッドシートへ記録する。
- 定時投稿（9:00 / 15:00 / 17:00）を自動化する。

---

## 1. アプリ本体（MVP）実装

### 1-1. 基本構成

- `app.py` に Flask + Slack Bolt ベースのアプリを実装。
- エンドポイント:
  - `POST /slack/events`（Slack Events 受信）
  - `GET /healthz`（ヘルスチェック）

### 1-2. Slackイベント処理

- リアクション:
  - `✅` → 対面
  - `💻` → オンライン
  - `💤` → 欠席
  - `🎤` → 発表希望（先着2名）
- スレッド投稿:
  - `テーマ：...` 形式を発表テーマとして更新

### 1-3. スケジュール処理

- APScheduler で月・水・金に定時実行:
  - 09:00 参加宣言投稿
  - 15:00 一次確定サマリ
  - 17:00 開始通知

### 1-4. 永続化

- `state.json` で宣言投稿 ts / 発表希望状態を保持。
- Google Sheets `出席管理` シートへ upsert 更新。

---

## 2. Google 認証方式の拡張

### 2-1. 鍵あり/鍵なし両対応

- `GOOGLE_SERVICE_ACCOUNT_JSON` がある場合は JSON 認証。
- 未設定の場合は ADC（Application Default Credentials）で認証。

### 2-2. 組織ポリシーで鍵作成禁止の場合の対応

- `iam.disableServiceAccountKeyCreation`（legacy）や managed 制約の影響で JSON 作成不可なケースを想定。
- 鍵が作れない環境でも起動できるよう運用パスを用意。

---

## 3. 起動失敗時の改善

### 3-1. 必須環境変数エラーの明確化

- 起動時に不足 env を列挙してエラー化。
- 何が足りないか一目で分かるよう改善。

### 3-2. クラッシュ回避

- 初期化失敗時でも Flask が即死しないようにし、
  - `/healthz` は `500`
  - `/slack/events` は `503`
 で原因メッセージを返すフェイルセーフを追加。

### 3-3. Cloud Run / Gunicorn 対応

- `app = create_flask_app()` を公開し、`app:app` 解決失敗を回避。

---

## 4. Render 運用時の対応

### 4-1. Google 認証無しでも起動可能に

- `NoopSheetRepository` を追加。
- Google 認証が無い場合はシート書き込みをスキップして起動継続。

### 4-2. 運用上の意味

- Slack 側の動作確認・運用は先行可能。
- ただしスプレッドシート反映を有効化するには、JSON または ADC の正しい設定が必要。

---

## 5. 手動テスト導線の追加

### 5-1. 即時投稿コマンド

- `#attendance` に `参加宣言投稿` を送ると、
  定時を待たずに宣言投稿を実行できるように実装。

### 5-2. 期待結果

- Bot が宣言メッセージを投稿。
- その投稿に対するリアクション・スレッド返信が処理される。

---

## 6. チャンネルID運用の整理

### 6-1. 設定値の確定

- `SLACK_CHANNEL_ID` は実チャンネルIDを使用。

### 6-2. コード簡素化

- `#attendance` 名称探索ロジックを削除。
- 余分な分岐を減らし、IDベースで確実に判定・投稿。

---

## 7. デプロイ・運用時の主要確認ポイント

1. Slack App
   - Bot Scopes 設定
   - Event Subscriptions 有効化
   - Request URL 検証成功
2. Render / Cloud Run
   - `SLACK_BOT_TOKEN` が有効（`xoxb-...`）
   - `SLACK_SIGNING_SECRET` 正常
   - `SLACK_CHANNEL_ID` が正しいチャンネルID
3. Google Sheets
   - 認証方式（JSON/ADC/Noop）を運用方針に合わせて選択

---

## 8. 現在の実装状態（要約）

- Slackイベント受信・定時投稿・手動投稿トリガーを実装済み。
- Google認証は JSON/ADC をサポート。
- 認証不可時は Noop で起動継続可能。
- 運用上のボトルネックは主に「Slackトークン値」「Google鍵ポリシー」「環境変数整合」。

