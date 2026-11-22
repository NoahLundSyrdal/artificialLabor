import pytest
from pydantic import BaseModel

from artificial_labor.llm import extract_code, extract_json


class Point(BaseModel):
    x: int
    y: int


def test_extract_json_handles_fences_and_chatter():
    assert extract_json('Sure!\n```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}
    assert extract_json('result: {"a": "}"} trailing') == {"a": "}"}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_extract_code_prefers_largest_block():
    text = "```python\nx = 1\n```\nand\n```python\nimport os\nprint(os.getcwd())\n```"
    assert extract_code(text).startswith("import os")
    assert extract_code("print(1)") == "print(1)\n"


def test_complete_model_retries_with_error_feedback(make_llm):
    replies = iter(['{"x": "not an int"}', '{"x": 1, "y": 2}'])
    llm = make_llm(lambda messages, model: next(replies))
    assert llm.complete_model([{"role": "user", "content": "go"}], Point) == Point(x=1, y=2)
    assert llm.usage.calls == 2
    # The validation error was fed back to the model.
    _, retry_messages = llm.backend.requests[1]
    assert "not valid" in retry_messages[-1]["content"]


def test_usage_rolls_up_from_child(make_llm):
    parent = make_llm(lambda m, model: "hi")
    child = parent.child()
    child.complete([{"role": "user", "content": "x"}], code=True)
    assert child.usage.calls == parent.usage.calls == 1
    # codestral: 1000 in * 0.3 + 500 out * 0.9 per 1M tokens
    assert parent.usage.cost_usd == pytest.approx((1000 * 0.3 + 500 * 0.9) / 1e6)


def test_extract_code_keeps_inner_fences_and_unclosed_blocks():
    reply = "Here:\n```python\nf.write('```sql\\n')\nprint(1)\n```\nDone."
    assert extract_code(reply) == "f.write('```sql\\n')\nprint(1)\n"
    assert extract_code("```python\nprint(1)\nprint(2") == "print(1)\nprint(2\n"
