# ohmywishes-mcp

An MCP (Model Context Protocol) server for [ohmywishes.com](https://ohmywishes.com) — wish lists and gift wishes — so an AI agent can read and manage your wishlists: create wishes, attach photos, group them into lists, reserve gifts on other people's lists.

Single file, Python standard library only, no dependencies.

> **Unofficial.** This talks to the public web API of the service (`api.ohmywishes.com`). The API is not formally documented, so endpoints and fields may change without notice. Not affiliated with or endorsed by ohmywishes.

## Features

- **14 tools** over stdio MCP: whoami, lists, wishes, pictures, reservations, plus a raw `omw_api` escape hatch for anything not covered
- **Safe updates**: `omw_update_wish` / `omw_update_wishlist` read the object first, merge your fields and only then send the full `PUT` the API requires — otherwise the API silently wipes fields you did not resend
- **No dependencies, no install step**: `python3 server.py`
- Works with any MCP client: Hermes, Claude Desktop, Cursor, custom clients

## Requirements

- Python 3.9+
- An ohmywishes account

## Getting a token

The API authenticates with a JWT bearer token that the web app receives when you log in.

1. Log in at <https://ohmywishes.com>
2. Open DevTools (`F12`) → **Network**
3. Keep the panel open, tick **Preserve log**, reload the page, and click through a list or the profile menu
4. Open any request to `api.ohmywishes.com` and look at its **request URL** — it carries `?token=eyJ...`
5. Copy the value after `token=` (the token is a JWT, three dot-separated parts)

Store it where the server can read it:

```bash
mkdir -p ~/.config/ohmywishes
printf '%s' 'PASTE_TOKEN_HERE' > ~/.config/ohmywishes/token
chmod 600 ~/.config/ohmywishes/token
```

Or pass it through the environment: `OMW_TOKEN=... python3 server.py`.

> The token grants full access to your account and lives about a year. Treat it as a password: never commit it, never paste it into chats, `chmod 600` the file.

## Install and run

```bash
git clone https://github.com/demoniksem/ohmywishes-mcp.git
cd ohmywishes-mcp
python3 server.py --help          # check the token is found
python3 server.py                 # stdio MCP server (blocks, waiting for JSON-RPC)
```

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `OMW_TOKEN` | — | JWT; takes priority over the file |
| `OMW_TOKEN_FILE` | `~/.config/ohmywishes/token` | File with the JWT |
| `OMW_BASE_URL` | `https://api.ohmywishes.com` | API base URL |
| `OMW_TIMEOUT` | `60` | HTTP timeout, seconds |

## Client configuration

**Hermes** (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  ohmywishes:
    command: python3
    args:
      - /absolute/path/to/ohmywishes-mcp/server.py
    enabled: true
```

Or let the CLI do it: `hermes mcp add ohmywishes --command python3 --args /absolute/path/to/server.py`

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ohmywishes": {
      "command": "python3",
      "args": ["/absolute/path/to/ohmywishes-mcp/server.py"]
    }
  }
}
```

Ready-to-copy files: [`examples/hermes-config.yaml`](examples/hermes-config.yaml), [`examples/claude-desktop.json`](examples/claude-desktop.json).

## Tools

| Tool | What it does |
|---|---|
| `omw_whoami` | Current account: id, username, counters. Token smoke test |
| `omw_list_wishlists` | Own wish lists with visibility and wish count |
| `omw_list_wishes` | Paged own wishes: `all`, `private`, `reserved`, `fulfilled` |
| `omw_get_wish` | One wish by id (price, link, photos, list membership, reservation flags) |
| `omw_create_wish` | Create a wish: `title` required, optional `private`, `description`, `price`, `currency`, `link`, `wish_lists` |
| `omw_update_wish` | Merge-and-update a wish without wiping fields |
| `omw_delete_wish` | Delete a wish |
| `omw_set_wish_picture` | Upload a local image file as the wish photo |
| `omw_create_wishlist` | Create a list: `title` required, `visibility` = `inherit` / `private` / `followers` |
| `omw_update_wishlist` | Merge-and-update a list |
| `omw_delete_wishlist` | Delete a list |
| `omw_reserve_wish` | Reserve somebody's wish (the owner sees it as taken) |
| `omw_unreserve_wish` | Cancel your reservation |
| `omw_api` | Raw call: any method + path under `/api/v2` or `/api/v3` |

## API notes worth knowing

Collected while mapping the API; they explain most surprises:

- **The token is accepted only as a query parameter** (`?token=...`). An `Authorization: Bearer` header is rejected with `403 security.invalid_access_token`, cookies and `X-Token` variants give `401`.
- **`PUT` on a wish replaces the whole object.** If you omit `wish_lists`, the wish is detached from its lists. That is why the `omw_update_*` tools exist.
- **Wish visibility is derived from the `private` boolean**; a `visibility` field on a wish is ignored.
- **Wish-list visibility is its own enum**: `inherit`, `private`, `followers`. Values like `public` or `link` return 400.
- **Unknown fields are ignored silently**, not rejected — a typo looks like "the field does nothing".
- **Links get `?utm_source=ohmywishes` appended** by the server.
- **`price` is a plain number**; the currency lives in a separate field (34 currencies, `RUB` by default).
- **You cannot reserve your own wish** (400).
- Responses use two shapes: bare arrays for wish listings, `{"items": [...]}` / `{"item": {...}}` elsewhere.

## Security

- The server never logs the token and sends it only to `api.ohmywishes.com`.
- All writes go through the account that owns the token — there is no dry-run mode.
- Test objects you create are real: clean them up (`omw_delete_wish`, `omw_delete_wishlist`).

## License

MIT — see [LICENSE](LICENSE).
