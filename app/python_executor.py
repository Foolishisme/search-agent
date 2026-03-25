import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


class PythonExecutionError(RuntimeError):
    pass


@dataclass
class PythonExecutionResult:
    stdout: str
    stderr: str
    exit_code: int | None


class WSLPythonExecutor:
    def __init__(
        self,
        temp_dir: Path,
        *,
        distro_name: str | None = None,
        python_command: str = "python3",
        timeout: float = 30.0,
    ) -> None:
        self.temp_dir = Path(temp_dir)
        self.distro_name = (distro_name or "").strip() or None
        self.python_command = python_command.strip() or "python3"
        self.timeout = timeout

    async def execute(self, code: str) -> PythonExecutionResult:
        normalized_code = code.strip()
        if not normalized_code:
            raise PythonExecutionError("Python code cannot be empty")

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        script_path = self.temp_dir / f"python_exec_{uuid4().hex}.py"
        script_path.write_text(normalized_code, encoding="utf-8")

        try:
            process = await asyncio.create_subprocess_exec(
                *self._build_command(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise PythonExecutionError(f"Python execution timed out after {self.timeout:.0f}s") from exc

            return PythonExecutionResult(
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                exit_code=process.returncode,
            )
        except FileNotFoundError as exc:
            raise PythonExecutionError("WSL is not available on this machine") from exc
        finally:
            script_path.unlink(missing_ok=True)

    def _build_command(self, script_path: Path) -> list[str]:
        python_command = shlex.quote(self.python_command)
        wsl_script_path = shlex.quote(self._windows_path_to_wsl(script_path))
        command = [
            "wsl",
        ]
        if self.distro_name:
            command.extend(["-d", self.distro_name])
        command.extend([
            "sh",
            "-lc",
            f"{python_command} {wsl_script_path}",
        ])
        return command

    @staticmethod
    def _windows_path_to_wsl(path: Path) -> str:
        resolved = path.resolve()
        drive = resolved.drive.rstrip(":").lower()
        if not drive:
            raise PythonExecutionError("Only Windows drive paths can be converted to WSL paths")
        posix_path = resolved.as_posix()
        prefix = f"{resolved.drive}/"
        if not posix_path.startswith(prefix):
            raise PythonExecutionError("Unable to convert path to WSL path")
        tail = posix_path[len(prefix):]
        return f"/mnt/{drive}/{tail}"
