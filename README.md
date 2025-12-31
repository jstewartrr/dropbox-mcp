# Dropbox MCP for Sovereign Mind

MCP server providing Dropbox file operations for MiddleGround Capital.

## Tools (14 total)

| Tool | Description |
|------|-------------|
| `list_folder` | List files and folders in a directory |
| `search_files` | Search for files by name or content |
| `get_file_metadata` | Get detailed file/folder metadata |
| `download_file` | Download file contents |
| `read_text_file` | Read text file content |
| `upload_file` | Upload files (text or binary) |
| `create_folder` | Create new folders |
| `move_file` | Move or rename files/folders |
| `copy_file` | Copy files/folders |
| `delete_file` | Delete files/folders (to trash) |
| `get_shared_link` | Get or create shared links |
| `list_revisions` | List file version history |
| `get_space_usage` | Get storage quota info |
| `test_connection` | Test API connection |

## Setup

### 1. Create Dropbox App

1. Go to https://www.dropbox.com/developers/apps
2. Create a new app:
   - Choose "Scoped access"
   - Choose "Full Dropbox" (or "App folder" if restricted)
   - Name: "MiddleGround Sovereign Mind"
3. Under "Permissions", enable:
   - `files.metadata.read`
   - `files.metadata.write`
   - `files.content.read`
   - `files.content.write`
   - `sharing.read`
   - `sharing.write`
4. Generate an access token (or use OAuth2 refresh flow)

### 2. Environment Variables

```bash
# Option A: Long-lived refresh token (recommended)
DROPBOX_REFRESH_TOKEN=your_refresh_token
DROPBOX_APP_KEY=your_app_key
DROPBOX_APP_SECRET=your_app_secret

# Option B: Access token (expires in 4 hours)
DROPBOX_ACCESS_TOKEN=your_access_token
```

### 3. Deploy to Azure Container Apps

```bash
# Build image
az acr build --registry sovereignmindacr --image dropbox-mcp:v1.0.0 .

# Create container app
az containerapp create \
  --name dropbox-mcp \
  --resource-group SovereignMind-RG \
  --environment SovereignMind-Env \
  --image sovereignmindacr.azurecr.io/dropbox-mcp:v1.0.0 \
  --target-port 8080 \
  --ingress external \
  --registry-server sovereignmindacr.azurecr.io \
  --env-vars \
    DROPBOX_REFRESH_TOKEN=secretref:dropbox-refresh-token \
    DROPBOX_APP_KEY=secretref:dropbox-app-key \
    DROPBOX_APP_SECRET=secretref:dropbox-app-secret
```

### 4. Add to SM Gateway

Update `app.py` in sm-mcp-gateway:

```python
"dropbox": {
    "url": "https://dropbox-mcp.lemoncoast-87756bcf.eastus.azurecontainerapps.io/mcp",
    "prefix": "dropbox",
    "description": "Dropbox file storage for MiddleGround",
    "enabled": True,
    "transport": "json",
    "priority": 1,
    "health_check": False
}
```

## Usage Examples

```python
# List root folder
{"name": "list_folder", "arguments": {"path": ""}}

# Search for Excel files
{"name": "search_files", "arguments": {"query": "budget", "file_extensions": ["xlsx", "xls"]}}

# Read a text file
{"name": "read_text_file", "arguments": {"path": "/Documents/notes.txt"}}

# Upload a file
{"name": "upload_file", "arguments": {"path": "/Reports/Q4.txt", "content": "Report content..."}}

# Get shared link
{"name": "get_shared_link", "arguments": {"path": "/Presentations/deck.pptx"}}
```

## Architecture

```
Claude.ai / API Claude
        │
        ▼
   SM MCP Gateway
        │
        ▼
   Dropbox MCP (this)
        │
        ▼
   Dropbox API
        │
        ▼
MiddleGround Dropbox
```

## Security Notes

- Use refresh tokens for production (auto-renew)
- Access tokens expire in 4 hours
- Store credentials in Azure Key Vault or Container App secrets
- Dropbox audit logs track all API access
