# coding: utf-8

import asyncio
import os
import threading
import typing as t
from concurrent.futures import CancelledError, ThreadPoolExecutor
from functools import wraps, partial
from logHandler import log
from .helpers import import_bundled_library



THREADED_EXECUTOR = None
ASYNCIO_EVENT_LOOP = asyncio.new_event_loop()
ASYNCIO_LOOP_THREAD = None


def initialize():
    global THREADED_EXECUTOR, ASYNCIO_EVENT_LOOP, ASYNCIO_LOOP_THREAD

    THREADED_EXECUTOR = ThreadPoolExecutor(
        max_workers=os.cpu_count() // 2, thread_name_prefix="piper4nvda_executor"
    )

    if ASYNCIO_LOOP_THREAD:
        log.warning(
            "Attempted to start the asyncio eventloop while it is already running"
        )
        return

    def _thread_target():
        log.info("Starting asyncio event loop")
        asyncio.set_event_loop(ASYNCIO_EVENT_LOOP)
        ASYNCIO_EVENT_LOOP.run_forever()

    ASYNCIO_LOOP_THREAD = threading.Thread(
        target=_thread_target, daemon=True, name="piper4nvda_asyncio"
    )
    ASYNCIO_LOOP_THREAD.start()


def terminate():
    global THREADED_EXECUTOR, ASYNCIO_LOOP_THREAD, ASYNCIO_EVENT_LOOP
    log.info("Shutting down the thread pool executor")
    THREADED_EXECUTOR.shutdown()
    THREADED_EXECUTOR = None
    if ASYNCIO_LOOP_THREAD:
        log.info("Shutting down asyncio event loop")
        ASYNCIO_EVENT_LOOP.call_soon_threadsafe(ASYNCIO_EVENT_LOOP.stop)
        ASYNCIO_LOOP_THREAD = None


def asyncio_create_task(coro):
    return ASYNCIO_EVENT_LOOP.call_soon_threadsafe(ASYNCIO_EVENT_LOOP.create_task, coro)


def asyncio_cancel_task(task):
    ASYNCIO_EVENT_LOOP.call_soon_threadsafe(task.cancel)


def asyncio_coroutine_to_concurrent_future(async_func):
    """Returns a concurrent.futures.Future that wrapps the decorated async function."""

    @wraps(async_func)
    def wrapper(*args, **kwargs):
        return asyncio.run_coroutine_threadsafe(
            async_func(*args, **kwargs), loop=ASYNCIO_EVENT_LOOP
        )

    return wrapper


def call_threaded(func: t.Callable[..., None]) -> t.Callable[..., "Future"]:
    """Call `func` in a separate thread. It wraps the function
    in another function that returns a `concurrent.futures.Future`
    object when called.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return THREADED_EXECUTOR.submit(func, *args, **kwargs)
        except RuntimeError:
            log.debug(f"Failed to submit function {func}.")

    return wrapper


def run_in_executor(func, *args, **kwargs):
    callable = partial(func, *args, **kwargs)
    return ASYNCIO_EVENT_LOOP.run_in_executor(THREADED_EXECUTOR, callable)
