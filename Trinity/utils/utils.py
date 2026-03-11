# analyzer/utils.py
import threading
from typing import Callable

def run_in_thread(fn: Callable, daemon: bool = True):
    t = threading.Thread(target=fn, daemon=daemon)
    t.start()
    return t
