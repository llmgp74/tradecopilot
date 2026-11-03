"""Memory configuration and storage contract."""

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

MemoryCondition = Literal["none", "prose", "structured", "full"]


@runtime_checkable
class MemoryStore(Protocol):
    """Persists the user profile and the append-only decision journal."""


class MemoryConfig(BaseModel):
    """Selects the memory condition and the store the agent reads from.

    Attributes:
        condition: Which memory content is injected into the agent.
        store: Backing store. The live app uses the SQLite store against the
            user database; each eval run passes its own database.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    condition: MemoryCondition = "full"
    store: MemoryStore
