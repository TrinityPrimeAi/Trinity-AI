
import platform
import psutil
import shutil
import subprocess
import json
import os
import time

try:
    import GPUtil  # type: ignore
    _has_gputil = True
except Exception:
    _has_gputil = False

try:
    import wmi  # type: ignore
    _has_wmi = True
except Exception:
    _has_wmi = False
    


def _get_cpu_info():
    cpu = {"name": None, "cores": psutil.cpu_count(logical=False), "threads": psutil.cpu_count(logical=True)}
    try:
        if _has_wmi and platform.system() == "Windows":
            c = wmi.WMI()
            for proc in c.Win32_Processor():
                cpu["name"] = proc.Name.strip() if proc.Name else None
                cpu["max_clock_mhz"] = getattr(proc, "MaxClockSpeed", None)
                cpu["current_clock_mhz"] = getattr(proc, "CurrentClockSpeed", None)
                break
    except Exception:
        pass

    if not cpu.get("name"):
        uname = platform.uname()
        cpu["name"] = uname.processor or uname.machine or platform.platform()
    return cpu


def _get_ram_info():
    vm = psutil.virtual_memory()
    total_gb = vm.total / (1024 ** 3)
    ram = {"total_gb": round(total_gb, 2), "used_percent": round(vm.percent, 1)}
    # tenta obter detalhes de módulos via wmi (Windows)
    if _has_wmi and platform.system() == "Windows":
        try:
            c = wmi.WMI()
            banks = []
            for mem in c.Win32_PhysicalMemory():
                banks.append({
                    "capacity_gb": round(int(mem.Capacity) / (1024 ** 3), 2) if getattr(mem, "Capacity", None) else None,
                    "speed_mhz": getattr(mem, "Speed", None),
                    "manufacturer": getattr(mem, "Manufacturer", None),
                    "part_number": getattr(mem, "PartNumber", None)
                })
            if banks:
                ram["modules"] = banks
        except Exception:
            pass
    return ram


def _get_disk_info():
    try:
        usage = psutil.disk_usage(os.path.expanduser("~"))
        return {"used_percent": usage.percent, "total_gb": round(usage.total / (1024 ** 3), 2)}
    except Exception:
        return {}


def _get_gpu_info():
    gpus = []
    try:
        if _has_gputil:
            gpus_raw = GPUtil.getGPUs()
            for g in gpus_raw:
                gpus.append({
                    "name": g.name,
                    "total_memory_mb": g.memoryTotal,
                    "load_percent": round(g.load * 100, 1)
                })
        elif platform.system() == "Windows":
            # fallback via wmic
            try:
                out = subprocess.check_output("wmic path win32_VideoController get name,AdapterRAM /format:csv", shell=True, stderr=subprocess.DEVNULL, timeout=5)
                text = out.decode(errors="ignore").strip()
                lines = [l for l in text.splitlines() if l.strip()]
                # skip header
                for l in lines[1:]:
                    parts = [p for p in l.split(",") if p.strip()]
                    if parts:
                        # last field usually Name
                        name = parts[-1]
                        gpus.append({"name": name})
            except Exception:
                pass
    except Exception:
        pass
    return gpus


def _get_network_info():
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        result = {}
        for ifname, addrlist in addrs.items():
            result[ifname] = {
                "addresses": [a.address for a in addrlist if getattr(a, "address", None)],
                "is_up": stats.get(ifname).isup if stats.get(ifname) else None,
                "speed_mbps": stats.get(ifname).speed if stats.get(ifname) else None
            }
        return result
    except Exception:
        return {}


def get_hardware_summary():
    
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": _get_cpu_info(),
        "ram": _get_ram_info(),
        "disk": _get_disk_info(),
        "gpus": _get_gpu_info(),
        "net": _get_network_info(),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    return info


def summary_to_text(summary: dict) -> str:
    sep_big = "=" * 60
    sep = "-" * 60
    lines = []

    # Cabeçalho
    lines.append(sep_big)
    lines.append("                 Trinity – RESUMO DE HARDWARE")
    lines.append(sep_big)
    lines.append("")
    lines.append(f"DATA DE GERAÇÃO: {summary.get('timestamp')}")
    lines.append(f"SISTEMA: {summary.get('platform')}")
    lines.append(f"ARQUITETURA: {summary.get('machine')}")
    lines.append("")

    # CPU
    cpu = summary.get("cpu", {})
    lines.append(sep)
    lines.append("CPU")
    lines.append(sep)
    lines.append(f"Nome: {cpu.get('name')}")
    lines.append(f"Cores físicos: {cpu.get('cores')}")
    lines.append(f"Threads: {cpu.get('threads')}")
    if cpu.get("max_clock_mhz"):
        lines.append(f"Clock Máximo: {cpu.get('max_clock_mhz')} MHz")
    if cpu.get("current_clock_mhz"):
        lines.append(f"Clock Atual: {cpu.get('current_clock_mhz')} MHz")
    lines.append("")

    # RAM
    ram = summary.get("ram", {})
    lines.append(sep)
    lines.append("MEMÓRIA RAM")
    lines.append(sep)
    lines.append(f"Total: {ram.get('total_gb')} GB")
    lines.append(f"Uso atual: {ram.get('used_percent')}%")
    lines.append("")
    modules = ram.get("modules")
    if modules:
        lines.append("Módulos instalados:")
        for m in modules:
            lines.append(
                f"  • {m.get('capacity_gb')} GB | "
                f"{m.get('speed_mhz')} MHz | "
                f"{m.get('manufacturer').strip()} | "
                f"{m.get('part_number')}"
            )
        lines.append("")

    # DISCO
    disk = summary.get("disk", {})
    lines.append(sep)
    lines.append("DISCO")
    lines.append(sep)
    lines.append(f"Total: {disk.get('total_gb')} GB")
    lines.append(f"Uso: {disk.get('used_percent')}%")
    lines.append("")

    # GPU
    lines.append(sep)
    lines.append("GPU")
    lines.append(sep)
    gpus = summary.get("gpus", [])
    if gpus:
        for g in gpus:
            lines.append(
                f"  • {g.get('name')} "
                f"(VRAM: {g.get('total_memory_mb', '?')} MB, Load: {g.get('load_percent','?')}%)"
            )
    else:
        lines.append("Nenhuma GPU detectada via GPUtil/WMIC.")
    lines.append("")

    # Rede
    net = summary.get("net", {})
    lines.append(sep)
    lines.append("REDE")
    lines.append(sep)
    for ifname, d in net.items():
        lines.append(f"Interface: {ifname}")
        lines.append(f"  Ativa: {'Sim' if d.get('is_up') else 'Não'}")
        lines.append(f"  Velocidade: {d.get('speed_mbps')} Mbps")
        lines.append("  Endereços:")
        for addr in d.get("addresses", []):
            lines.append(f"    • {addr}")
        lines.append("")

    lines.append(sep_big)
    return "\n".join(lines)



def dump_full_wmi_raw(output_path: str, timeout: int = 300) -> str:
    """
    Gera um dump *completo* do WMI usando PowerShell e salva em output_path (txt).
    Retorna caminho do arquivo salvo ou exceção.
    OBS: somente Windows. Pode demorar MUITO e gerar arquivo grande.
    """
    if platform.system() != "Windows":
        raise RuntimeError("Dump full WMI está disponível apenas no Windows.")

    # PowerShell heavy script: lista classes e faz Get-WmiObject em cada
    ps_script = r'''
$ErrorActionPreference = "SilentlyContinue"
Get-WmiObject -List | ForEach-Object {
  $class = $_.Name
  try {
    Write-Output "== $class =="
    Get-WmiObject -Class $class | ForEach-Object {
      $_ | Format-List * -Force
      Write-Output "`n"
    }
  } catch {
    Write-Output "== ERRO no class $class =="
  }
}
'''
    # Executa PowerShell
    cmd = ["powershell", "-NoProfile", "-Command", ps_script]
    with open(output_path, "w", encoding="utf-8", errors="ignore") as fout:
        proc = subprocess.Popen(cmd, stdout=fout, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(f"Dump WMI excedeu o tempo limite de {timeout}s. Arquivo parcial salvo em {output_path}")

    return output_path

def get_all_common_info():
    
    return get_hardware_summary()


def save_summary_txt(path: str):
    summary = get_hardware_summary()
    text = summary_to_text(summary) 
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# =====================================================================
#                    🔵 NOVA FUNÇÃO notify_hardware()
# =====================================================================

def notify_hardware(cpu_info, ram_info, disk_info, net_info, gpus, mode="A"):
    """
    Notificação A = EXTREMAMENTE detalhada (uso total do hardware)
    Notificação B = Detalhada, porém mais organizada e elegante (recomendada)
    Notificação C = Resumida
    """

    # ---------------------
    # 🔸 Modo C (resumo)
    # ---------------------
    if mode == "C":
        return f"""
[Hardware Info — Resumo]
CPU: {cpu_info.get('name')}
RAM: {ram_info.get('total_gb')} GB
DISK: {disk_info.get('total_gb')} GB (usado {disk_info.get('used_percent')}%)
"""

    # ---------------------
    # 🔸 Modo A (completo)
    # ---------------------
    if mode == "A":
        return f"""
[Hardware Info — Modo Completo]

CPU
- Nome: {cpu_info.get('name')}
- Núcleos: {cpu_info.get('cores')}
- Threads: {cpu_info.get('threads')}
- Clock Máx: {cpu_info.get('max_clock_mhz')} MHz
- Clock Atual: {cpu_info.get('current_clock_mhz')} MHz

RAM
- Total: {ram_info.get('total_gb')} GB
- Uso: {ram_info.get('used_percent')}%
- Módulos: {ram_info.get('modules')}

DISCO
- Total: {disk_info.get('total_gb')} GB
- Uso: {disk_info.get('used_percent')}%

REDE
{net_info}

GPUs
{gpus}
"""

    # ---------------------
    # 🔵 Modo B (seu padrão)
    # ---------------------
    return f"""
[Hardware Info — Notificação B]

CPU
 • {cpu_info.get('name')}
 • {cpu_info.get('cores')}C / {cpu_info.get('threads')}T
 • {cpu_info.get('current_clock_mhz')} MHz / {cpu_info.get('max_clock_mhz')} MHz

RAM
 • Total: {ram_info.get('total_gb')} GB
 • Uso: {ram_info.get('used_percent')}%
 • Módulos detectados: {len(ram_info.get('modules', []))}

Disco
 • Total: {disk_info.get('total_gb')} GB
 • Uso: {disk_info.get('used_percent')}%

Rede
 • Interfaces: {len(net_info)}

GPU
 • Detectadas: {len(gpus)}
"""
