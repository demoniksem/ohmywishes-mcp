#!/usr/bin/env python3
"""Smoke test: the server starts, speaks MCP and exposes every tool.

Runs without a token on purpose — it checks the handshake, the tool list and the
graceful "missing_token" answer, so CI needs no credentials.

    python3 tests/smoke_test.py
"""
import json
import os
import pathlib
import subprocess
import sys

SERVER = pathlib.Path(__file__).resolve().parent.parent / "server.py"
EXPECTED = {
    "omw_whoami",
    "omw_list_wishlists",
    "omw_list_wishes",
    "omw_get_wish",
    "omw_create_wish",
    "omw_update_wish",
    "omw_delete_wish",
    "omw_set_wish_picture",
    "omw_create_wishlist",
    "omw_update_wishlist",
    "omw_delete_wishlist",
    "omw_reserve_wish",
    "omw_unreserve_wish",
    "omw_api",
}


def main():
    # Run without credentials on purpose: even a machine that has a real token
    # must behave like CI here.
    env = dict(os.environ)
    env["OMW_TOKEN"] = ""
    env["OMW_TOKEN_FILE"] = os.path.join(os.path.dirname(__file__), "no-such-token")
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    feed, sink = proc.stdin, proc.stdout
    if feed is None or sink is None:  # static checkers: pipes exist because we passed PIPE
        raise SystemExit("could not open pipes to the server")

    def rpc(msg):
        feed.write(json.dumps(msg) + "\n")
        feed.flush()
        line = sink.readline()
        if not line:
            raise SystemExit("no answer from server")
        return json.loads(line)

    init = rpc({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "smoke", "version": "1"}},
    })
    server_info = init["result"]["serverInfo"]
    assert server_info["name"] == "ohmywishes", server_info
    print(f"initialize ok: {server_info['name']} {server_info['version']}")

    feed.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    feed.flush()

    tools = {t["name"] for t in rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
    missing = EXPECTED - tools
    assert not missing, f"tools missing: {sorted(missing)}"
    print(f"tools/list ok: {len(tools)} tools")

    # Without a token every call must fail cleanly instead of crashing the process.
    call = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "omw_whoami", "arguments": {}}})
    result = call["result"]
    payload = json.loads(result["content"][0]["text"])
    assert "missing_token" in payload.get("error", ""), payload
    print("missing token handled gracefully")

    # The process must still be alive and answering after that error.
    ping = rpc({"jsonrpc": "2.0", "id": 4, "method": "ping"})
    assert ping.get("result") == {}, ping
    print("server still alive after a failed call")

    feed.close()
    proc.wait(timeout=10)
    print("smoke test passed")


if __name__ == "__main__":
    main()
