# Slack 連携・アプリ追加手順（詳細版）

このドキュメントは、`study-group-bot` を Slack ワークスペースで実運用するための
「Slack App 作成〜Event Subscriptions 検証〜運用開始」までを詳細に説明します。

---

## 1. 事前に準備するもの

- Render などで公開済みのアプリ URL
  - 例:`https://<project-name>.onrender.com`
- Slack ワークスペースの管理権限（アプリをインストールできる権限）
- 本アプリの環境変数
  - `SLACK_BOT_TOKEN`（後で取得）
  - `SLACK_SIGNING_SECRET`（後で取得）
  - `SLACK_CHANNEL_ID`

> 重要: `SLACK_CHANNEL_ID` は **チャンネル名ではなく ID** を設定してください。

---

## 2. Slack App を作成する

1. [Slack API: Your Apps](https://api.slack.com/apps) を開く
2. `Create New App` を押す
3. `From scratch` を選ぶ
4. App Name を入力
5. 対象ワークスペースを選択
6. `Create App`

---

## 3. OAuth Scopes を設定する

1. 左メニュー `OAuth & Permissions` を開く
2. `Bot Token Scopes` に次を追加
   - `chat:write`
   - `channels:history`
   - `channels:read`
   - `reactions:read`
   - `users:read`

### Scope の用途

- `chat:write`: Bot 投稿
- `channels:history`: チャンネルメッセージ受信
- `channels:read`: チャンネル情報参照
- `reactions:read`: リアクションイベント処理
- `users:read`: ユーザー表示名解決

---

## 4. ワークスペースへインストールする

1. `OAuth & Permissions` 画面で `Install to Workspace`
2. 権限確認画面で許可
3. インストール後に表示される
   - `Bot User OAuth Token`（`xoxb-...`）を控える

これを `SLACK_BOT_TOKEN` に設定します。

---

## 5. Signing Secret を取得する

1. 左メニュー `Basic Information`
2. `App Credentials` の `Signing Secret` を表示
3. 値を控える

これを `SLACK_SIGNING_SECRET` に設定します。

---

## 6. Event Subscriptions を有効化する

1. 左メニュー `Event Subscriptions`
2. `Enable Events` を ON
3. `Request URL` に次を設定
   - `https://<公開URL>/slack/events`

`Verified` になることを確認してください。

### `Verified` にならないときの確認

- URL が `https` か
- `/slack/events` を付けているか
- アプリが起動しているか (`/healthz` が200か)
- Render 側の環境変数が不足していないか

---

## 7. Subscribe to bot events を追加する

`Event Subscriptions` の `Subscribe to bot events` で以下を追加:

- `reaction_added`
- `reaction_removed`
- `message.channels`

保存後、必要に応じて再インストールを求められたら再インストールしてください。

---

## 8. チャンネルへ Bot を追加する

Slack の `#attendance` で:

```text
/invite @study-group-bot
```

Bot が参加していないとイベントを受信できない場合があります。

---

## 9. 環境変数を本番に設定する

最低限必要:

- `SLACK_BOT_TOKEN=xoxb-...`
- `SLACK_SIGNING_SECRET=...`
- `SLACK_CHANNEL_ID=...`
- `MEET_URL=...`
- `GOOGLE_SPREADSHEET_ID=...`

任意:

- `GOOGLE_SERVICE_ACCOUNT_JSON=...`
- `STATE_PATH=/tmp/state.json`

---

## 10. 動作確認（最短）

### 10-1. ヘルス確認

```bash
curl -i https://<公開URL>/healthz
```

- `200 ok` なら起動成功

### 10-2. 手動投稿トリガー

`#attendance` で次を投稿:

```text
参加宣言投稿
```

期待動作:

- Bot が参加宣言メッセージを投稿
- 「参加宣言投稿を実行しました。」が返る

### 10-3. リアクション処理確認

Bot 投稿に対して:

- `✅`（対面）
- `💻`（オンライン）
- `💤`（欠席）
- `🎤`（発表希望）

発表者はスレッドで:

```text
テーマ：〇〇
```

---

## 11. よくある失敗と対処

### A. `invalid_auth`

- `SLACK_BOT_TOKEN` が無効（`xoxb` でない / 古い）
- 再インストール後の最新 token を設定し直す

### B. `Your URL didn't respond with challenge`

- Request URL が誤り（`/slack/events` なし等）
- アプリが落ちている / 500, 503 を返している

### C. `#attendance` に投稿しても反応しない

- `message.channels` 未購読
- Bot 未招待
- `SLACK_CHANNEL_ID` が誤り（名前ではなくID）

### D. Google Sheets に反映されない

- `GOOGLE_SERVICE_ACCOUNT_JSON` 未設定か不正
- もしくは ADC 未設定
- 対象シートをサービスアカウントに共有していない

---

## 12. 運用チェックリスト

- [ ] `/healthz` が 200
- [ ] Event Subscriptions が Verified
- [ ] Bot Scopes が必要分揃っている
- [ ] Bot が `#attendance` に参加済み
- [ ] `参加宣言投稿` で即時投稿できる
- [ ] リアクション・テーマ更新が動く
- [ ] （必要なら）Google Sheets 反映が動く

