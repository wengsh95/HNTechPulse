import asyncio
from typing import Any, Coroutine


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine, handling the case where an event loop is already running.

    If no loop is running, uses asyncio.run(). If a loop is already running
    (e.g. inside Streamlit or Jupyter), spawns a new loop in a separate thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
