import os
import json
import re
from datetime import datetime, timezone

class MemoryManager:
    """
    SaaS-ready:
    - Isola memória por usuário: memory/{user_id}/
    - Salva transcript em JSONL por sessão
    - Salva resumo em Markdown com metadados (frontmatter)
    - Mantém index.jsonl para busca rápida por sessões
    - Salva timestamps UTC + local (timezone do usuário via settings)
    """

    def __init__(self, base_dir="memory", user_id="default", timezone_name=None):
        self.base_dir = base_dir
        self.user_id = str(user_id)
        self.timezone_name = timezone_name  # opcional: vindo do settings
        self.user_dir = os.path.join(base_dir, self.user_id)

        self.sessions_dir = os.path.join(self.user_dir, "sessions")
        self.summaries_dir = os.path.join(self.user_dir, "summaries")
        self.index_path = os.path.join(self.user_dir, "index.jsonl")

        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.summaries_dir, exist_ok=True)

        self.conversation = []
        self.session_id = None
        self.session_started_utc = None

        self.start_session()

    # --------- sessão ---------

    def start_session(self):
        now_utc = datetime.now(timezone.utc)
        self.session_started_utc = now_utc
        self.session_id = now_utc.strftime("%Y-%m-%d_%H-%M-%S")
        self.conversation = []

    def _now(self):
        ts_utc = datetime.now(timezone.utc)
        ts_local = ts_utc.astimezone()  # usa TZ do sistema; UI pode exibir conforme settings
        return ts_utc, ts_local

    # --------- API compatível ---------

    def add(self, sender, message):
        ts_utc, ts_local = self._now()
        item = {
            "sender": sender,
            "message": message,

            # fonte da verdade
            "timestamp_utc": ts_utc.isoformat().replace("+00:00", "Z"),

            "timestamp_local": ts_local.isoformat(),
            "tz_offset_minutes": int(ts_local.utcoffset().total_seconds() // 60) if ts_local.utcoffset() else 0,
        }
        self.conversation.append(item)

    def save(self, summary_text="(nenhum resumo gerado)", topics=None, highlights=None):
       
        if not self.conversation:
            return None, None

        ended_utc = datetime.now(timezone.utc)

        session_file = os.path.join(self.sessions_dir, f"{self.session_id}.jsonl")
        summary_file = os.path.join(self.summaries_dir, f"{self.session_id}.md")

        with open(session_file, "w", encoding="utf-8") as f:
            for item in self.conversation:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        topics = topics or []
        highlights = highlights or []

        turns_user = sum(1 for x in self.conversation if str(x.get("sender","")).lower() in ("user", "você", "usuario", "usuário"))
        turns_assistant = len(self.conversation) - turns_user

        md = self._build_summary_md(
            summary_text=summary_text,
            started_at_utc=self.session_started_utc,
            ended_at_utc=ended_utc,
            turns_user=turns_user,
            turns_assistant=turns_assistant,
            topics=topics,
            highlights=highlights,
        )

        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(md)

        index_row = {
            "session_id": self.session_id,
            "started_at_utc": self.session_started_utc.isoformat().replace("+00:00", "Z"),
            "ended_at_utc": ended_utc.isoformat().replace("+00:00", "Z"),
            "turns": len(self.conversation),
            "topics": topics[:12],
            "highlights": highlights[:5],
            "summary_preview": (summary_text or "")[:240],
        }
        with open(self.index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(index_row, ensure_ascii=False) + "\n")

        self.start_session()

        return session_file, summary_file

    def load_all_memory(self, max_chars=60000):

        combined = []
        if not os.path.exists(self.summaries_dir):
            return ""

        files = sorted(
            [fn for fn in os.listdir(self.summaries_dir) if fn.endswith(".md")],
            reverse=False
        )

        for fn in files:
            path = os.path.join(self.summaries_dir, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    combined.append(f.read().strip())
            except Exception:
                pass

        text = "\n\n---\n\n".join(combined)
        return text[-max_chars:]  

    def get_relevant(self, query, limit=8):
       
        all_text = self.load_all_memory(max_chars=200000)
        lines = [l.strip() for l in all_text.splitlines() if l.strip()]

        qwords = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) >= 4]
        scored = []
        for line in lines:
            low = line.lower()
            score = sum(1 for w in qwords if w in low)
            if score > 0:
                scored.append((score, line))

        scored.sort(key=lambda x: x[0], reverse=True)
        return "\n".join(line for _, line in scored[:limit])

    # --------- helpers ---------

    def _build_summary_md(self, summary_text, started_at_utc, ended_at_utc, turns_user, turns_assistant, topics, highlights):
        started = started_at_utc.isoformat().replace("+00:00", "Z")
        ended = ended_at_utc.isoformat().replace("+00:00", "Z")

        # frontmatter YAML simples (LLM-friendly)
        fm = [
            "---",
            f"session_id: {self.session_id}",
            f"started_at_utc: {started}",
            f"ended_at_utc: {ended}",
            f"timezone_name: {self.timezone_name or 'system'}",
            f"turns_user: {turns_user}",
            f"turns_assistant: {turns_assistant}",
            f"topics: {topics}",
            "---",
            "",
        ]

        body = []
        body.append("## Resumo")
        body.append(summary_text.strip() if summary_text else "(sem resumo)")
        body.append("")
        body.append("## Highlights")
        if highlights:
            for h in highlights[:10]:
                body.append(f"- {h}")
        else:
            body.append("- (nenhum highlight)")
        body.append("")

        body.append("## Metadados")
        body.append(f"- Sessão: `{self.session_id}`")
        body.append(f"- Início (UTC): {started}")
        body.append(f"- Fim (UTC): {ended}")
        body.append("")

        return "\n".join(fm + body)
