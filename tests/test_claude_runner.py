"""Сборка команды Claude CLI и передача промпта."""

from core.config import Settings
from integrations.claude_runner import ClaudeRequest, ClaudeRunner


def _runner() -> ClaudeRunner:
    return ClaudeRunner(Settings(_env_file=None, claude_bin="claude"))


def test_prompt_is_not_passed_as_argument():
    """Длинный промпт в командной строке ломает запуск: на Windows это WinError 206."""
    request = ClaudeRequest(prompt="ю" * 50_000)
    command = _runner()._build_command(request, "claude-haiku-4-5-20251001")
    assert request.prompt not in command
    assert max(len(part) for part in command) < 1000
    assert command[1] == "-p"


def test_economy_mode_disables_mcp_and_tools():
    command = _runner()._build_command(ClaudeRequest(prompt="привет"), "модель")
    assert "--strict-mcp-config" in command
    assert '{"mcpServers":{}}' in command


def test_tools_mode_reads_user_settings():
    request = ClaudeRequest(prompt="привет", tools=["mcp__claude_ai_Notion"])
    command = _runner()._build_command(request, "модель")
    assert "--strict-mcp-config" not in command
    assert "mcp__claude_ai_Notion" in command
    assert command[command.index("--setting-sources") + 1] == "user"


def test_absolute_binary_is_used_as_is():
    runner = ClaudeRunner(Settings(_env_file=None, claude_bin="/opt/bin/claude"))
    assert runner._executable() == "/opt/bin/claude"


def test_subprocess_env_normalizes_proxy_variables():
    """CLI читает окружение сам — унаследованный socks4 увёл бы его в никуда."""
    from core.net import subprocess_env

    settings = Settings(_env_file=None, telegram_proxy="http://proxy:3128")
    environment = subprocess_env(settings)
    assert environment["HTTP_PROXY"] == "http://proxy:3128"
    assert environment["HTTPS_PROXY"] == "http://proxy:3128"
    assert "ALL_PROXY" not in environment
