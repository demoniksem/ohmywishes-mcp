#!/usr/bin/env python3
"""Ohmywishes MCP server (stdio, stdlib only).

Unofficial: talks to the Ohmywishes web API, not affiliated with the service.

Wraps the Ohmywishes HTTP API (api.ohmywishes.com, v2 + v3).
Auth: JWT in OMW_TOKEN, or in a token file (OMW_TOKEN_FILE,
      default ~/.config/ohmywishes/token).
The API only accepts the JWT as ?token= — see api() below.

Read tools:   omw_whoami, omw_list_wishlists, omw_list_wishes, omw_get_wish
Write tools:  omw_create_wish, omw_update_wish, omw_delete_wish,
              omw_create_wishlist, omw_update_wishlist, omw_delete_wishlist
Reservations: omw_reserve_wish, omw_unreserve_wish
Escape hatch: omw_api (any method + path under /api/v2 or /api/v3)
"""
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BASE = os.environ.get("OMW_BASE_URL", "https://api.ohmywishes.com").rstrip("/")
TOKEN = os.environ.get("OMW_TOKEN", "").strip()
TOKEN_FILE = os.path.expanduser(os.environ.get("OMW_TOKEN_FILE", "~/.config/ohmywishes/token"))
if not TOKEN and os.path.exists(TOKEN_FILE):
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
            TOKEN = fh.read().strip()
    except OSError:
        TOKEN = ""
TIMEOUT = int(os.environ.get("OMW_TIMEOUT", "60"))
PROTOCOL = "2024-11-05"
UNSET = object()


def api(method, path, body=None, query=None):
    if not path.startswith("/"):
        path = "/" + path
    url = BASE + path
    # Ohmywishes accepts the JWT only as a ?token= query parameter (verified);
    # the Authorization header is rejected with 403 security.invalid_access_token.
    params = dict(query or {})
    if TOKEN:
        params["token"] = TOKEN
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    data = None
    headers = {"Accept": "application/json", "User-Agent": "ohmywishes-mcp/1.0"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return {"status": resp.status, "body": json.loads(raw) if raw.strip() else None}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw[:2000]
        return {"status": e.code, "body": payload,
                "error": "unauthorized" if e.code == 401 else "http_error"}
    except urllib.error.URLError as e:
        return {"error": "network", "detail": str(e.reason)}


def ok(resp):
    return "error" not in resp and 200 <= resp.get("status", 0) < 300


def api_upload(path, file_path, field="picture", extra_query=None):
    """POST multipart/form-data with one file part (wish pictures, avatars)."""
    if not path.startswith("/"):
        path = "/" + path
    if not os.path.exists(file_path):
        return {"error": "file_not_found", "path": file_path}
    params = dict(extra_query or {})
    if TOKEN:
        params["token"] = TOKEN
    url = BASE + path + ("?" + urlencode(params) if params else "")
    boundary = "----omw" + uuid.uuid4().hex
    name = os.path.basename(file_path)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(file_path, "rb") as fh:
        blob = fh.read()
    body = bytearray()
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\n'.encode()
    body += f"Content-Type: {ctype}\r\n\r\n".encode()
    body += blob
    body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=bytes(body), method="POST", headers={
        "Accept": "application/json",
        "User-Agent": "ohmywishes-mcp/1.0",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return {"status": resp.status, "body": json.loads(raw) if raw.strip() else None}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw[:2000]
        return {"status": e.code, "body": payload, "error": "http_error"}
    except urllib.error.URLError as e:
        return {"error": "network", "detail": str(e.reason)}


def res(resp):
    """Wrap an API response as an MCP tool result, flagging non-2xx as errors."""
    return text_result(resp, not ok(resp))


def strip_utm(link):
    """The API appends ?utm_source=ohmywishes — drop it before re-sending on update."""
    if not link:
        return link
    parts = urlsplit(link)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
         if not (k == "utm_source" and v == "ohmywishes")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


def text_result(obj, is_error=False):
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": body}], "isError": is_error}


def pick(args, key, default=UNSET):
    return args[key] if key in args else default


TOOLS = [
    {
        "name": "omw_whoami",
        "description": "Current Ohmywishes account: id, username, name, counters. Use it first to check the token works.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "omw_list_wishlists",
        "description": "Own wish lists with visibility and wishesCount.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "omw_list_wishes",
        "description": "Paged wishes of the logged-in user: all, private, reserved (reserved by me), or fulfilled.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["all", "private", "reserved", "fulfilled"], "default": "all"},
                "size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "page": {"type": "integer", "minimum": 1, "default": 1},
            },
        },
    },
    {
        "name": "omw_get_wish",
        "description": "One wish by id (v3 shape: price{price,currency}, externalUri, isPrivate, wishLists, reservation flags).",
        "inputSchema": {"type": "object", "properties": {"wish_id": {"type": "string"}}, "required": ["wish_id"]},
    },
    {
        "name": "omw_create_wish",
        "description": (
            "Create a wish. Only title is required (private defaults to false). price is a number, "
            "currency a 3-letter code (default RUB), wish_lists a list of wish-list ids."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "private": {"type": "boolean", "default": False},
                "description": {"type": "string"},
                "price": {"type": "number"},
                "currency": {"type": "string"},
                "link": {"type": "string"},
                "wish_lists": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
    },
    {
        "name": "omw_update_wish",
        "description": (
            "Update a wish safely: reads the current wish, merges the given fields and sends the full PUT "
            "the API requires, so description, price and list membership are not wiped. "
            "Pass wish_lists to replace membership; price:null clears the price."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "wish_id": {"type": "string"},
                "title": {"type": "string"},
                "private": {"type": "boolean"},
                "description": {"type": "string"},
                "price": {"type": ["number", "null"]},
                "currency": {"type": "string"},
                "link": {"type": ["string", "null"]},
                "wish_lists": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["wish_id"],
        },
    },
    {
        "name": "omw_delete_wish",
        "description": "Delete a wish by id (irreversible).",
        "inputSchema": {"type": "object", "properties": {"wish_id": {"type": "string"}}, "required": ["wish_id"]},
    },
    {
        "name": "omw_set_wish_picture",
        "description": (
            "Upload a local image file as the photo of a wish (POST .../picture, multipart). "
            "file_path is a path on this machine, e.g. a photo the user saved to the share."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"wish_id": {"type": "string"}, "file_path": {"type": "string"}},
            "required": ["wish_id", "file_path"],
        },
    },
    {
        "name": "omw_create_wishlist",
        "description": "Create a wish list. Required: title. visibility: inherit (default) | private | followers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "visibility": {"type": "string", "enum": ["inherit", "private", "followers"]},
            },
            "required": ["title"],
        },
    },
    {
        "name": "omw_update_wishlist",
        "description": "Update a wish list: reads it, merges the given fields, sends the full PUT.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "list_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "visibility": {"type": "string", "enum": ["inherit", "private", "followers"]},
            },
            "required": ["list_id"],
        },
    },
    {
        "name": "omw_delete_wishlist",
        "description": "Delete a wish list by id.",
        "inputSchema": {"type": "object", "properties": {"list_id": {"type": "string"}}, "required": ["list_id"]},
    },
    {
        "name": "omw_reserve_wish",
        "description": "Reserve somebody's wish so the owner sees it as taken. Returns the updated wish.",
        "inputSchema": {
            "type": "object",
            "properties": {"wish_id": {"type": ["string", "integer"]}},
            "required": ["wish_id"],
        },
    },
    {
        "name": "omw_unreserve_wish",
        "description": "Cancel a reservation made by the logged-in user.",
        "inputSchema": {
            "type": "object",
            "properties": {"wish_id": {"type": ["string", "integer"]}},
            "required": ["wish_id"],
        },
    },
    {
        "name": "omw_api",
        "description": (
            "Raw Ohmywishes API call for anything the named tools do not cover "
            "(profile, follow, favourites, notifications, selections). "
            "path must start with /api/v2 or /api/v3, e.g. /api/v3/selections."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
                "path": {"type": "string"},
                "body": {"type": ["object", "array", "null"]},
                "query": {"type": "object"},
            },
            "required": ["method", "path"],
        },
    },
]


def call_tool(name, args):
    if name == "omw_whoami":
        return res(api("GET", "/api/v2/users/self"))
    if name == "omw_list_wishlists":
        return res(api("GET", "/api/v3/own-user/wish-lists"))
    if name == "omw_list_wishes":
        scope = args.get("scope", "all")
        if scope not in ("all", "private", "reserved", "fulfilled"):
            return text_result({"error": "bad_scope", "allowed": ["all", "private", "reserved", "fulfilled"]}, True)
        return res(api("GET", f"/api/v2/users/self/wish-lists/{scope}/wishes",
                               query={"size": int(args.get("size", 20)), "page": int(args.get("page", 1))}))
    if name == "omw_get_wish":
        return res(api("GET", f"/api/v3/wishes/{args['wish_id']}"))
    if name == "omw_create_wish":
        title = (args.get("title") or "").strip()
        if not title:
            return text_result({"error": "title is required"}, True)
        body = {"title": title, "private": bool(args.get("private", False))}
        for key in ("description", "price", "currency", "link", "wish_lists"):
            val = pick(args, key)
            if val is not UNSET:
                body[key] = val
        return res(api("POST", "/api/v2/users/self/wishes", body=body))
    if name == "omw_update_wish":
        wid = args["wish_id"]
        cur = api("GET", f"/api/v3/wishes/{wid}")
        item = (cur.get("body") or {}).get("item") if ok(cur) else None
        if not item:
            return text_result({"error": "cannot read current wish", "upstream": cur}, True)
        price_obj = item.get("price") or {}
        body = {
            "title": pick(args, "title", item.get("title")),
            "private": pick(args, "private", item.get("isPrivate", False)),
            "description": pick(args, "description", item.get("description") or ""),
            "currency": pick(args, "currency", price_obj.get("currency") or "RUB"),
            "price": pick(args, "price", price_obj.get("price")),
            "link": pick(args, "link", strip_utm(item.get("externalUri"))),
            "wish_lists": pick(args, "wish_lists",
                               [w.get("id") for w in (item.get("wishLists") or []) if w.get("id")]),
        }
        return res(api("PUT", f"/api/v2/users/self/wishes/{wid}", body=body))
    if name == "omw_delete_wish":
        return res(api("DELETE", f"/api/v2/users/self/wishes/{args['wish_id']}"))
    if name == "omw_set_wish_picture":
        path = os.path.expanduser(args["file_path"])
        return res(api_upload(f"/api/v2/users/self/wishes/{args['wish_id']}/picture", path))
    if name == "omw_create_wishlist":
        title = (args.get("title") or "").strip()
        if not title:
            return text_result({"error": "title is required"}, True)
        body = {"title": title}
        for key in ("description", "visibility"):
            val = pick(args, key)
            if val is not UNSET:
                body[key] = val
        return res(api("POST", "/api/v3/own-user/wish-lists", body=body))
    if name == "omw_update_wishlist":
        lid = args["list_id"]
        cur = api("GET", f"/api/v3/own-user/wish-lists/{lid}")
        item = (cur.get("body") or {}).get("item") if ok(cur) else None
        if not item:
            return text_result({"error": "cannot read current wish list", "upstream": cur}, True)
        body = {
            "title": pick(args, "title", item.get("title")),
            "description": pick(args, "description", item.get("description") or ""),
            "visibility": pick(args, "visibility", item.get("visibility") or "inherit"),
        }
        return res(api("PUT", f"/api/v3/own-user/wish-lists/{lid}", body=body))
    if name == "omw_delete_wishlist":
        return res(api("DELETE", f"/api/v3/own-user/wish-lists/{args['list_id']}"))
    if name == "omw_reserve_wish":
        if "wish_id" not in args:
            return text_result({"error": "wish_id is required"}, True)
        return res(api("POST", f"/api/v3/wishes/{args['wish_id']}/reservation", body=None))
    if name == "omw_unreserve_wish":
        if "wish_id" not in args:
            return text_result({"error": "wish_id is required"}, True)
        return res(api("DELETE", f"/api/v3/wishes/{args['wish_id']}/reservation"))
    if name == "omw_api":
        path = str(args.get("path", ""))
        if not (path.startswith("/api/v2") or path.startswith("/api/v3")):
            return text_result({"error": "path must start with /api/v2 or /api/v3"}, True)
        return res(api(args.get("method", "GET"), path, body=args.get("body"), query=args.get("query")))
    return text_result({"error": f"unknown tool {name}"}, True)


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        rid = req.get("id")
        if method == "initialize":
            params = req.get("params") or {}
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "ohmywishes", "version": "1.0.0"},
            }})
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if not TOKEN:
                send({"jsonrpc": "2.0", "id": rid, "result": text_result(
                    {"error": "missing_token",
                     "hint": f"Put a bearer token from ohmywishes.com into {TOKEN_FILE} (chmod 600) or set OMW_TOKEN"}, True)})
                continue
            try:
                result = call_tool(name, args)
            except KeyError as e:
                result = text_result({"error": "missing_argument", "detail": str(e)}, True)
            except Exception as e:  # never kill the server on a tool error
                result = text_result({"error": "exception", "detail": repr(e)}, True)
            send({"jsonrpc": "2.0", "id": rid, "result": result})
        elif rid is not None:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print(f"token: {'set' if TOKEN else 'NOT set'} (env OMW_TOKEN or {TOKEN_FILE})")
        print("tools: 14 (see README)")
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] in ("-V", "--version"):
        print("ohmywishes-mcp 1.0.0")
        raise SystemExit(0)
    main()
