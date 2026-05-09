from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Agent(Protocol):
    """단일 에이전트 계약. 구현체는 `name`과 비동기 `run`을 제공한다."""

    name: str

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]: ...
