from langchain_mcp_adapters.client import MultiServerMCPClient

SERVERS = {
    "context7": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"]
    }
}

async def load_mcp_tools(servers=None):
    return await MultiServerMCPClient(servers or SERVERS).get_tools()