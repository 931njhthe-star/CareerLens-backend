import asyncio
import sys


def run(coroutine):
    # psycopg async connections require a selector loop on Windows.
    factory = asyncio.SelectorEventLoop if sys.platform == 'win32' else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coroutine)
