# study-group-bot

要件定義書 (`requirements.md`) をもとに作成した Slack 勉強会運用 Bot です。  
Slack 上のリアクションとスレッド返信を Google スプレッドシートへ反映します。

## 実装済み機能（MVP）

- 月水金 9:00 に参加宣言メッセージを `#attendance` に投稿
- ✅/💻/💤 の最後のリアクションを参加形態として `出席管理` シートへ反映
- 🎤 の先着 2 名を発表者として判定し `発表の有無` を更新
- 🎤 取り消しで繰り上げ再計算
- 発表者のみ `テーマ：...` のスレッド返信で `発表テーマ` を更新（最新上書き）
- 月水金 15:00 に一次確定サマリを投稿
- 月水金 17:00 に `@channel` 付き開始通知を投稿

## 必要な環境変数

- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `SLACK_CHANNEL_ID` (`#attendance` のチャンネルID)
- `MEET_URL` (固定 Meet URL)
- `GOOGLE_SPREADSHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (サービスアカウント JSON を 1 行文字列で)
- `STATE_PATH` (任意。デフォルト `./state.json`)
- `PORT` (任意。デフォルト `3000`)

## Google スプレッドシート

- ワークシート名: `出席管理`
- ヘッダ（固定）:
  - 日付
  - 参加者
  - 対面/オンライン
  - 発表の有無
  - 発表テーマ

初回起動時に `出席管理` がなければ自動作成します。

## Slack アプリ設定

### OAuth Scopes (Bot Token)

- `chat:write`
- `channels:history`
- `channels:read`
- `reactions:read`
- `users:read`

### Event Subscriptions

Request URL: `https://<your-domain>/slack/events`

Subscribe to bot events:
- `reaction_added`
- `reaction_removed`
- `message.channels`

## 起動

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

ヘルスチェック:

```bash
curl http://localhost:3000/healthz
```
