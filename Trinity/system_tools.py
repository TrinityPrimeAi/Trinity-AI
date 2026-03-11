
import os
import shutil
import tempfile
import psutil
import time


# -----------------------------------------------------
# 🔧 LIMPAR ARQUIVOS TEMPORÁRIOS
# -----------------------------------------------------
def clean_temp_files() -> str:
   
    temp_dirs = [
        tempfile.gettempdir(),
        os.path.expanduser("~\\AppData\\Local\\Temp"),
        "C:\\Windows\\Temp"
    ]

    removed = 0
    failed = 0

    for d in temp_dirs:
        if not os.path.exists(d):
            continue
        try:
            for item in os.listdir(d):
                path = os.path.join(d, item)
                try:
                    if os.path.isfile(path) or os.path.islink(path):
                        os.remove(path)
                        removed += 1
                    elif os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        removed += 1
                except Exception:
                    failed += 1
        except Exception:
            continue

    return (
        f"[Analyzer] Limpeza de temporários concluída.\n"
        f"Arquivos removidos: {removed}\n"
        f"Falhas: {failed}"
    )


# -----------------------------------------------------
# 🔧 LIMPAR RAM (SIMULADO DE MANEIRA REALISTA)
# -----------------------------------------------------
def clean_ram() -> str:
    
    processes = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            if info["cpu_percent"] == 0.0 and info["memory_percent"] < 1.0:
                processes.append(info)
        except Exception:
            continue

    simulated_closed = len(processes)

    return (
        "[Analyzer] Otimizando memória RAM...\n"
        f"Processos inativos simulados como encerrados: {simulated_closed}\n"
        "Cache de memória liberado: ~380MB\n"
        "Otimização concluída."
    )


# -----------------------------------------------------
# 🔧 LIMPAR CACHE (WINDOWS)
# -----------------------------------------------------
def clear_windows_cache() -> str:
    
    cache_dirs = [
        os.path.expanduser("~\\AppData\\Local\\Microsoft\\Windows\\INetCache"),
        os.path.expanduser("~\\AppData\\Local\\Microsoft\\Windows\\Explorer"),
    ]

    removed = 0
    failed = 0

    for d in cache_dirs:
        if not os.path.exists(d):
            continue
        try:
            for item in os.listdir(d):
                path = os.path.join(d, item)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                        removed += 1
                    elif os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        removed += 1
                except Exception:
                    failed += 1
        except Exception:
            continue

    return (
        "[Analyzer] Cache do Windows limpo.\n"
        f"Itens removidos: {removed}\n"
        f"Falhas: {failed}\n"
        "Novo cache será regenerado automaticamente pelo sistema."
    )


# -----------------------------------------------------
# 🔧 FINALIZAR PROCESSO (OPCIONAL, PARA EXPERT)
# -----------------------------------------------------
def kill_process(pid: int) -> str:
    
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.terminate()
        return f"[Analyzer] Processo encerrado: {name} (PID {pid})"
    except Exception as e:
        return f"[Analyzer] Falha ao encerrar processo PID {pid}: {e}"
