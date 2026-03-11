

import os
import time
import psutil
import json
import logging
from typing import Any, Dict, List, Optional

from sys_actions import clean_ram 

logger = logging.getLogger("Monitor")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "analyzer_settings.json")
if not os.path.exists(SETTINGS_PATH):
    DEFAULT_SETTINGS = {
        "diagnostic_mode": {
            "autonomy": "B2",
            "auto_scan_interval": 8,
            "mem_threshold": 85,
            "disk_threshold": 92,
            "cpu_threshold": 90
        }
    }
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

try:
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        SETTINGS = json.load(f)
except Exception:
    SETTINGS = {}

DIAG = SETTINGS.get("diagnostic_mode", {})
AUTONOMY = DIAG.get("autonomy", "B2")  # B2 = Permissão para executar, B3 = Ação autônoma
INTERVAL_DEFAULT = DIAG.get("auto_scan_interval", 8)


class SystemMonitor:
    def __init__(self, queue: Optional[Any] = None, interval: Optional[float] = None):
        self.queue = queue
        self.interval = interval if interval is not None else INTERVAL_DEFAULT
        self.cpu_threshold = DIAG.get("cpu_threshold", 90)
        self.mem_threshold = DIAG.get("mem_threshold", 85)
        self.disk_threshold = DIAG.get("disk_threshold", 92)
        self._running = False
        self._last_emit_ts = 0.0
        self.cooldown = 6.0  
        self.action_history: List[Dict[str, Any]] = []

    def start_monitoring(self):
        logger.info(f"[Monitor] starting monitor (autonomy={AUTONOMY}) interval={self.interval}s")
        self._running = True
        time.sleep(0.5)
        while self._running:
            try:
                self._check_once()
            except Exception as e:
                logger.exception(f"[Monitor] loop error: {e}")
                self._emit("monitor_log", f"monitor loop error: {e}")
            time.sleep(self.interval)

    def stop(self):
        self._running = False

    def _check_once(self):
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent

        disk = 0.0
        tried_paths = []
        try:
            path = os.path.expanduser("~")
            tried_paths.append(path)
            disk = psutil.disk_usage(path).percent
        except Exception:
            try:
                path2 = "/"
                tried_paths.append(path2)
                disk = psutil.disk_usage(path2).percent
            except Exception:
                try:
                    path3 = "C:\\"
                    tried_paths.append(path3)
                    disk = psutil.disk_usage(path3).percent
                except Exception:
                    disk = 0.0

        top_procs = self._get_top_processes(6)
        now = time.time()

        if now - self._last_emit_ts >= self.cooldown:
            self._emit("monitor_status", {"cpu": cpu, "mem": mem, "disk": disk})
            self._last_emit_ts = now

        if cpu >= self.cpu_threshold or mem >= self.mem_threshold or disk >= self.disk_threshold:
            detail = {"cpu": cpu, "mem": mem, "disk": disk, "top_procs": top_procs}
            self._emit("monitor_alert", detail)

            if AUTONOMY == "B3":
                self._mitigate_critical(detail)
        else:
            if disk >= (self.disk_threshold - 6):
                self._emit("monitor_suggest", {"suggest": "clean_temp", "disk": disk, "top_procs": top_procs})
            if mem >= (self.mem_threshold - 6) and AUTONOMY == "B3":
                self._auto_free_memory(top_procs)

        if mem >= self.mem_threshold:
            if AUTONOMY == "B3":
                result = clean_ram()
                self._emit("monitor_autofix", {"action": "clean_ram", "result": result})

    def _get_top_processes(self, n: int = 5) -> List[Dict[str, Any]]:
        procs = []
        for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                cpu_p = info.get("cpu_percent")
                mem_p = info.get("memory_percent")
                if cpu_p is None:
                    cpu_p = p.cpu_percent(interval=None)
                if mem_p is None:
                    mem_p = p.memory_percent()
                procs.append({
                    "pid": int(info.get("pid") or 0),
                    "name": str(info.get("name") or "")[:120],
                    "cpu_percent": float(cpu_p or 0.0),
                    "memory_percent": float(mem_p or 0.0)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception:
                continue
        procs_sorted = sorted(procs, key=lambda x: (x.get("cpu_percent", 0.0) or 0.0) + (x.get("memory_percent", 0.0) or 0.0), reverse=True)
        return procs_sorted[:n]

    def _emit(self, typ: str, payload: Any):
        try:
            if self.queue:
                safe_payload = payload
                if isinstance(payload, dict):
                    safe_payload = {}
                    for k, v in payload.items():
                        try:
                            import json
                            json.dumps({k: v})
                            safe_payload[k] = v
                        except Exception:
                            safe_payload[k] = str(v)
                self.queue.put((typ, safe_payload))
        except Exception:
            logger.exception("failed to emit event to queue")

    # ---------- Mitigations (for AUTONOMY B3) ----------
    def _mitigate_critical(self, detail: Dict[str, Any]):
       
        top = detail.get("top_procs", [])
        if not top:
            return
        candidate = None
        for p in top:

            name = (p.get("name") or "").lower()
            pid = int(p.get("pid") or 0)
            if pid <= 4:
                continue
            if "idle" in name or "system" in name:
                continue
            candidate = p
            break
        if not candidate:
            return
        pid = int(candidate.get("pid"))
        try:
            ok, msg = self.kill_process(pid)
            action = {"when": time.time(), "action": "kill_process", "pid": pid, "result": ok, "msg": msg}
            self.action_history.append(action)
            self._emit("monitor_action", action)
        except Exception as e:
            logger.exception(f"mitigate error: {e}")
            self._emit("monitor_log", f"mitigate error: {e}")

    # ---------- Auto free memory helper ----------
    def _auto_free_memory(self, top_procs: List[Dict[str, Any]]):
        try:
            res = self.free_memory()
            self._emit("monitor_action", {"action": "free_memory", "result": res})
        except Exception as e:
            logger.exception(f"auto free memory failed: {e}")
            self._emit("monitor_log", f"auto free memory failed: {e}")

    # ---------- Public utility actions ----------
    def kill_process(self, pid: int):
        try:
            p = psutil.Process(int(pid))
            name = p.name()
            p.terminate()
            gone, alive = psutil.wait_procs([p], timeout=3)
            if alive:
                try:
                    p.kill()
                except Exception:
                    pass
            return True, f"Processo {name} (PID {pid}) terminado."
        except psutil.NoSuchProcess:
            return False, f"Processo {pid} não encontrado."
        except Exception as e:
            return False, f"Falha ao terminar PID {pid}: {e}"

    def clean_temp_folder(self, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        import shutil
        if paths is None:
            if os.name == "nt":
                paths = [os.environ.get("TEMP", ""), os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp")]
            else:
                paths = ["/tmp"]
        removed = []
        failed = []
        for base in paths:
            if not base or not os.path.exists(base):
                continue
            try:
                for name in os.listdir(base):
                    fp = os.path.join(base, name)
                    try:
                        if os.path.isfile(fp) or os.path.islink(fp):
                            os.remove(fp)
                            removed.append(fp)
                        elif os.path.isdir(fp):
                            shutil.rmtree(fp, ignore_errors=True)
                            removed.append(fp)
                    except Exception as e:
                        failed.append({"path": fp, "error": str(e)})
            except Exception as e:
                failed.append({"path": base, "error": str(e)})
        return {"removed": removed, "failed": failed}

    def free_memory(self) -> Dict[str, Any]:
       
        result = {"action": None, "ok": False, "detail": None}
        try:
            if os.name == "posix" and os.path.exists("/proc/sys/vm/drop_caches"):
                try:
                    import subprocess
                    subprocess.run(["sync"], check=False)
                    with open("/proc/sys/vm/drop_caches", "w") as f:
                        f.write("3\n")
                    result["action"] = "drop_caches"
                    result["ok"] = True
                except Exception as e:
                    result["detail"] = f"drop_caches failed: {e}"
                    result["ok"] = False
            elif os.name == "nt":
                try:
                    import ctypes
                    PROCESS_SET_QUOTA = 0x0100
                    psapi = ctypes.windll.psapi
                    kernel32 = ctypes.windll.kernel32
                    cleaned = 0
                    for proc in psutil.process_iter(attrs=["pid"]):
                        pid = int(proc.info.get("pid") or 0)
                        try:
                            h = kernel32.OpenProcess(PROCESS_SET_QUOTA, False, pid)
                            if h:
                                try:
                                    psapi.EmptyWorkingSet(h)
                                    cleaned += 1
                                except Exception:
                                    pass
                                kernel32.CloseHandle(h)
                        except Exception:
                            continue
                    result["action"] = "empty_working_set"
                    result["ok"] = True
                    result["detail"] = {"processes_touched": cleaned}
                except Exception as e:
                    result["detail"] = f"windows free memory noop failed: {e}"
                    result["ok"] = False
            else:
                result["action"] = "noop"
                result["ok"] = False
        except Exception as e:
            result["detail"] = str(e)
            result["ok"] = False
        return result
