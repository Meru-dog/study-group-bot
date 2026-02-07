import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gspread
import google.auth
from google.auth.exceptions import DefaultCredentialsError
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Response, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ATTENDANCE_EMOJIS = {"white_check_mark": "対面", "computer": "オンライン", "zzz": "欠席"}
SPEAKER_EMOJI = "microphone"
TOPIC_PREFIX = "テーマ："
DATE_FORMAT = "%Y/%m/%d"


@dataclass
class Settings:
    slack_bot_token: str
    slack_signing_secret: str
    slack_channel_id: str
    meet_url: str
    google_spreadsheet_id: str
    google_service_account_json: Optional[str]
    state_path: Path

    @staticmethod
    def from_env() -> "Settings":
        required_keys = [
            "SLACK_BOT_TOKEN",
            "SLACK_SIGNING_SECRET",
            "SLACK_CHANNEL_ID",
            "MEET_URL",
            "GOOGLE_SPREADSHEET_ID",
        ]
        missing = [key for key in required_keys if not os.environ.get(key)]
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(
                "Missing required environment variables: "
                f"{joined}. Please set them before starting the app."
            )

        return Settings(
            slack_bot_token=os.environ["SLACK_BOT_TOKEN"],
            slack_signing_secret=os.environ["SLACK_SIGNING_SECRET"],
            slack_channel_id=os.environ["SLACK_CHANNEL_ID"],
            meet_url=os.environ["MEET_URL"],
            google_spreadsheet_id=os.environ["GOOGLE_SPREADSHEET_ID"],
            google_service_account_json=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"),
            state_path=Path(os.environ.get("STATE_PATH", "./state.json")),
        )


class LocalState:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.state = {"declaration_messages": {}, "speaker_requests": {}}
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self):
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_declaration_message(self, date_key: str, channel: str, ts: str):
        with self.lock:
            self.state["declaration_messages"][date_key] = {"channel": channel, "ts": ts}
            self.save()

    def get_declaration_message(self, date_key: str) -> Optional[Dict[str, str]]:
        with self.lock:
            return self.state["declaration_messages"].get(date_key)

    def add_speaker_request(self, date_key: str, user_id: str, event_ts: str):
        with self.lock:
            day = self.state["speaker_requests"].setdefault(date_key, {})
            day[user_id] = {"active": True, "requested_at": event_ts}
            self.save()

    def remove_speaker_request(self, date_key: str, user_id: str):
        with self.lock:
            day = self.state["speaker_requests"].setdefault(date_key, {})
            if user_id in day:
                day[user_id]["active"] = False
            self.save()

    def get_speakers(self, date_key: str) -> List[str]:
        with self.lock:
            day = self.state["speaker_requests"].get(date_key, {})
            active = [
                (uid, info["requested_at"]) for uid, info in day.items() if info.get("active")
            ]
            active.sort(key=lambda x: float(x[1]))
            return [uid for uid, _ in active[:2]]


class SheetRepository:
    HEADERS = ["日付", "参加者", "対面/オンライン", "発表の有無", "発表テーマ"]
    SHEETS_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self, settings: Settings):
        try:
            if settings.google_service_account_json:
                creds = json.loads(settings.google_service_account_json)
                gc = gspread.service_account_from_dict(creds)
                logger.info("Using GOOGLE_SERVICE_ACCOUNT_JSON for Google Sheets authentication")
            else:
                credentials, _ = google.auth.default(scopes=self.SHEETS_SCOPES)
                gc = gspread.authorize(credentials)
                logger.info("Using Application Default Credentials for Google Sheets authentication")
        except DefaultCredentialsError as exc:
            raise RuntimeError(
                "Google credentials not found. Set GOOGLE_SERVICE_ACCOUNT_JSON on Render "
                "or configure GOOGLE_APPLICATION_CREDENTIALS/ADC in the runtime environment."
            ) from exc

        self.sheet = gc.open_by_key(settings.google_spreadsheet_id)
        try:
            self.ws = self.sheet.worksheet("出席管理")
        except gspread.WorksheetNotFound:
            self.ws = self.sheet.add_worksheet(title="出席管理", rows=2000, cols=10)
            self.ws.append_row(self.HEADERS)

    def _ensure_headers(self):
        first = self.ws.row_values(1)
        if first != self.HEADERS:
            self.ws.clear()
            self.ws.append_row(self.HEADERS)

    def _find_row(self, date_key: str, participant: str) -> Optional[int]:
        records = self.ws.get_all_records()
        for idx, rec in enumerate(records, start=2):
            if rec["日付"] == date_key and rec["参加者"] == participant:
                return idx
        return None

    def upsert_attendance(self, date_key: str, participant: str, attendance: str):
        self._ensure_headers()
        row = self._find_row(date_key, participant)
        if row:
            self.ws.update(f"C{row}", [[attendance]])
        else:
            self.ws.append_row([date_key, participant, attendance, "", ""])

    def update_speaker_flags(self, date_key: str, speaker_names: List[str]):
        records = self.ws.get_all_records()
        updates: List[Tuple[int, str]] = []
        for idx, rec in enumerate(records, start=2):
            if rec["日付"] != date_key:
                continue
            value = "○" if rec["参加者"] in speaker_names else ""
            updates.append((idx, value))
        for idx, value in updates:
            self.ws.update(f"D{idx}", [[value]])

    def update_topic(self, date_key: str, participant: str, topic: str):
        row = self._find_row(date_key, participant)
        if row:
            self.ws.update(f"E{row}", [[topic]])

    def get_day_records(self, date_key: str) -> List[Dict[str, str]]:
        return [r for r in self.ws.get_all_records() if r["日付"] == date_key]


class StudyGroupBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.app = App(token=settings.slack_bot_token, signing_secret=settings.slack_signing_secret)
        self.handler = SlackRequestHandler(self.app)
        self.state = LocalState(settings.state_path)
        self.repo = SheetRepository(settings)
        self.user_name_cache: Dict[str, str] = {}
        self._register_handlers()
        self.scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
        self._register_jobs()

    def _today(self) -> str:
        return datetime.now().strftime(DATE_FORMAT)

    def _register_jobs(self):
        self.scheduler.add_job(self.post_declaration_message, "cron", day_of_week="mon,wed,fri", hour=9, minute=0)
        self.scheduler.add_job(self.post_summary_message, "cron", day_of_week="mon,wed,fri", hour=15, minute=0)
        self.scheduler.add_job(self.post_start_message, "cron", day_of_week="mon,wed,fri", hour=17, minute=0)

    def start(self):
        self.scheduler.start()

    def _display_name(self, user_id: str) -> str:
        if user_id in self.user_name_cache:
            return self.user_name_cache[user_id]
        info = self.app.client.users_info(user=user_id)
        profile = info["user"]
        name = profile.get("profile", {}).get("display_name") or profile.get("real_name") or user_id
        self.user_name_cache[user_id] = name
        return name

    def post_declaration_message(self):
        date_key = self._today()
        text = (
            "【本日 勉強会】参加宣言（締切15:00）\n"
            "本日 17:00–19:00 勉強会（渋谷＋Meet）です。\n"
            "15:00までにこの投稿にリアクションで参加宣言してください：\n"
            "✅ 対面（渋谷）\n"
            "💻 オンライン（Meet）\n"
            "💤 欠席\n"
            "発表したい人は 🎤 を追加で押してください（先着2名／取り消しは🎤を外す）\n"
            "発表者はスレッドに `テーマ：〇〇` と返信してください（後で変更OK）\n"
            f"Meet：{self.settings.meet_url}"
        )
        resp = self.app.client.chat_postMessage(channel=self.settings.slack_channel_id, text=text)
        self.state.set_declaration_message(date_key, self.settings.slack_channel_id, resp["ts"])
        logger.info("Declaration message posted for %s", date_key)

    def _register_handlers(self):
        @self.app.event("reaction_added")
        def on_reaction_added(event, logger):
            self._handle_reaction(event, added=True)
            logger.info("processed reaction_added")

        @self.app.event("reaction_removed")
        def on_reaction_removed(event, logger):
            self._handle_reaction(event, added=False)
            logger.info("processed reaction_removed")

        @self.app.event("message")
        def on_message(event, logger):
            self._handle_thread_message(event)
            logger.info("processed message event")

    def _is_target_message(self, date_key: str, channel: str, ts: str) -> bool:
        msg = self.state.get_declaration_message(date_key)
        return bool(msg and msg["channel"] == channel and msg["ts"] == ts)

    def _handle_reaction(self, event: Dict, added: bool):
        date_key = self._today()
        item = event.get("item", {})
        if item.get("type") != "message":
            return
        if not self._is_target_message(date_key, item.get("channel"), item.get("ts")):
            return

        user_id = event["user"]
        user_name = self._display_name(user_id)
        reaction = event["reaction"]

        if reaction in ATTENDANCE_EMOJIS and added:
            self.repo.upsert_attendance(date_key, user_name, ATTENDANCE_EMOJIS[reaction])
            self._refresh_speaker_flags(date_key)

        if reaction == SPEAKER_EMOJI:
            if added:
                self.state.add_speaker_request(date_key, user_id, event["event_ts"])
            else:
                self.state.remove_speaker_request(date_key, user_id)
            self._refresh_speaker_flags(date_key)

    def _refresh_speaker_flags(self, date_key: str):
        speaker_ids = self.state.get_speakers(date_key)
        speaker_names = [self._display_name(uid) for uid in speaker_ids]
        self.repo.update_speaker_flags(date_key, speaker_names)

    def _handle_thread_message(self, event: Dict):
        if event.get("subtype") is not None:
            return
        date_key = self._today()
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return
        declaration = self.state.get_declaration_message(date_key)
        if not declaration or declaration["ts"] != thread_ts:
            return

        text = event.get("text", "")
        if not text.startswith(TOPIC_PREFIX):
            return

        speaker_ids = self.state.get_speakers(date_key)
        if event.get("user") not in speaker_ids:
            return

        topic = text[len(TOPIC_PREFIX) :].strip()
        if not topic:
            return
        participant = self._display_name(event["user"])
        self.repo.update_topic(date_key, participant, topic)

    def post_summary_message(self):
        date_key = self._today()
        records = self.repo.get_day_records(date_key)
        if not records:
            return

        taimen = [r["参加者"] for r in records if r["対面/オンライン"] == "対面"]
        online = [r["参加者"] for r in records if r["対面/オンライン"] == "オンライン"]
        absent = [r["参加者"] for r in records if r["対面/オンライン"] == "欠席"]
        speakers = [r for r in records if r["発表の有無"] == "○"]
        speaker_lines = [
            f"- {s['参加者']}（{s['対面/オンライン']}） テーマ: {s['発表テーマ'] or '未入力'}" for s in speakers
        ]

        text = (
            "【一次確定サマリ 15:00】\n"
            f"対面: {', '.join(taimen) if taimen else 'なし'}\n"
            f"オンライン: {', '.join(online) if online else 'なし'}\n"
            f"欠席: {', '.join(absent) if absent else 'なし'}\n"
            "発表者:\n"
            f"{chr(10).join(speaker_lines) if speaker_lines else '- なし'}\n"
            f"Meet: {self.settings.meet_url}"
        )
        self.app.client.chat_postMessage(channel=self.settings.slack_channel_id, text=text)

    def post_start_message(self):
        date_key = self._today()
        records = self.repo.get_day_records(date_key)
        speakers = [r for r in records if r["発表の有無"] == "○"]
        speaker_lines = [
            f"- {s['参加者']}（{s['対面/オンライン']}） テーマ: {s['発表テーマ'] or '未入力'}" for s in speakers
        ]
        text = (
            "@channel 勉強会を開始します！\n"
            f"Meet: {self.settings.meet_url}\n"
            "本日の発表者:\n"
            f"{chr(10).join(speaker_lines) if speaker_lines else '- なし'}"
        )
        self.app.client.chat_postMessage(channel=self.settings.slack_channel_id, text=text)


def create_flask_app() -> Flask:
    app = Flask(__name__)

    try:
        settings = Settings.from_env()
    except Exception as exc:
        error_message = str(exc)
        logger.error(error_message)

        @app.route("/slack/events", methods=["POST"])
        def slack_events_unavailable() -> Response:
            return Response(error_message, status=503)

        @app.route("/healthz", methods=["GET"])
        def healthz_unavailable() -> Response:
            return Response(error_message, status=500)

        return app

    try:
        bot = StudyGroupBot(settings)
        bot.start()
    except Exception as exc:
        error_message = str(exc)
        logger.error(error_message)

        @app.route("/slack/events", methods=["POST"])
        def slack_events_unavailable_runtime() -> Response:
            return Response(error_message, status=503)

        @app.route("/healthz", methods=["GET"])
        def healthz_unavailable_runtime() -> Response:
            return Response(error_message, status=500)

        return app

    @app.route("/slack/events", methods=["POST"])
    def slack_events() -> Response:
        return bot.handler.handle(request)

    @app.route("/healthz", methods=["GET"])
    def healthz() -> Response:
        return Response("ok", status=200)

    return app


# Cloud Run / gunicorn の buildpack 既定エントリポイント（app:app）互換のため、
# `app` という名前で Flask インスタンスを公開する。
app = create_flask_app()
flask_app = app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))
