import json
import logging

from llm_central_gateway.logging import JsonFormatter


def test_json_formatter_redacts_nested_secrets() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "done", (), None)
    record.event = "test.complete"
    record.data = {"nested": {"Authorization": "Bearer secret"}, "safe": "visible"}
    payload = json.loads(JsonFormatter(100).format(record))
    assert payload["data"]["nested"]["Authorization"] == "[REDACTED]"
    assert payload["data"]["safe"] == "visible"
