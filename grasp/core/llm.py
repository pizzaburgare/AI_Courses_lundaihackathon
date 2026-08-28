"""The one place the pipeline talks to a model.

``ask_json`` is how every step gets structured data back. Nothing downstream parses a
model reply, so there is no regex, no fence stripping and no markdown format anywhere in
the pipeline: the schema is the contract and Pydantic validates it here. A reply that
fails that validation is a rejected answer inside :func:`ask_valid`, not an exception the
pipeline has to survive.
"""

import os
from collections.abc import Callable

from dotenv import load_dotenv
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr, ValidationError

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


def ask_json[T: BaseModel](system: str, user: Content, schema: type[T], model: str = "") -> T:
    """One call, validated *schema* out. The only structured exchange format there is.

    *model* overrides the run's model for this one call. Ingest uses it to read a PDF
    with a model that has eyes, whatever text model the rest of the run is on.
    """
    messages: list[BaseMessage] = [SystemMessage(content=system), HumanMessage(content=user)]
    client = ChatOpenAI(
        model=model or model_name(),
        api_key=SecretStr(os.getenv("OPENROUTER_API_KEY") or ""),
        base_url=OPENROUTER_URL,
    )
    # method="function_calling", not the default: on a full-size scene prompt the
    # json_schema path makes Kimi emit its reasoning ahead of the object, and the reply
    # fails to parse as JSON. Tool calling is the only mode every model here honours.
    result = client.with_structured_output(schema, method="function_calling").invoke(messages)
    if not isinstance(result, schema):
        raise TypeError(f"expected {schema.__name__}, got {type(result).__name__}")
    return result


def ask_valid[T: BaseModel](
    system: str,
    user: str,
    schema: type[T],
    check: Callable[[T], list[str]],
    attempts: int = 3,
    model: str = "",
) -> T:
    """Ask for *schema* until *check* finds nothing to complain about.

    *check* returns a list of complaints, empty when the answer is acceptable. Each
    rejected answer is followed by a call that quotes the complaints, so a reply that is
    merely 200 words too long costs one more call instead of failing a whole course run.

    *model* overrides the run's model for every attempt, the way it does in
    :func:`ask_json`. The scene step uses it to write Python with a code model.

    A reply that cannot be read as *schema* at all spends an attempt like any other
    rejected answer, rather than ending the step. Some models narrate their reasoning
    ahead of the object they were asked for, and one such reply must not cost a whole
    course run.
    """
    problems: list[str] = []
    complaint = ""
    for _ in range(attempts):
        try:
            result = ask_json(system, user + complaint, schema, model)
        except (ValidationError, OutputParserException, TypeError) as err:
            problems = [
                (
                    f"the reply could not be read as {schema.__name__}: "
                    f"{str(err).splitlines()[0]}. Answer with the object alone - no "
                    f"reasoning, no prose and no markdown fence before or after it."
                )
            ]
        else:
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
