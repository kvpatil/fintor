"""Fintor's finance tools over the Model Context Protocol.

`python -m src.mcp_server` serves them over stdio for Claude Desktop.
See src/mcp_server/server.py for what is exposed and why none of it calls a model.

Only `main` is re-exported. Binding the MCPServer instance here as `server`
would shadow the `server` SUBMODULE on the package, so `import
src.mcp_server.server` would hand back the object instead of the module -
which broke every test that tried to monkeypatch module state.
"""

from src.mcp_server.server import main

__all__ = ["main"]
