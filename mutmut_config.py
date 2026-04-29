"""Mutmut configuration hooks for MCP Gateway.

See Task 2.5 of the MCP Gateway implementation plan. These hooks are
intentionally minimal; extend them if mutation runs need per-mutation
context (e.g. to skip generated files) or one-time setup (e.g. seeding
test fixtures).
"""


def pre_mutation(context):
    """Called before each mutation is applied.

    The ``context`` object exposes attributes such as ``filename`` and
    ``current_source_line`` which can be used to skip uninteresting
    mutations. Currently a no-op.
    """
    pass


def init():
    """Called once before any mutations are run. Currently a no-op."""
    pass
