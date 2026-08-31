"""Перевод markdown в HTML, понятный Telegram."""

from integrations.markdown_html import markdown_to_telegram_html, split_message


def test_converts_bold_and_italic():
    assert markdown_to_telegram_html("**жирный** и *курсив*") == "<b>жирный</b> и <i>курсив</i>"


def test_escapes_raw_html():
    assert markdown_to_telegram_html("<script>alert(1)</script>").startswith("&lt;script&gt;")


def test_keeps_links():
    result = markdown_to_telegram_html("[Медуза](https://meduza.io)")
    assert result == '<a href="https://meduza.io">Медуза</a>'


def test_converts_headings_and_bullets():
    result = markdown_to_telegram_html("## Новости\n- первый\n- второй")
    assert "<b>Новости</b>" in result
    assert result.count("• ") == 2


def test_code_block_survives_escaping():
    result = markdown_to_telegram_html("```\nif a < b:\n    pass\n```")
    assert result.startswith("<pre>") and "a &lt; b" in result


def test_splits_long_text_by_paragraphs():
    text = "\n\n".join(["абзац" * 100] * 12)
    chunks = split_message(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)


def test_short_text_is_not_split():
    assert split_message("короткий текст") == ["короткий текст"]
