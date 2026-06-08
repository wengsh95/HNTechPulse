import asyncio
import sys
from typing import Any, Coroutine


def _suppress_noisy_windows_disconnects(
    loop: asyncio.AbstractEventLoop, context: dict[str, Any]
) -> None:
    exc = context.get("exception")
    message = str(context.get("message", ""))

    if (
        sys.platform == "win32"
        and isinstance(exc, ConnectionResetError)
        and "_ProactorBasePipeTransport._call_connection_lost" in message
    ):
        return

    loop.default_exception_handler(context)


def _run_coro(coro: Coroutine[Any, Any, Any]) -> Any:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(_suppress_noisy_windows_disconnects)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine, handling the case where an event loop is already running.

    If no loop is running, uses asyncio.run(). If a loop is already running
    (e.g. inside Streamlit or Jupyter), spawns a new loop in a separate thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_coro(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_coro, coro).result()
