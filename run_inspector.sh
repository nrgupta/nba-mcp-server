#!/bin/bash

echo "Killing any processes on MCP inspector ports..."
lsof -ti:6274 | xargs kill -9 2>/dev/null
lsof -ti:6277 | xargs kill -9 2>/dev/null
echo "Done. Starting MCP inspector..."

npx @modelcontextprotocol/inspector python3 /Users/neilgupta/Desktop/NBA-MCP/nba_mcp_server.py
