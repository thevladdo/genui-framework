"""
In-memory stores for the suite.

The store singletons resolve REDIS_URL from backend/.env on first use, so without this a test that renders or answers a query reads and writes the Redis of whoever runs the suite.
Every test calls asyncio.run on a new loop, the shared connection dies with the previous loop, and the authoritative stores then refuse to answer.
A module whose tests reach these stores calls use_memory_stores() from setUpModule.
"""


def use_memory_stores() -> None:
    try:
        import api.deps as deps
        import utils.content_policy_store as policy_store
        import utils.theme_store as theme_store
        from profiles import ChatSessionStore, ProfileStore
        from zones import ZoneConfigStore
    except ModuleNotFoundError as e:
        # Without fastapi the route tests skip themselves and there is no store to replace; any other missing module is a broken import, and swallowing it would leave the tests on a real Redis.
        if e.name != "fastapi":
            raise
        return
    policy_store._STORE = policy_store.ContentPolicyStore()
    theme_store._STORE = theme_store.ThemeStore()
    deps._profile_store = ProfileStore()
    deps._session_store = ChatSessionStore()
    deps._zone_config_store = ZoneConfigStore()
