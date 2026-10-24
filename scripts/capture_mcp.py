#!/usr/bin/env python3
"""Drive the real MCP server over stdio and record what it actually answers.

    .venv/bin/python scripts/capture_mcp.py

Writes build/demo/mcp_session.json - a transcript of a genuine JSON-RPC
exchange with `python -m src.mcp_server`. Nothing here is written by hand:
the tool names, descriptions and the call result all come back from the
server process. The closing section of the demo narrates that Fintor's
analysis functions are callable by another agent over MCP, and MCP is
stdio-only, so this is the only way to show it without faking a screenshot.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def rpc(proc, obj: dict) -> dict | None:
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == obj.get("id"):
            return msg


def main() -> int:
    proc = subprocess.Popen(
        [str(REPO / ".venv/bin/python"), "-m", "src.mcp_server"],
        cwd=str(REPO), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1)

    init = rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2024-11-05",
                                 "capabilities": {},
                                 "clientInfo": {"name": "fintor-demo",
                                                "version": "1.0"}}})
    proc.stdin.write(json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    tools = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                       "params": {}})
    call = rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                      "params": {"name": "analyze_portfolio", "arguments": {
                          "holdings": [
                              {"symbol": "BND", "shares": 2600, "cost_basis": 78.0,
                               "asset_class": "bond"},
                              {"symbol": "VTI", "shares": 380, "cost_basis": 160.0,
                               "asset_class": "equity"},
                              {"symbol": "TLT", "shares": 300, "cost_basis": 104.0,
                               "asset_class": "bond"}],
                          "cash": 60000.0}}})

    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    names = [t["name"] for t in (tools or {}).get("result", {}).get("tools", [])]
    if not names:
        print("no tools returned - refusing to write a transcript", file=sys.stderr)
        return 1

    out = {"server": (init or {}).get("result", {}).get("serverInfo", {}),
           "tools": (tools or {}).get("result", {}).get("tools", []),
           "call": (call or {}).get("result", {})}
    dest = REPO / "build" / "demo" / "mcp_session.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"{len(names)} tools: {', '.join(names)}")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
