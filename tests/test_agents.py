from app.services.agents import (
    ANSWER_NOT_FOUND,
    ANSWER_PROMPT,
    SCOPE_PROMPT,
    DocumentFragment,
    build_answer_context,
    parse_scope_verdict,
)


# uv run pytest -s tests/test_agents.py::test_build_answer_context_labels_documents
def test_build_answer_context_labels_documents() -> None:
    fragments = [
        DocumentFragment(document_name="doc-a", text="contenido A"),
        DocumentFragment(document_name="doc-b", text="contenido B"),
    ]

    context = build_answer_context(fragments)

    assert "[documento: doc-a]\ncontenido A" in context
    assert "[documento: doc-b]\ncontenido B" in context


# uv run pytest -s tests/test_agents.py::test_answer_prompt_includes_not_found_instruction
def test_answer_prompt_includes_not_found_instruction() -> None:
    prompt = ANSWER_PROMPT.format(context="ctx", query="q")
    assert ANSWER_NOT_FOUND in prompt
    assert "EXCLUSIVAMENTE" in prompt


# uv run pytest -s tests/test_agents.py::test_scope_prompt_embeds_scope_and_query
def test_scope_prompt_embeds_scope_and_query() -> None:
    prompt = SCOPE_PROMPT.format(scope="solo diagnósticos de vehículos", query="¿precio del oro?")
    assert "solo diagnósticos de vehículos" in prompt
    assert "¿precio del oro?" in prompt


# uv run pytest -s tests/test_agents.py::test_parse_scope_verdict_variants
def test_parse_scope_verdict_variants() -> None:
    assert parse_scope_verdict("TRUE") is True
    assert parse_scope_verdict("true.") is True
    assert parse_scope_verdict(" False ") is False
    assert parse_scope_verdict("FALSE.") is False
    assert parse_scope_verdict("no estoy seguro") is None
    assert parse_scope_verdict("") is None
