# MCP Server Setup

## Google Calendar MCP

1. Go to [claude.ai](https://claude.ai) → Settings → Integrations
2. Connect **Google Calendar**
3. Copy the MCP server URL: `https://gcal.mcp.claude.com/mcp`
4. Add to `.env`: `GCAL_MCP_URL=https://gcal.mcp.claude.com/mcp`

The Calendar agent uses this to:
- Check free/busy slots before suggesting travel dates
- Create calendar events after booking is approved

## Gmail MCP

1. Go to [claude.ai](https://claude.ai) → Settings → Integrations
2. Connect **Gmail**
3. Copy the MCP server URL: `https://gmail.mcp.claude.com/mcp`
4. Add to `.env`: `GMAIL_MCP_URL=https://gmail.mcp.claude.com/mcp`

The Email agent uses this to:
- Scan for existing booking confirmation emails
- Send trip summary after approval

## Passing MCP servers to Claude API

```python
response = anthropic.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1000,
    messages=[{"role": "user", "content": prompt}],
    mcp_servers=[
        {"type": "url", "url": GCAL_MCP_URL, "name": "google-calendar"},
        {"type": "url", "url": GMAIL_MCP_URL, "name": "gmail"},
    ]
)
```
