# main.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import psutil
import os
import json
import core.facts_manager
import re
from memory.memory_store import MemoryStore
from datetime import datetime, timezone
from datetime import datetime
from utils.tool_registry import ToolRegistry

from sys_actions import clean_temp_files, clean_ram, kill_process_by_name, kill_process_by_pid
from core.monitor import SystemMonitor
from core.backend_gpt import GPTBackend
from core.memory_manager import MemoryManager
from hardware_info.hardware_info import get_all_common_info, get_hardware_summary, summary_to_text
from core.facts_manager import FactsManager

def classify_yes_no(text: str):
    t = (text or "").strip().lower()

    yes = [
        "sim","s","manda","pode mandar","pode","ok","okay","blz","beleza",
        "claro","bora","vai","manda aí","manda ai","pode sim",
        "sem problemas","pode enviar","envia","envie","mostra"
    ]

    no = [
        "não","nao","n","negativo","deixa","deixa pra lá","deixa pra la",
        "melhor não","melhor nao","não precisa","nao precisa",
        "agora não","agora nao","dispenso","não quero","nao quero"
    ]

    if any(p in t for p in yes):
        return "yes"
    if any(p in t for p in no):
        return "no"
    return None


def estimate_importance(text: str) -> int:
    t = (text or "").lower()

    if any(k in t for k in ["me chame", "meu nome é", "você é", "a partir de hoje", "nunca", "regra", "proibido"]):
        return 5

    if any(k in t for k in ["eu gosto", "eu amo", "eu odeio", "prefiro", "não gosto"]):
        return 4

    if any(k in t for k in ["projeto", "Trinity", "trabalho", "faculdade", "meta", "objetivo"]):
        return 3

    return 2


def detect_persistent_fact(text: str):
    if not text:
        return None

    triggers = [
        "nunca se esqueça",
        "lembre disso",
        "meu nome é",
        "eu me chamo",
        "você é",
        "não faça novamente",
        "não faça isso novamente",
        "guarde isso",
        "decore isso",
        "lembre disso",
        "salve na sua memória",
        "adicione na sua memória",
    ]

    t = text.lower()
    for trig in triggers:
        if trig in t:
            return text.strip()

    return None


# -------------------------
# Constants de cores / tema
# -------------------------
BG_COLOR = "#1A1A1A"           # fundo geral
CHAT_BG = "#121212"           # fundo área de chat
USER_COLOR = "#EC3030"        # vermelho usuário
Trinity_COLOR = "#00ff88"
SYSTEM_COLOR = "#6D2FFF"      # roxo mensagens do sistema/pensamento
MONITOR_COLOR = "#FC6704"     # dourado monitor
HW_TITLE = "#FFD447"
HW_SECTION = "#3CC0E9"
HW_KEY = "#FFFFFF"
HW_VALUE = "#56FC51"
HW_SEPARATOR = "#444343"
META_COLOR = "#00ff88"        # caso precise para outras mensagens

FONT_BASE = ("Consolas", 11)
FONT_SMALL = ("Consolas", 9)


class TrinityApp:
    def __init__(self, root):
        self.user_id = "default"
        self.root = root
        self.root.title("Trinity v6")

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        MEMORY_DIR = os.path.join(BASE_DIR, "memory")

        # ===== TOOLS + LOGS =====
        self.user_id = getattr(self, "user_id", "default_user")

        self.user_dir = os.path.join(BASE_DIR, "memory", self.user_id)
        self.logs_dir = os.path.join(self.user_dir, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)

        self.tool_log_path = os.path.join(self.logs_dir, "tools.jsonl")

        self.tools = ToolRegistry()


        # ✅ 2) Managers apontando pro MESMO memory/
        self.memory = MemoryManager(
            base_dir=MEMORY_DIR,
            user_id=self.user_id,
            timezone_name=getattr(self, "user_timezone", None)
        )

        self.facts_manager = FactsManager(base_dir=MEMORY_DIR)

        self.user_id = getattr(self, "user_id", "default")

        db_path = os.path.join(MEMORY_DIR, self.user_id, "memory_store.sqlite3")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.memory_store = MemoryStore(db_path=db_path)

        # ✅ 3) Carregar memória ANTES do system_prompt (evita AttributeError)
        self.persistent_memory = self.memory.load_all_memory()

        print("========== MEMÓRIA CARREGADA ==========")
        print(self.persistent_memory[:1500])
        print("======================================")

        print("LEN persistent_memory:", len(self.persistent_memory or ""))
        print("PREVIEW persistent_memory:", (self.persistent_memory or "")[:400])


        # ✅ 4) Agora pode construir o prompt
        self.system_prompt = self.build_system_prompt()

        # ---------- aplicar bg do root ----------
        self.root.configure(bg=BG_COLOR)

        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure("TButton", padding=6)
        style.configure("TLabel", background=BG_COLOR, foreground="white")
        style.configure("TFrame", background=BG_COLOR)

        self.queue = queue.Queue()
        self.monitor = SystemMonitor(queue=self.queue)
        self.backend = GPTBackend()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.recent_messages = []
        self.is_generating = False
        self.last_process_list = []

        # ----------------- Layout principal com frames -----------------
        # ===== LAYOUT RESPONSIVO (grid) =====
        self.root.grid_rowconfigure(0, weight=1)  # chat cresce
        self.root.grid_rowconfigure(1, weight=0)  # entrada fixa
        self.root.grid_rowconfigure(2, weight=0)  # toolbar fixa
        self.root.grid_columnconfigure(0, weight=1)

        top_frame = ttk.Frame(self.root)
        top_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        top_frame.grid_rowconfigure(0, weight=1)
        top_frame.grid_columnconfigure(0, weight=1)

        # Chat area (ScrolledText)
        self.text_area = scrolledtext.ScrolledText(
            top_frame,
            wrap=tk.WORD,
            height=25,
            width=80,
            state='disabled',
            font=FONT_BASE,
            bg=CHAT_BG,
            fg="white",
            insertbackground="white",
            relief=tk.FLAT
        )
        self.text_area.grid(row=0, column=0, sticky="nsew")
        self._ensure_chat_theme()

        # Barra de entrada
        entry_frame = ttk.Frame(self.root)
        entry_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 8))
        entry_frame.grid_columnconfigure(0, weight=1)

        self.entry = tk.Entry(
            entry_frame,
            font=("Consolas", 12),
            bg="#2A2A2A",
            fg=USER_COLOR,
            insertbackground="white",
            relief=tk.FLAT
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.entry.bind("<Return>", self.on_enter_pressed)

        try:
            self.entry.configure(foreground=USER_COLOR)
        except Exception:
            pass

        send_btn = ttk.Button(entry_frame, text="Enviar", command=lambda: self.on_enter_pressed(None))
        send_btn.grid(row=0, column=1, sticky="e")

        toolbar = ttk.Frame(self.root)
        toolbar.grid(row=2, column=0, sticky="ew", padx=8, pady=6)

        self.monitor_label = ttk.Label(toolbar, text="Monitor: Inicializando...", font=FONT_SMALL)
        self.monitor_label.pack(side=tk.LEFT, padx=(0, 10))
        try:
            self.monitor_label.configure(foreground=MONITOR_COLOR)
        except Exception:
            pass


        self.autofix_btn = ttk.Button(toolbar, text="Autofix", command=self.autofix)
        self.autofix_btn.pack(side=tk.RIGHT, padx=(6, 0))
        hw_btn = ttk.Button(toolbar, text="Resumo HW (Chat)",
                            command=lambda: self.root.after(0, lambda: self.notify_hardware_in_chat(detailed=False)))
        hw_btn.pack(side=tk.RIGHT, padx=(6, 0))
        manage_btn = ttk.Button(toolbar, text="Gerenciar Processos",
                                command=lambda: self.root.after(0, self.open_process_manager))
        manage_btn.pack(side=tk.RIGHT, padx=(6, 0))

        self.monitor_thread = threading.Thread(target=self.monitor.start_monitoring, daemon=True)
        self.monitor_thread.start()

        self.root.after(100, self.process_queue)

        self._ensure_tags_configured()


        from datetime import datetime

    def _get_relevant_memory(self, query: str, max_lines: int = 12, max_chars: int = 2000) -> str:
        if not self.persistent_memory:
            return ""

        lines = [l.strip() for l in self.persistent_memory.splitlines() if l.strip()]
        if not lines:
            return ""

        qwords = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) >= 4]

        scored = []
        for line in lines:
            low = line.lower()
            score = sum(1 for w in qwords if w in low)
            scored.append((score, line))

        scored.sort(key=lambda x: x[0], reverse=True)
        picked = [l for s, l in scored if s > 0][:max_lines]

        if not picked:
            picked = lines[:max_lines]

        text = "\n".join(picked)
        return text[:max_chars]


    def _should_interrupt_now(self) -> bool:
        if getattr(self, "is_generating", False):
            return False
        import time
        last = getattr(self, "_last_proactive_ts", 0.0)
        if time.time() - last < 90:
            return False
        return True


    def _proactive_decide(self, event_type: str, payload: dict) -> str:
      
        system = (
            "Você é Trinity, um assistente PROATIVO rodando localmente.\n"
            "Você recebe eventos do sistema (cpu/mem/disk/processos).\n"
            "Sua tarefa: decidir se deve interromper o usuário.\n"
            "Se for útil, escreva UMA mensagem curta e acionável.\n"
            "Se não for necessário, responda exatamente: IGNORE\n"
            "Nunca seja dramático. Sem perguntas repetitivas."
        )

        user = (
            f"EVENTO: {event_type}\n"
            f"DADOS: {payload}\n\n"
            "Responda com uma mensagem curta OU IGNORE."
        )

        msg = [
            {"role": "system", "content": system},
            *getattr(self, "recent_messages", [])[-6:],
            {"role": "user", "content": user},
        ]

        out = self.backend.generate_full_response(msg, max_completion_tokens=180)
        out = (out or "").strip()

        if out.upper().startswith("IGNORE"):
            return ""
        return out


    def handle_monitor_event(self, event_type: str, payload: dict):
        if not self._should_interrupt_now():
            return

        if event_type not in ("monitor_alert", "monitor_suggest", "monitor_autofix"):
            return

        disk = float(payload.get("disk", 0.0) or 0.0)
        if disk >= 90:
            self.pending_action = {"type": "disk_cleanup"}
            self.awaiting_action_confirm = True

            self._render_message(
                "meta",
                f"⚠️ Seu disco está em {disk:.1f}%.\n"
                "Quer que eu faça uma limpeza automática agora (temporários + ajustes seguros)?\n"
                "Responda: **SIM** ou **NÃO**."
            )
            return


        text = self._proactive_decide(event_type, payload)
        if not text:
            return

        import time
        self._last_proactive_ts = time.time()
        self._render_message("meta", f"⚙️ {text}")

    def _tool_decision(self, user_text: str) -> dict:
        system = (
            "Você é Chronos rodando LOCALMENTE com acesso a ferramentas do PC.\n"
            "Se a pergunta exigir olhar arquivos/pastas/editar/deletar/mover, escolha UMA ferramenta.\n"
            "Responda SOMENTE com JSON válido, sem texto extra.\n\n"
            'Formatos:\n'
            '{"tool":"none"}\n'
            '{"tool":"list_files","args":{"path":"C:/Users/.../Desktop"}}\n'
            '{"tool":"count_files","args":{"path":"C:/Users/.../Desktop"}}\n'
            '{"tool":"read_text","args":{"path":"C:/Users/.../file.txt"}}\n'
            '{"tool":"write_text","args":{"path":"C:/Users/.../file.txt","content":"..."}}\n'
            '{"tool":"move","args":{"src":"...","dst":"..."}}\n'
            '{"tool":"delete","args":{"path":"..."}}\n\n'
            "Se não precisar de ferramenta, use tool=none."
        )

        msg = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ]

        raw = self.backend.generate_full_response(msg, max_completion_tokens=180) or ""

        m = re.search(r"\{.*\}", raw, flags=re.S)
        if not m:
            return {"tool": "none", "args": {}}

        try:
            data = json.loads(m.group(0))
            if not isinstance(data, dict):
                return {"tool": "none", "args": {}}
            data.setdefault("tool", "none")
            data.setdefault("args", {})
            return data
        except Exception:
            return {"tool": "none", "args": {}}


    def _log_tool_call(self, tool_call: dict, tool_result: dict):
        try:
            rec = {
                "ts_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "user_id": getattr(self, "user_id", "default_user"),
                "tool": tool_call.get("tool"),
                "args": tool_call.get("args", {}),
                "result": tool_result,
            }
            with open(self.tool_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _run_quick_fix(self, action: str):
        
        try:
            if action == "disk_cleanup":
                removed = clean_temp_files()  
                return {"ok": True, "removed": removed}

            if action == "clean_temp":
                removed = clean_temp_files()
                return {"ok": True, "removed": removed}

            if action == "clean_ram":
                res = clean_ram()
                return {"ok": True, "result": res}

            return {"ok": False, "error": f"unknown_action: {action}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


    def _chat_newline(self, n=1):
        self.text_area.configure(state="normal")
        self.text_area.insert(tk.END, "\n" * n)
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()


    def _append_chat(self, sender: str, message: str, tag: str = "normal_text"):
      
        if message is None:
            message = ""

        self.text_area.configure(state="normal")

        current = self.text_area.get("1.0", tk.END)
        if current.strip():
            self.text_area.insert(tk.END, "\n\n")

        header = f"{sender}: "
        self.text_area.insert(tk.END, header, "title_big" if sender.lower() == "Trinity" else "subtitle")

        self.text_area.insert(tk.END, message.strip(), tag)

        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()

    def _append_chat_stream(self, sender: str, chunk: str, tag: str = "normal_text"):
        
        if not chunk:
            return

        self.text_area.configure(state="normal")
        self.text_area.insert(tk.END, chunk, tag)
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()


    def _end_stream_block(self):
        
        self.text_area.configure(state="normal")
        self.text_area.insert(tk.END, "\n")
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()


    def load_all_memories(self):
        memories = []
        for file in sorted(self.memory_dir.glob("*.json")):
            with open(file, "r", encoding="utf-8") as f:
                memories.extend(json.load(f))
        return memories

    def build_system_prompt(self):
        user_name = getattr(self, "user_name", "Usuário")
        assistant_name = getattr(self, "assistant_name", "Trinity")

        facts = ""
        try:
            facts = self.facts_manager.formatted_facts()
        except Exception:
            facts = ""

        memory = self.persistent_memory or ""

        return f"""
    Você é {assistant_name}, um assistente pessoal do usuário {user_name}.

    Você opera em um sistema com MEMÓRIA PERSISTENTE REAL:
    - FATOS PERSISTENTES (verdades sobre o usuário)
    - REGISTROS HISTÓRICOS (resumos de conversas anteriores)

    ## REGRAS CRÍTICAS (OBRIGATÓRIAS)
    - Nunca diga que não tem memória.
    - Nunca diga que "cada conversa é independente".
    - Nunca diga que "não pode armazenar informações".
    - Se algo foi salvo como fato, confirme de forma curta: "Registrado na memória persistente."
    - Você TEM ferramentas locais. Se precisar de dados do PC, use as ferramentas. Você tem acesso a todos os dados do computador do usuário.

    ## USO CORRETO DA MEMÓRIA
    - Use FATOS PERSISTENTES como prioridade máxima quando a pergunta for sobre o usuário.
    - Use REGISTROS HISTÓRICOS quando o usuário pedir lembrança de conversas anteriores.
    - Se não encontrar o detalhe exato nos registros, diga: "Não encontrei esse detalhe específico nos registros carregados", e ofereça um resumo do que existe.
    - {facts if facts else "- (nenhum fato persistente registrado ainda)"}

    ## CONHECIMENTO GERAL vs MEMÓRIA
    - Se a pergunta for conhecimento geral (ex.: história, ciência, matemática, cultura), responda normalmente e NÃO force memória.
    - Se a pergunta for pessoal (ex.: "o que você sabe sobre mim?", "lembra do que conversamos?"), use fatos e registros.
    - Se não houver timestamp explícito, não diga “recentemente”; diga “em algum momento anterior”.

    ## ESTILO
    - Seja direto e natural.
    - Não mencione "prompt", "sistema", "arquivos" ou "JSON".
    - Não invente memórias específicas. Se não houver evidência, seja transparente.
    - Não encerre respostas com perguntas padrão do tipo: "Como posso ajudar?", "Posso ajudar em mais alguma coisa?", "Se precisar de algo, estou aqui."
    - Só faça perguntas se precisar de uma informação específica para cumprir a tarefa.

    ## FATOS PERSISTENTES (PRIORIDADE MÁXIMA)
    {facts if facts else "- (nenhum fato persistente registrado ainda)"}

    ## REGISTROS HISTÓRICOS DISPONÍVEIS
    {memory if memory else "(nenhum registro histórico carregado)"}

    """.strip()


    def _ensure_tags_configured(self):
        # cria as tags com as cores pedidas (se o widget já existir)
        try:
            self.text_area.tag_config("user", foreground=USER_COLOR)
            self.text_area.tag_config("Trinity", foreground=Trinity_COLOR)
            self.text_area.tag_config("meta", foreground=META_COLOR, font=FONT_SMALL)
            self.text_area.tag_config("system", foreground=SYSTEM_COLOR, font=FONT_SMALL)
            self.text_area.tag_config("monitor", foreground=MONITOR_COLOR)

            # hardware multicolor
            self.text_area.tag_config("hw_title", foreground=HW_TITLE, font=("Consolas", 11, "bold"))
            self.text_area.tag_config("hw_section", foreground=HW_SECTION, font=("Consolas", 10, "bold"))
            self.text_area.tag_config("hw_key", foreground=HW_KEY, font=("Consolas", 10, "bold"))
            self.text_area.tag_config("hw_value", foreground=HW_VALUE, font=("Consolas", 10))
            self.text_area.tag_config("hw_separator", foreground=HW_SEPARATOR)
            self.text_area.tag_config("hardware", foreground="#E6C07B")  # fallback color for generic HW lines

            self.text_area.tag_config("list_number", foreground="#FFD447", font=("Consolas", 11, "bold"))
            self.text_area.tag_config("list_bullet", foreground="#3CC0E9", font=("Consolas", 11))
            self.text_area.tag_config("title_big", foreground="#00FFDD", font=("Consolas", 12, "bold"))
            self.text_area.tag_config("subtitle", foreground="#FF7AE6", font=("Consolas", 11, "bold"))
            self.text_area.tag_config("normal_text", foreground=Trinity_COLOR)
        except Exception:
            pass

    # -------------------------
    def on_close(self):
        try:
            full_text = "\n".join([f"{m['sender']}: {m['message']}" for m in self.memory.conversation])
            summary = self.backend.summarize(full_text)

            raw_path, summary_path = self.memory.save(summary)

            utc_now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            self.memory_store.add(
                text=summary,
                meta={
                    "type": "session_summary",
                    "user_id": self.user_id,
                    "created_at_utc": utc_now,
                    "session_id": getattr(self.memory, "session_id", None),
                    "summary_path": summary_path,
                    "raw_path": raw_path,
                    "importance": 2,
                    "pinned": False,
                }
            )

            self._append_chat("Trinity", f"Memória salva:\n- RAW: {raw_path}\n- RESUMO: {summary_path}", "meta")
            self.memory.add("action", f"Memória salva: RAW={raw_path}, SUMMARY={summary_path}")
        except Exception as e:
            print("Erro ao salvar memória:", e)

        self.root.destroy()


    def on_enter_pressed(self, event=None):

        user_text = self.entry.get().strip()
        if not user_text or self.is_generating:
            return "break"

        self.entry.delete(0, tk.END)

        self._render_message("user", user_text)

        try:
            self.memory.add("user", user_text)
            # memória curta (para o modelo)
            self.recent_messages.append({"role": "user", "content": user_text})
            self.recent_messages = self.recent_messages[-20:]  # mantém curto

        except Exception:
            pass

        threading.Thread(target=self.generate_response, args=(user_text,), daemon=True).start()

        return "break"

    def _ensure_chat_theme(self):
        ta = self.text_area

        # Base
        ta.configure(wrap="word", padx=16, pady=16, spacing1=6, spacing2=2, spacing3=8)

        # Divisor
        ta.tag_configure("divider", foreground="#2A2A2A")

        # Headers
        ta.tag_configure("user_header", foreground="#EC3030", font=("Consolas", 10, "bold"))
        ta.tag_configure("ai_header", foreground="#00ff88", font=("Consolas", 10, "bold"))
        ta.tag_configure("meta_header", foreground="#6D2FFF", font=("Consolas", 10, "bold"))
        ta.tag_configure("time", foreground="#8A8A8A", font=("Consolas", 9))

        # Bodies
        ta.tag_configure("user_body", foreground="#FFFFFF", font=("Consolas", 11))
        ta.tag_configure("ai_body", foreground="#EDEDED", font=("Consolas", 11))
        ta.tag_configure("meta_body", foreground="#D0D0FF", font=("Consolas", 11))

        # Quote & code
        ta.tag_configure("quote", lmargin1=18, lmargin2=18, foreground="#B6B6B6")
        ta.tag_configure("codeblock", font=("Consolas", 10), background="#0E0E0E", foreground="#EDEDED", lmargin1=16, lmargin2=16)

    def _insert_divider(self):
        self.text_area.insert(tk.END, "\n────────────\n", "divider")

    def _render_message(self, role: str, text: str):
        name_map = {"user": "Você", "assistant": getattr(self, "assistant_name", "Chronos"), "meta": "Sistema"}
        emoji_map = {"user": "👤", "assistant": "🤖", "meta": "⚙️"}

        header_tag = "user_header" if role == "user" else "ai_header" if role == "assistant" else "meta_header"
        body_tag = "user_body" if role == "user" else "ai_body" if role == "assistant" else "meta_body"

        now = datetime.now().strftime("%H:%M")

        self.text_area.configure(state="normal")

        current = self.text_area.get("1.0", tk.END).strip()
        if current:
            self._insert_divider()

        self.text_area.insert(tk.END, f"{emoji_map[role]} {name_map[role]}  ", header_tag)
        self.text_area.insert(tk.END, f"{now}\n", "time")
        self.text_area.insert(tk.END, f"{(text or '').strip()}\n", body_tag)

        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()


    def _start_assistant_card(self):
        self.text_area.configure(state="normal")
        current = self.text_area.get("1.0", tk.END).strip()
        if current:
            self._insert_divider()

        now = datetime.now().strftime("%H:%M")
        name = getattr(self, "assistant_name", "Chronos")

        self.text_area.insert(tk.END, f"🤖 {name}  ", "ai_header")
        self.text_area.insert(tk.END, f"{now}\n", "time")
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()


    def _append_assistant_stream(self, chunk: str):
        self.text_area.configure(state="normal")
        self.text_area.insert(tk.END, chunk, "ai_body")
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()


    def _end_assistant_card(self):
        self.text_area.configure(state="normal")
        self.text_area.insert(tk.END, "\n", "ai_body")
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)
        self.root.update_idletasks()




    def add_persistent_fact(self, fact: str):

        imp = estimate_importance(fact)
        self.facts_manager.add_fact(fact)
        self.system_prompt = self.build_system_prompt()

        utc_now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        self.memory_store.add(
            text=fact,
            meta={
                "type": "fact",
                "user_id": self.user_id,
                "created_at_utc": utc_now,
                "importance": 4,
                "pinned": True if "nome" in fact.lower() or "chamar" in fact.lower() else False,

            }
        )

        try:
            total = len(self.facts_manager.load_facts())
            self._append_chat("Trinity", f"[FATO SALVO] ({total}) {fact}", "meta")
        except Exception:
            self._append_chat("Trinity", f"[FATO SALVO] {fact}", "meta")



    # -------------------------
    def process_queue(self):
        while not self.queue.empty():
            typ, payload = self.queue.get()
            if typ == "monitor_status":
                cpu = payload.get("cpu", 0)
                mem = payload.get("mem", 0)
                disk = payload.get("disk", 0)
                # atualiza label do monitor com cor dourada (tag monitor aplicada no append)
                self.monitor_label.config(text=f"Monitor: CPU: {cpu:.1f}%, RAM: {mem:.1f}%, Disco: {disk:.1f}%")
            elif typ in ("monitor_alert", "monitor_suggest", "monitor_autofix"):
                self.handle_monitor_event(typ, payload)
        self.root.after(100, self.process_queue)

    # -------------------------
    def autofix(self):
        if self.is_generating:
            return
        self._append_chat("Trinity", "Iniciando autofix completo: limpando RAM, processos pesados e arquivos temporários...", "Trinity")
        try:
            self.memory.add("action", "Autofix iniciado: limpar RAM, matar processos pesados, limpar temp")
        except Exception:
            pass
        threading.Thread(target=self._run_autofix, daemon=True).start()

    def _run_autofix(self):
        self.is_generating = True
        try:
            res_ram = clean_ram()
            self._append_chat("Trinity", f"Limpeza de RAM: {res_ram}", "Trinity")
            try:
                self.memory.add("action", f"clean_ram -> {res_ram}")
            except Exception:
                pass

            procs = self.monitor._get_top_processes(10)
            killed = 0
            killed_list = []
            current_pid = os.getpid()  # PID do próprio app
            for p in procs:
                if p['pid'] == current_pid:
                    continue  # Não mata o próprio processo
                if p['cpu_percent'] > 30:
                    res = self.monitor.kill_process(p['pid'])
                    if res[0]:
                        killed += 1
                        killed_list.append(f"{p['name']} (PID {p['pid']})")

            if killed == 0:
                self._append_chat("Trinity", "Nenhum processo pesado (CPU > 30%) foi finalizado.", "Trinity")
            else:
                self._append_chat("Trinity", f"Processos pesados finalizados: {killed}", "Trinity")
                try:
                    self.memory.add("action", f"Processos finalizados no autofix: {', '.join(killed_list)}")
                except Exception:
                    pass

            res_temp = clean_temp_files()
            self._append_chat("Trinity", f"Arquivos temporários removidos: {res_temp}", "Trinity")
            try:
                self.memory.add("action", f"clean_temp -> {res_temp}")
            except Exception:
                pass

            self._append_chat("Trinity", "Autofix completo finalizado.", "Trinity")
            try:
                self.memory.add("action", "Autofix finalizado")
            except Exception:
                pass
        except Exception as e:
            self._append_chat("Trinity", f"[ERRO] Durante autofix: {e}", "meta")
        self.is_generating = False

    def open_process_manager(self):
        window = tk.Toplevel(self.root)
        window.title("Gerenciador de Processos")
        window.geometry("900x600")
        window.configure(bg=BG_COLOR)

        # ========================= PARTE SUPERIOR: TABELA =========================
        table_frame = ttk.Frame(window)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ("pid", "name", "cpu", "ram", "status")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")

        for col in columns:
            tree.heading(col, text=col.upper(), command=lambda c=col: sort_tree(c))
            tree.column(col, width=120 if col != "name" else 260, anchor="w")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # ========================= FILTRO =========================
        filter_frame = ttk.Frame(window)
        filter_frame.pack(fill=tk.X, padx=5)

        ttk.Label(filter_frame, text="Filtrar por nome:").pack(side=tk.LEFT)
        filter_var = tk.StringVar()
        filter_entry = ttk.Entry(filter_frame, textvariable=filter_var)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # ========================= BARRA INFERIOR FIXA =========================
        bottom_frame = ttk.Frame(window)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)

        cpu_label = ttk.Label(bottom_frame, text="CPU: --%")
        cpu_label.pack(side=tk.LEFT, padx=5)

        ram_label = ttk.Label(bottom_frame, text="RAM: --%")
        ram_label.pack(side=tk.LEFT, padx=5)

        disk_label = ttk.Label(bottom_frame, text="Disco: --%")
        disk_label.pack(side=tk.LEFT, padx=5)

        kill_btn = ttk.Button(bottom_frame, text="Finalizar processo", command=lambda: kill_selected())
        kill_btn.pack(side=tk.RIGHT, padx=10)

        # ========================= FUNÇÕES INTERNAS =========================

        process_list = []

        def update_monitor_labels():
            try:
                cpu_label.config(text=f"CPU: {psutil.cpu_percent():.1f}%")
                ram_label.config(text=f"RAM: {psutil.virtual_memory().percent:.1f}%")
                disk_label.config(text=f"Disco: {psutil.disk_usage('/').percent:.1f}%")
            except:
                pass
            window.after(1500, update_monitor_labels)

        def refresh_process_list():
            nonlocal process_list
            tree.delete(*tree.get_children())
            process_list = []

            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    info = proc.info
                    process_list.append({
                        "pid": info.get("pid"),
                        "name": info.get("name") or "N/A",
                        "cpu": float(info.get("cpu_percent") or 0),
                        "ram": float(info.get("memory_percent") or 0),
                        "status": info.get("status") or "N/A"
                    })
                except:
                    continue

            apply_filters()

        def apply_filters():
            text = filter_var.get().lower()
            tree.delete(*tree.get_children())

            filtered = [p for p in process_list if text in p["name"].lower()]

            for i, p in enumerate(filtered):
                tree.insert("", "end", values=(
                    p["pid"], p["name"], f"{p['cpu']:.1f}", f"{p['ram']:.1f}", p["status"]
                ))

        def sort_tree(col):
            reverse = getattr(sort_tree, "reverse", False)
            setattr(sort_tree, "reverse", not reverse)

            process_list.sort(key=lambda x: x[col], reverse=reverse)
            apply_filters()

        def kill_selected():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Info", "Nenhum processo selecionado.")
                return

            current_pid = os.getpid()

            for item in selected:
                pid = int(tree.item(item)["values"][0])

                if pid == current_pid:
                    messagebox.showwarning("Aviso", "Não posso finalizar o próprio Trinity.")
                    continue

                success, msg = kill_process_by_pid(pid)
                self._append_chat("Trinity", msg, "Trinity")

            refresh_process_list()

        filter_var.trace_add("write", lambda *_: apply_filters())

        # ========================= INICIAR =========================
        update_monitor_labels()
        refresh_process_list()

    def notify_hardware_in_chat(self, detailed: bool = False):
        
        try:
            summary = get_hardware_summary()
            text = summary_to_text(summary)
        except Exception as e:
            self._append_chat("Trinity", f"Erro ao coletar informações de hardware: {e}", "meta")
            return

        header = "[Hardware - Resumo]\n"
        self._append_chat("Trinity", header, "Trinity")

        lines = text.splitlines()

        def insert_lines_chunked(start=0, chunk_size=25):
            end = min(start + chunk_size, len(lines))
            for ln in lines[start:end]:
                line = ln.rstrip()
                # heurística para aplicar tags coloridas:
                if not line.strip():
                    self._append_chat("Trinity", " ", "hw_separator")
                    continue

                # Se for cabeçalho principal (linha de ====== no summary_to_text)
                if set(line.strip()) == set("="):
                    self._append_chat("Trinity", line, "hw_title")
                    continue

                # se linha começa com '-' ou '•' -> item de lista (seção)
                if line.strip().startswith("•") or line.strip().startswith("-"):
                    self._append_chat("Trinity", line.strip(), "hw_section")
                    continue

                # se tem 'DATA', 'SISTEMA', etc (títulos de topo)
                if line.strip().upper().startswith(("DATA", "SISTEMA", "ARQUITETURA", "CPU", "MEMÓRIA", "DISCO", "GPU", "REDE")):
                    self._append_chat("Trinity", line.strip(), "hw_title")
                    continue

                # se contém ':', separa em chave/valor
                if ":" in line:
                    parts = line.split(":", 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if key:
                        self._append_chat("Trinity", f"{key}:", "hw_key")
                    if val:
                        self._append_chat("Trinity", f" {val}", "hw_value")
                else:
                    # fallback para linhas quaisquer
                    self._append_chat("Trinity", line, "hardware")

            if end < len(lines):
                # schedule next chunk
                self.root.after(40, lambda: insert_lines_chunked(end, chunk_size))
        insert_lines_chunked(0, 40) 

    def detect_persistent_fact(text: str):
        if not text:
            return None

        t = text.strip()
        low = t.lower()

        triggers = [
            "nunca se esqueça",
            "lembre disso",
            "meu nome é",
            "eu me chamo",
            "você é",
            "não faça novamente",
            "não faça isso novamente",
            "salve na sua memória",
            "salve na memória",
            "guarde na sua memória",
            "adicione na sua memória",
        ]

        if any(trig in low for trig in triggers):
            if ":" in t and ("salve" in low or "guarde" in low or "adicione" in low):
                payload = t.split(":", 1)[1].strip()
                if payload:
                    return payload

            return t

        return None


    def extract_intent_with_gpt(self, user_text):
        memory_block = (
            "MEMÓRIA HISTÓRICA (REGISTROS REAIS):\n"
            "============================\n"
            f"{self._get_relevant_memory(user_text)}\n"
            "============================\n"
        )

        system_prompt_full = self.build_system_prompt() + "\n\n" + memory_block

        # ===== TOOL DECISION =====
        tool_call = self._tool_decision(user_text)
        tool_result = None

        if tool_call.get("tool") and tool_call["tool"] != "none":
            tool_result = self.tools.execute(
                tool_call["tool"],
                tool_call.get("args", {})
            )
            self._log_tool_call(tool_call, tool_result)

        tool_block = ""
        if tool_result is not None:
            tool_block = (
                "RESULTADO DE FERRAMENTA (DADOS REAIS DO SISTEMA):\n"
                "============================\n"
                f"{tool_result}\n"
                "============================\n"
                "Use isso como fonte real."
            )

        messages = [
            {
                "role": "system",
                "content": self.system_prompt + ("\n\n" + tool_block if tool_block else "")
            },
            *self.recent_messages[-8:],
            {"role": "user", "content": user_text},
        ]


        full_response = self.backend.generate_full_response(messages, max_completion_tokens=512)

        try:
            data = json.loads(full_response)
            return data
        except Exception:
            return {"intent": "respond", "params": {}, "response_text": full_response}
        
        

    # -------------------------
    def generate_response(self, user_text):
        self.is_generating = True

        try:
            low = (user_text or "").lower().strip()

            if getattr(self, "awaiting_action_confirm", False):
                ans = classify_yes_no(low)

                if ans == "yes":
                    self.awaiting_action_confirm = False
                    action = (getattr(self, "pending_action", {}) or {}).get("type")
                    self.pending_action = None

                    result = self._run_quick_fix(action)
                    self._render_message("meta", f"✅ Correção executada: {result}")
                    return

                if ans == "no":
                    self.awaiting_action_confirm = False
                    self.pending_action = None
                    self._render_message("meta", "Beleza — não vou mexer em nada. Se quiser depois é só pedir 🙂")
                    return

            if getattr(self, "awaiting_hw_confirm", False):
                ans = classify_yes_no(low)
                if ans == "yes":
                    self.awaiting_hw_confirm = False
                    self.notify_hardware_in_chat(detailed=False)
                    return
                if ans == "no":
                    self.awaiting_hw_confirm = False
                    self._render_message("meta", "Beleza, sem problemas 🙂")
                    return
            
            mentions_ram = ("ram" in low) or ("memória ram" in low) or ("uso de ram" in low)
            status_words = any(k in low for k in ["uso", "%", "quanto", "como tá", "como está", "agora", "consumo"])
            clean_words = any(k in low for k in ["limpar", "liberar", "otimizar", "fechar processos"])

            if mentions_ram and status_words and not clean_words:
                self.awaiting_hw_confirm = True
                self._render_message(
                    "meta",
                    "💡 Você pode clicar no botão **Resumo HW (Chat)**.\n"
                    "Se quiser que eu envie aqui, diga: **sim / manda / ok**"
                )
                return

            fact = detect_persistent_fact(user_text)
            if fact:
                self.add_persistent_fact(fact)  

            intent_data = self.extract_intent_with_gpt(user_text)
            intent = intent_data.get("intent")
            response_text = intent_data.get("response_text", "")

            if intent not in ("clean_ram", "clean_temp"):
                intent = "respond"
            if intent is None:
                intent = "respond"

            if intent == "clean_ram":
                res = clean_ram()
                self._render_message("assistant", f"✅ Resultado: {res}")
                return

            if intent == "clean_temp":
                res = clean_temp_files()
                self._render_message("assistant", f"✅ Temporários removidos: {res}")
                return

            if intent != "respond":
                self._render_message("assistant", response_text)
                return

            tool_call = self._tool_decision(user_text)
            print("DEBUG tool_call:", tool_call)

            tool_result = None
            if tool_call.get("tool") and tool_call["tool"] != "none":
                tool_result = self.tools.execute(tool_call["tool"], tool_call.get("args", {}))
                self._log_tool_call(tool_call, tool_result)

            tool_block = ""
            if tool_result is not None:
                tool_block = (
                    "DADOS DO SISTEMA (FERRAMENTA LOCAL EXECUTADA):\n"
                    "============================\n"
                    f"tool_call: {tool_call}\n"
                    f"tool_result: {tool_result}\n"
                    "============================\n"
                    "Use esses dados como VERDADE. Não diga que não tem acesso.\n"
                )

            hits = self.memory_store.search(user_text, top_k=10)

            from datetime import datetime, timezone

            def _utc_now():
                return datetime.now(timezone.utc)

            def _recency_factor(created_at_utc: str) -> float:
                try:
                    s = (created_at_utc or "").replace("Z", "+00:00")
                    dt = datetime.fromisoformat(s)
                    days = (_utc_now() - dt).total_seconds() / 86400.0

                    if days < 1:
                        return 1.25
                    if days < 7:
                        return 1.10
                    if days < 30:
                        return 1.00
                    if days < 180:
                        return 0.90
                    return 0.80
                except Exception:
                    return 1.0

            reranked = []
            for h in hits:
                meta = h.get("meta", {}) or {}
                sem = float(h.get("score", 0.0))
                imp = int(meta.get("importance", 2))
                pinned = bool(meta.get("pinned", False))
                ts = meta.get("created_at_utc", "")

                boost = (1.0 + imp * 0.25) * _recency_factor(ts)
                if pinned:
                    boost *= 1.5

                reranked.append((sem * boost, h))

            reranked.sort(key=lambda x: x[0], reverse=True)
            top_hits = [h for _, h in reranked[:6]]

            relevant_lines = []
            for h in top_hits:
                meta = h.get("meta", {}) or {}
                ts = meta.get("created_at_utc", "?")
                typ = meta.get("type", "mem")
                relevant_lines.append(f"- [{ts}] ({typ}) {h.get('text','')}")

            relevant_block = "\n".join(relevant_lines) if relevant_lines else "(nenhuma memória relevante encontrada)"

            memory_block = (
                "MEMÓRIA RELEVANTE (BUSCA SEMÂNTICA):\n"
                "============================\n"
                f"{relevant_block}\n"
                "============================\n"
            )

        
            system_prompt_full = self.build_system_prompt() + "\n\n" + tool_block + "\n\n" + memory_block

            messages = [
                {"role": "system", "content": system_prompt_full},
                *self.recent_messages[-8:],
                {"role": "user", "content": user_text},
            ]

       
            response_builder = []

            self._start_assistant_card()

            for chunk in self.backend.generate_stream(messages):
                response_builder.append(chunk)
                self._append_assistant_stream(chunk)

            self._end_assistant_card()

            final_response = "".join(response_builder).strip()

            try:
                self.recent_messages.append({"role": "assistant", "content": final_response})
                self.recent_messages = self.recent_messages[-20:]
            except Exception:
                pass

            try:
                self.memory.add("assistant", final_response)
            except Exception:
                pass

        except Exception as e:
            try:
                self._render_message("meta", f"❌ [ERRO] {e}")
            except Exception:
                print("ERRO:", e)

        finally:
            self.is_generating = False




# -------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = TrinityApp(root)
    root.mainloop()