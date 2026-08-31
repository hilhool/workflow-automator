"""Типизированные ошибки движка.

Каждая ошибка несёт код (для логов и API), человекочитаемое сообщение
и контекст — что именно выполнялось в момент сбоя.
"""


class WorkflowError(Exception):
    """Базовая ошибка движка. Не выбрасывается напрямую."""

    code = "WORKFLOW_ERROR"

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "context": self.context}

    def __str__(self) -> str:
        if not self.context:
            return self.message
        details = ", ".join(f"{key}={value!r}" for key, value in self.context.items())
        return f"{self.message} ({details})"


class ConfigError(WorkflowError):
    """Не хватает настройки в .env или значение невалидно."""

    code = "CONFIG_ERROR"


class DefinitionError(WorkflowError):
    """Некорректное описание воркфлоу в YAML."""

    code = "DEFINITION_ERROR"


class NodeNotFoundError(DefinitionError):
    """В YAML указан тип шага, которого нет в реестре."""

    code = "NODE_NOT_FOUND"


class TemplateError(WorkflowError):
    """Ошибка подстановки {{ ... }} в параметрах шага."""

    code = "TEMPLATE_ERROR"


class NodeExecutionError(WorkflowError):
    """Шаг упал во время выполнения."""

    code = "NODE_EXECUTION_ERROR"


class ClaudeError(NodeExecutionError):
    """Вызов Claude CLI завершился неуспешно."""

    code = "CLAUDE_ERROR"


class TelegramError(NodeExecutionError):
    """Ошибка при работе с Telegram."""

    code = "TELEGRAM_ERROR"


class TelegramAuthError(TelegramError):
    """Нет авторизованной сессии Telegram — нужен вход через scripts/tg_login.py."""

    code = "TELEGRAM_AUTH_ERROR"


class MoodleError(NodeExecutionError):
    """Ошибка при работе с Moodle."""

    code = "MOODLE_ERROR"


class MoodleAuthError(MoodleError):
    """Логин или пароль не подошли."""

    code = "MOODLE_AUTH_ERROR"


class MoodleWebServiceUnavailable(MoodleError):
    """Веб-сервисы Moodle закрыты — работаем через обычный вход на сайт."""

    code = "MOODLE_WS_UNAVAILABLE"


class MailError(NodeExecutionError):
    """Ошибка при работе с почтой по IMAP."""

    code = "MAIL_ERROR"


class MailAuthError(MailError):
    """Почтовый сервер не принял адрес или пароль."""

    code = "MAIL_AUTH_ERROR"
