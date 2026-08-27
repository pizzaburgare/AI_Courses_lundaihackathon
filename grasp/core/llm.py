"""The one place the pipeline talks to a model.

``ask_json`` is how every step gets structured data back. Nothing downstream parses a
model reply, so there is no regex, no fence stripping and no markdown format anywhere in
the pipeline: the schema is the contract and Pydantic validates it here.
"""

import os
from collections.abc import Callable

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from grasp.core.config import DEFAULT_MODEL, MODEL_ENV, OPENROUTER_URL

load_dotenv()

# A user message is either plain text or OpenAI-style content parts, which is how a PDF
# or an image reaches the model during ingest.
Content = str | list[str | dict[str, object]]


def model_name() -> str:
    """The model every call in this process uses. ``grasp --model`` sets the env var."""
    return os.getenv(MODEL_ENV) or DEFAULT_MODEL


def ask(system: str, user: Content) -> str:
    """One call, free text out. Used only where the answer is genuinely prose."""
    messages: list[BaseMessage] = [SystemMessage(content=system), HumanMessage(content=user)]
    client = ChatOpenAI(
        model=model_name(),
        api_key=SecretStr(os.getenv("OPENROUTER_API_KEY") or ""),
        base_url=OPENROUTER_URL,
    )
    return str(client.invoke(messages).content).strip()


def ask_json[T: BaseModel](system: str, user: Content, schema: type[T]) -> T:
    """One call, validated *schema* out. The only structured exchange format there is."""
    messages: list[BaseMessage] = [SystemMessage(content=system), HumanMessage(content=user)]
    client = ChatOpenAI(
        model=model_name(),
        api_key=SecretStr(os.getenv("OPENROUTER_API_KEY") or ""),
        base_url=OPENROUTER_URL,
    )
    result = client.with_structured_output(schema).invoke(messages)
    if not isinstance(result, schema):
        raise TypeError(f"expected {schema.__name__}, got {type(result).__name__}")
    return result


def ask_valid[T: BaseModel](
    system: str,
    user: str,
    schema: type[T],
    check: Callable[[T], list[str]],
    attempts: int = 3,
) -> T:
    """Ask for *schema* until *check* finds nothing to complain about.

    *check* returns a list of complaints, empty when the answer is acceptable. Each
    rejected answer is followed by a call that quotes the complaints, so a reply that is
    merely 200 words too long costs one more call instead of failing a whole course run.
    """
    problems: list[str] = []
    complaint = ""
    for _ in range(attempts):
        result = ask_json(system, user + complaint, schema)
        problems = check(result)
        if not problems:
            return result
        complaint = (
            "\n\n---\n\n# Your previous answer was rejected\n\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nAnswer again from the material above, fixing every point."
        )
    raise ValueError(
        f"{schema.__name__} was still invalid after {attempts} attempts:\n"
        + "\n".join(f"- {p}" for p in problems)
    )
