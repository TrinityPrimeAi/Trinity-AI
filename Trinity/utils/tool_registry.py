import shutil
from pathlib import Path


class ToolRegistry:
    def __init__(self, base_allowed=None):
        self.base_allowed = base_allowed or [
            str(Path.home()),
            str(Path.home() / "Desktop"),
            str(Path.home() / "Documents"),
            str(Path.home() / "Downloads"),
        ]

    # --------------------
    # Helpers / segurança
    # --------------------
    def _resolve_path(self, path: str) -> str:
        p = (path or "").strip()

        if p.lower() in ("desktop", "área de trabalho", "area de trabalho"):
            return str(Path.home() / "Desktop")
        if p.lower() in ("downloads", "download"):
            return str(Path.home() / "Downloads")
        if p.lower() in ("documents", "documentos", "docs"):
            return str(Path.home() / "Documents")

        return p

    def _is_allowed(self, path: str) -> bool:
        p = Path(path).resolve()
        for base in self.base_allowed:
            try:
                if str(p).startswith(str(Path(base).resolve())):
                    return True
            except Exception:
                continue
        return False

    # --------------------
    # Tools
    # --------------------
    def list_files(self, path: str):
        path = self._resolve_path(path)
        if not self._is_allowed(path):
            return {"error": "path_not_allowed", "path": path}

        p = Path(path)
        if not p.exists():
            return {"error": "path_not_found", "path": path}

        return {"path": path, "files": [f.name for f in p.iterdir()]}

    def count_files(self, path: str):
        path = self._resolve_path(path)
        if not self._is_allowed(path):
            return {"error": "path_not_allowed", "path": path}

        p = Path(path)
        if not p.exists():
            return {"error": "path_not_found", "path": path}

        return {"path": path, "count": len(list(p.iterdir()))}

    def read_text(self, path: str):
        path = self._resolve_path(path)
        if not self._is_allowed(path):
            return {"error": "path_not_allowed", "path": path}

        try:
            with open(path, "r", encoding="utf-8") as f:
                return {"path": path, "content": f.read()[:5000]}
        except Exception as e:
            return {"error": str(e), "path": path}

    def write_text(self, path: str, content: str):
        path = self._resolve_path(path)
        if not self._is_allowed(path):
            return {"error": "path_not_allowed", "path": path}

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content or "")
            return {"status": "written", "path": path}
        except Exception as e:
            return {"error": str(e), "path": path}

    def delete(self, path: str):
        path = self._resolve_path(path)
        if not self._is_allowed(path):
            return {"error": "path_not_allowed", "path": path}

        p = Path(path)
        if not p.exists():
            return {"error": "path_not_found", "path": path}

        try:
            if p.is_file():
                p.unlink()
            else:
                shutil.rmtree(p)
            return {"status": "deleted", "path": path}
        except Exception as e:
            return {"error": str(e), "path": path}

    def move(self, src: str, dst: str):
        src = self._resolve_path(src)
        dst = self._resolve_path(dst)

        if not self._is_allowed(src) or not self._is_allowed(dst):
            return {"error": "path_not_allowed", "src": src, "dst": dst}

        try:
            shutil.move(src, dst)
            return {"status": "moved", "src": src, "dst": dst}
        except Exception as e:
            return {"error": str(e), "src": src, "dst": dst}

    # --------------------
    # Dispatcher
    # --------------------
    def execute(self, tool: str, args: dict):
        args = args or {}

        if tool == "list_files":
            return self.list_files(**args)
        if tool == "count_files":
            return self.count_files(**args)
        if tool == "read_text":
            return self.read_text(**args)
        if tool == "write_text":
            return self.write_text(**args)
        if tool == "move":
            return self.move(**args)
        if tool == "delete":
            return self.delete(**args)

        return {"error": f"unknown_tool: {tool}", "args": args}
