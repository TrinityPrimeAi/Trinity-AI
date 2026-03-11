import re

class IntentParser:
    def __init__(self): 
        self.memory_logic_terms = [
            "lembrar", "lembra", "lembrou", "recordar", "histórico",
            "memória da conversa", "memoria da conversa",
            "memória do chat", "memoria do chat",
            "contexto", "você se lembra", "vc se lembra",
            "memória continua funcionando"
        ]

        # --- Termos para RAM ---
        self.ram_terms = [
            "ram", "memória ram", "memoria ram", "memória física",
            "memoria física", "uso de ram", "quanto de ram",
            "limpar ram", "limpa ram", "liberar ram",
            "liberar memória ram", "liberar memoria ram", "otimizar ram"
        ]

        # --- Termos para disco ---
        self.disk_terms = [
            "uso do disco", "ver disco", "checar disco",
            "espaço em disco", "disco cheio", "limpar temp", "limpar temporários",
            "pasta temporária", "limpar arquivos temporários"
        ]

        # --- Termos para processos pesados ---
        self.heavy_process_terms = [
            "processos pesados", "listar processos", "processos em execução",
            "processos rodando", "listar processos pesados",
            "ver processos pesados", "processos ativos"
        ]

        # --- Termos para confirmação e negação ---
        self.confirm_terms = ["sim", "pode", "faça", "confirma", "confirmar", "ok", "okay", "execute", "continue"]
        self.deny_terms = ["não", "nao", "cancelar", "cancela", "pare", "stop"]

        # --- Padrões para fechar processos ---
        self.kill_process_patterns = [
            r"matar processo (.+)",
            r"finalizar processo (.+)",
            r"fechar processo (.+)",
            r"encerrar processo (.+)",
            r"matar o (.+)",
            r"fechar o (.+)",
            r"mata (.+)",
            r"finaliza (.+)",
            r"mata o (.+)",
            r"finaliza o (.+)",
            r"fecha (.+)",
            r"fecha o (.+)"
        ]

        # --- Padrões para encontrar processos ---
        self.find_process_patterns = [
            r"procura processo (.+)",
            r"procure processo (.+)",
            r"procura processos (.+)",
            r"procure processos (.+)",
            r"procura processo com nome (.+)",
            r"procure processo com nome (.+)",
            r"procura processo com pid (\d+)",
            r"procure processo com pid (\d+)",
            r"procura processo com caminho (.+)",
            r"procure processo com caminho (.+)",
            r"encontra processo (.+)",
            r"encontre processo (.+)",
            r"encontra processos (.+)",
            r"encontre processos (.+)",
            r"encontra processo com nome (.+)",
            r"encontre processo com nome (.+)",
            r"encontra processo com pid (\d+)",
            r"encontre processo com pid (\d+)",
            r"encontra processo com caminho (.+)",
            r"encontre processo com caminho (.+)"
        ]

        # --- Termos para listar por filtro (CPU, RAM, nome, etc) ---
        self.filter_process_patterns = [
            r"listar processos com cpu maior que (\d+)%?",
            r"listar processos com ram menor que (\d+)%?",
            r"listar processos que contenham '(.+)' no nome",
            r"listar processos com nome '(.+)'",
            r"listar processos com pid (\d+)",
            r"listar processos com caminho '(.+)'",
            r"listar processos do '(.+)'"
        ]

        # --- Termos para perguntar se processo está aberto ---
        self.process_exists_patterns = [
            r"tem processo do (.+) aberto",
            r"processo do (.+) está rodando",
            r"processo do (.+) está aberto",
            r"o (.+) está aberto",
            r"tem (.+) rodando",
            r"tem (.+) aberto"
        ]

        # --- Outros intents simples ---
        self.basic_intents = {
            # RAM
            "get_ram": [
                "quanto de ram",
                "mostrar ram",
                "ver ram",
                "consultar ram",
                "uso de ram",
                "ram total"
            ],
            "clean_ram": [
                "limpar ram",
                "liberar ram",
                "limpar memória ram",
                "liberar memória ram",
                "otimizar ram",
                "ram alta",
                "cache alto",
                "cache de ram alta"
            ],

            # Disco
            "check_disk": [
                "uso do disco",
                "ver disco",
                "checar disco",
                "espaço em disco",
                "disco cheio"
            ],
            "clean_temp": [
                "limpar temp",
                "limpar temporários",
                "limpar pasta temporária",
                "limpar arquivos temporários",
                "limpar lixo",
                "limpar lixos"
            ],

            # Processos pesados
            "list_heavy_processes": [
                "listar processos pesados",
                "ver processos pesados",
                "processos pesados",
                "processos ativos",
                "listar processos em execução"
            ],

            # Autofix (ação múltipla)
            "autofix": [
                "autofix",
                "corrigir sistema",
                "corrigir computador",
                "otimizar sistema"
            ]
        }

    def parse_intent(self, text: str):
        if not text or not text.strip():
            return {"intent": None, "params": {}}

        t = text.lower().strip()

        for phrase in self.memory_logic_terms:
            pattern = r'\b' + re.escape(phrase) + r'\b'
            if re.fullmatch(pattern, t):
                return {"intent": None, "params": {}}

        if any(term == t for term in self.confirm_terms):
            return {"intent": "confirm_action", "params": {}}

        if any(term == t for term in self.deny_terms):
            return {"intent": "deny_action", "params": {}}

        for intent, phrases in self.basic_intents.items():
            if any(phrase in t for phrase in phrases):
                return {"intent": intent, "params": {}}

        for pattern in self.kill_process_patterns:
            m = re.search(pattern, t)
            if m:
                proc_name = m.group(1).strip()
                return {"intent": "kill_process", "params": {"process_name": proc_name}}

        for pattern in self.find_process_patterns:
            m = re.search(pattern, t)
            if m:
                val = m.group(1).strip()
                if val.isdigit():
                    return {"intent": "find_process", "params": {"pid": int(val)}}
                else:
                    if "pid" in pattern:
                        pass
                    elif "caminho" in pattern:
                        return {"intent": "find_process", "params": {"path": val}}
                    else:
                        return {"intent": "find_process", "params": {"name": val}}

        for pattern in self.filter_process_patterns:
            m = re.search(pattern, t)
            if m:
                if "cpu" in pattern:
                    cpu_threshold = int(m.group(1))
                    return {"intent": "filter_processes", "params": {"cpu_gt": cpu_threshold}}
                elif "ram" in pattern:
                    ram_threshold = int(m.group(1))
                    return {"intent": "filter_processes", "params": {"ram_lt": ram_threshold}}
                elif "nome" in pattern:
                    nome = m.group(1).strip()
                    return {"intent": "filter_processes", "params": {"name_contains": nome}}
                elif "pid" in pattern:
                    pid = int(m.group(1))
                    return {"intent": "filter_processes", "params": {"pid": pid}}
                elif "caminho" in pattern:
                    path = m.group(1).strip()
                    return {"intent": "filter_processes", "params": {"path_contains": path}}

        for pattern in self.process_exists_patterns:
            m = re.search(pattern, t)
            if m:
                app_name = m.group(1).strip()
                return {"intent": "process_exists", "params": {"app_name": app_name}}

        if any(term in t for term in self.heavy_process_terms):
            return {"intent": "list_heavy_processes", "params": {}}

        if any(term in t for term in self.disk_terms):
            if any(term in t for term in self.basic_intents["clean_temp"]):
                return {"intent": "clean_temp", "params": {}}
            else:
                return {"intent": "check_disk", "params": {}}

        return {"intent": None, "params": {}}
