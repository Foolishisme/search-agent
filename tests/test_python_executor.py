import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.python_executor import PythonExecutionError, WSLPythonExecutor


class FakeProcess:
    def __init__(self, *, stdout: bytes, stderr: bytes, returncode: int) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.killed = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


class WSLPythonExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.executor = WSLPythonExecutor(
            Path(self.tempdir.name),
            distro_name="Ubuntu-24.04",
            python_command="python3",
            timeout=5,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    async def test_execute_returns_result_and_deletes_temp_file(self):
        fake_process = FakeProcess(stdout=b"3\n", stderr=b"", returncode=0)

        with patch("app.python_executor.asyncio.create_subprocess_exec", return_value=fake_process) as create_mock:
            result = await self.executor.execute("print(1 + 2)")

        self.assertEqual(result.stdout, "3\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(list(Path(self.tempdir.name).glob("*.py")), [])
        args = create_mock.await_args.args
        self.assertEqual(args[0], "wsl")
        self.assertEqual(args[1], "-d")
        self.assertEqual(args[2], "Ubuntu-24.04")
        self.assertEqual(args[3], "sh")
        self.assertEqual(args[4], "-lc")
        self.assertIn("python3", args[5])
        self.assertIn("/mnt/", args[5])

    async def test_execute_raises_for_empty_code(self):
        with self.assertRaises(PythonExecutionError):
            await self.executor.execute("   ")
