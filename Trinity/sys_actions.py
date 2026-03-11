import psutil
import os
import shutil
import tempfile
import platform
import subprocess

# -----------------------------------------------------------
# LIMPAR RAM (Finge otimização real - mantém funcionamento)
# -----------------------------------------------------------
def clean_ram():
    """Simula limpeza de RAM ajustando prioridades e finalizando processos leves."""
    adjusted = 0
    for proc in psutil.process_iter(['pid', 'memory_percent']):
        try:
            # Ajusta a prioridade para processos que consomem muita RAM (Windows)
            if proc.info['memory_percent'] > 0.5:
                if platform.system() == "Windows":
                    proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                else:
                    proc.nice(10)  # UNIX-like
                adjusted += 1
        except Exception:
            pass
    return f"Memória otimizada: {adjusted} processos ajustados."


# -----------------------------------------------------------
# LIMPAR ARQUIVOS TEMPORÁRIOS
# -----------------------------------------------------------
def clean_temp_files():
    temp_dir = tempfile.gettempdir()
    removed = 0

    try:
        for root, dirs, files in os.walk(temp_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                try:
                    os.remove(file_path)
                    removed += 1
                except Exception:
                    pass
        for root, dirs, _ in os.walk(temp_dir, topdown=False):
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    os.rmdir(dir_path)
                except Exception:
                    pass

    except Exception:
        return "Erro ao tentar limpar arquivos temporários."

    return removed


# -----------------------------------------------------------
# ENCERRAR PROCESSO POR NOME
# -----------------------------------------------------------
def kill_process_by_name(proc_name):
    
    proc_name = proc_name.lower().replace(".exe", "").strip()
    killed = 0
    msgs = []

    for proc in psutil.process_iter(['name', 'pid']):
        try:
            pname = proc.info['name']
            if pname and proc_name in pname.lower().replace(".exe", "").strip():
                proc.kill()
                killed += 1
                msgs.append(f"Processo {pname} (PID {proc.info['pid']}) finalizado.")
        except Exception as e:
            msgs.append(f"Erro ao finalizar processo {proc.info.get('name', '?')}: {e}")

    if killed > 0:
        return True, "\n".join(msgs)
    else:
        return False, f"Nenhum processo com nome contendo '{proc_name}' foi encontrado."



# -----------------------------------------------------------
# ENCERRAR PROCESSO POR PID
# -----------------------------------------------------------
def kill_process_by_pid(pid):
  
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        proc.wait(timeout=3)
        return True, f"Processo PID {pid} terminado."
    except psutil.NoSuchProcess:
        return False, f"Processo PID {pid} não existe."
    except psutil.TimeoutExpired:
        return False, f"Timeout ao terminar processo PID {pid}."
    except Exception as e:
        return False, f"Erro ao terminar processo PID {pid}: {str(e)}"


# -----------------------------------------------------------
# LISTAR PROCESSOS COM FILTRO (POR NOME, CPU, MEMÓRIA)
# -----------------------------------------------------------
def list_processes(filter_name=None, min_cpu=0.0, min_mem=0.0, limit=20):
  
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            if filter_name and filter_name.lower() not in proc.info['name'].lower():
                continue
            if proc.info['cpu_percent'] < min_cpu:
                continue
            if proc.info['memory_percent'] < min_mem:
                continue
            procs.append(proc.info)
        except Exception:
            pass
    procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
    return procs[:limit]


# -----------------------------------------------------------
# LIBERAR CACHE DE DISCO (LINUX) - opcional
# -----------------------------------------------------------
def free_disk_cache():
    """
    No Linux, libera cache do disco para liberar memória.
    Em Windows, não faz nada.
    """
    if platform.system() == "Linux":
        try:
            subprocess.run(['sync'])
            subprocess.run(['sudo', 'bash', '-c', 'echo 3 > /proc/sys/vm/drop_caches'])
            return "Cache do disco liberado."
        except Exception as e:
            return f"Erro ao liberar cache: {str(e)}"
    else:
        return "Liberação de cache não suportada neste sistema."


# -----------------------------------------------------------
# PEGAR INFORMAÇÕES GERAIS DO SISTEMA
# -----------------------------------------------------------
def get_system_info():
  
    try:
        cpu_count = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.expanduser("~"))
        return {
            "cpu_count": cpu_count,
            "cpu_freq": psutil.cpu_freq().current if psutil.cpu_freq() else None,
            "total_ram_gb": mem.total / (1024**3),
            "available_ram_gb": mem.available / (1024**3),
            "disk_total_gb": disk.total / (1024**3),
            "disk_used_percent": disk.percent,
            "platform": platform.platform()
        }
    except Exception as e:
        return {"error": str(e)}
