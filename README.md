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
- `GOOGLE_SERVICE_ACCOUNT_JSON` (任意。従来方式。サービスアカウント JSON を 1 行文字列で)
- `STATE_PATH` (任意。デフォルト `./state.json`)
- `PORT` (任意。デフォルト `3000`)


## Google 認証（鍵あり/鍵なし）

このアプリは次の順で Google Sheets 認証を行います。

1. `GOOGLE_SERVICE_ACCOUNT_JSON` が設定されている場合: その JSON を利用
2. `GOOGLE_SERVICE_ACCOUNT_JSON` が未設定の場合: Application Default Credentials (ADC) を利用

JSON キー作成が組織ポリシーで禁止されている場合は、`GOOGLE_SERVICE_ACCOUNT_JSON` を設定せずに実行し、
実行環境のサービスアカウントに Sheets へのアクセス権を付与してください（鍵レス運用）。

ADC 利用時は、対象スプレッドシートを実行サービスアカウントに共有（編集者）してください。

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

1. Slack App 設定の **Event Subscriptions** を ON にする
2. **Request URL** に `https://<your-domain>/slack/events` を設定する
   - `<your-domain>` は「公開された実URLのドメイン」を入れます。
   - `study-bot` のような任意文字列はURLとして解決できないため、Slackで `not a proper link` になります。
   - 例: Cloud Run の場合 `https://<service>-<hash>-an.a.run.app/slack/events`
   - 例: ローカル確認時は `https://<ngrok-subdomain>.ngrok-free.app/slack/events` のようなHTTPS公開URLを使います。
   - URL 検証で `Verified` になる必要があります（`/slack/events` が外部から到達可能であること）。
3. **Subscribe to bot events** に以下を追加する
   - `reaction_added`
   - `reaction_removed`
   - `message.channels`

この Bot は `/slack/events` でイベントを受信し、`message.channels` はスレッド投稿の `テーマ：...` 更新に利用します。

## ローカル実行時の設定例

起動前に必須環境変数を設定してください（`GOOGLE_SERVICE_ACCOUNT_JSON` は任意）。

```bash
export SLACK_BOT_TOKEN='xoxb-...'
export SLACK_SIGNING_SECRET='...'
export SLACK_CHANNEL_ID='C0123456789'
export MEET_URL='https://meet.google.com/...'
export GOOGLE_SPREADSHEET_ID='...'
python app.py
```

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
