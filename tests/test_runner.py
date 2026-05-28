from bridge.runner import CommandRunner

import pytest


@pytest.mark.asyncio
async def test_runner_returns_error_when_executable_is_missing():
    result = await CommandRunner(executable="rotom-dex-missing-command-for-test").run(["version"])
    assert result.exit_code == 127
    assert "não encontrado" in result.stderr.lower()
