"""
Dropbox MCP Server for Sovereign Mind
Provides file operations for MiddleGround Capital Dropbox
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from flask import Flask, request, jsonify
import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode, FileMetadata, FolderMetadata

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
DROPBOX_ACCESS_TOKEN = os.environ.get("DROPBOX_ACCESS_TOKEN")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")

# Initialize Dropbox client
def get_dropbox_client() -> dropbox.Dropbox:
    """Get authenticated Dropbox client with auto-refresh."""
    if DROPBOX_REFRESH_TOKEN and DROPBOX_APP_KEY and DROPBOX_APP_SECRET:
        # Use refresh token for long-lived access
        return dropbox.Dropbox(
            oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
            app_key=DROPBOX_APP_KEY,
            app_secret=DROPBOX_APP_SECRET
        )
    elif DROPBOX_ACCESS_TOKEN:
        # Fallback to access token
        return dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
    else:
        raise ValueError("No Dropbox credentials configured")

# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

TOOLS = [
    {
        "name": "list_folder",
        "description": "List files and folders in a Dropbox directory. Returns file names, sizes, and modification dates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Dropbox folder path (use '' for root, '/folder' for subfolder)"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Include contents of subfolders",
                    "default": False
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entries to return",
                    "default": 100
                }
            },
            "required": []
        }
    },
    {
        "name": "search_files",
        "description": "Search for files and folders in Dropbox by name or content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (searches file names and content)"
                },
                "path": {
                    "type": "string",
                    "description": "Limit search to this folder path (optional)"
                },
                "file_extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by file extensions (e.g., ['pdf', 'docx'])"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 50
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_file_metadata",
        "description": "Get detailed metadata for a file or folder including size, dates, and sharing info.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Full path to the file or folder"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "download_file",
        "description": "Download a file from Dropbox and return its contents (text files) or base64 (binary).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Full path to the file in Dropbox"
                },
                "as_text": {
                    "type": "boolean",
                    "description": "Return as text (True) or base64 (False)",
                    "default": True
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_text_file",
        "description": "Read the text content of a file (txt, md, csv, json, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Full path to the text file"
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Maximum bytes to read (for large files)",
                    "default": 1000000
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "upload_file",
        "description": "Upload a file to Dropbox. Supports text content or base64-encoded binary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Destination path in Dropbox (e.g., '/Reports/Q4_Report.pdf')"
                },
                "content": {
                    "type": "string",
                    "description": "File content (text or base64-encoded)"
                },
                "is_base64": {
                    "type": "boolean",
                    "description": "Set to true if content is base64-encoded",
                    "default": False
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite if file exists",
                    "default": True
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "create_folder",
        "description": "Create a new folder in Dropbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Full path for the new folder"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "move_file",
        "description": "Move or rename a file or folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_path": {
                    "type": "string",
                    "description": "Current path of the file/folder"
                },
                "to_path": {
                    "type": "string",
                    "description": "New path for the file/folder"
                }
            },
            "required": ["from_path", "to_path"]
        }
    },
    {
        "name": "copy_file",
        "description": "Copy a file or folder to a new location.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_path": {
                    "type": "string",
                    "description": "Source path"
                },
                "to_path": {
                    "type": "string",
                    "description": "Destination path"
                }
            },
            "required": ["from_path", "to_path"]
        }
    },
    {
        "name": "delete_file",
        "description": "Delete a file or folder (moves to trash, can be recovered).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to delete"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "get_shared_link",
        "description": "Get or create a shared link for a file or folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file/folder"
                },
                "create_if_missing": {
                    "type": "boolean",
                    "description": "Create a new link if none exists",
                    "default": True
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_revisions",
        "description": "List previous versions of a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum revisions to return",
                    "default": 10
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "get_space_usage",
        "description": "Get Dropbox account storage usage and quota.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "test_connection",
        "description": "Test the Dropbox API connection and return account info.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

def list_folder(path: str = "", recursive: bool = False, limit: int = 100) -> Dict:
    """List contents of a Dropbox folder."""
    try:
        dbx = get_dropbox_client()
        entries = []
        result = dbx.files_list_folder(path, recursive=recursive, limit=min(limit, 2000))
        
        while True:
            for entry in result.entries:
                entry_info = {
                    "name": entry.name,
                    "path": entry.path_display,
                    "type": "folder" if isinstance(entry, FolderMetadata) else "file"
                }
                if isinstance(entry, FileMetadata):
                    entry_info.update({
                        "size": entry.size,
                        "size_human": format_size(entry.size),
                        "modified": entry.server_modified.isoformat() if entry.server_modified else None,
                        "content_hash": entry.content_hash[:16] + "..." if entry.content_hash else None
                    })
                entries.append(entry_info)
                
                if len(entries) >= limit:
                    break
            
            if not result.has_more or len(entries) >= limit:
                break
            result = dbx.files_list_folder_continue(result.cursor)
        
        return {
            "success": True,
            "path": path or "/",
            "count": len(entries),
            "entries": entries[:limit]
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def search_files(query: str, path: str = None, file_extensions: List[str] = None, max_results: int = 50) -> Dict:
    """Search for files in Dropbox."""
    try:
        dbx = get_dropbox_client()
        
        # Build search options
        options = dropbox.files.SearchOptions(
            path=path,
            max_results=min(max_results, 1000),
            file_extensions=file_extensions
        )
        
        result = dbx.files_search_v2(query, options=options)
        
        matches = []
        for match in result.matches:
            metadata = match.metadata.get_metadata()
            match_info = {
                "name": metadata.name,
                "path": metadata.path_display,
                "type": "folder" if isinstance(metadata, FolderMetadata) else "file"
            }
            if isinstance(metadata, FileMetadata):
                match_info.update({
                    "size": metadata.size,
                    "size_human": format_size(metadata.size),
                    "modified": metadata.server_modified.isoformat() if metadata.server_modified else None
                })
            matches.append(match_info)
        
        return {
            "success": True,
            "query": query,
            "count": len(matches),
            "matches": matches
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def get_file_metadata(path: str) -> Dict:
    """Get metadata for a file or folder."""
    try:
        dbx = get_dropbox_client()
        metadata = dbx.files_get_metadata(path, include_has_explicit_shared_members=True)
        
        result = {
            "success": True,
            "name": metadata.name,
            "path": metadata.path_display,
            "type": "folder" if isinstance(metadata, FolderMetadata) else "file"
        }
        
        if isinstance(metadata, FileMetadata):
            result.update({
                "size": metadata.size,
                "size_human": format_size(metadata.size),
                "modified": metadata.server_modified.isoformat() if metadata.server_modified else None,
                "client_modified": metadata.client_modified.isoformat() if metadata.client_modified else None,
                "rev": metadata.rev,
                "content_hash": metadata.content_hash,
                "is_downloadable": metadata.is_downloadable
            })
        
        return result
    except ApiError as e:
        return {"success": False, "error": str(e)}

def download_file(path: str, as_text: bool = True) -> Dict:
    """Download a file from Dropbox."""
    try:
        dbx = get_dropbox_client()
        metadata, response = dbx.files_download(path)
        content = response.content
        
        result = {
            "success": True,
            "name": metadata.name,
            "path": metadata.path_display,
            "size": metadata.size
        }
        
        if as_text:
            try:
                result["content"] = content.decode('utf-8')
                result["encoding"] = "utf-8"
            except UnicodeDecodeError:
                import base64
                result["content"] = base64.b64encode(content).decode('ascii')
                result["encoding"] = "base64"
                result["note"] = "Binary file returned as base64"
        else:
            import base64
            result["content"] = base64.b64encode(content).decode('ascii')
            result["encoding"] = "base64"
        
        return result
    except ApiError as e:
        return {"success": False, "error": str(e)}

def read_text_file(path: str, max_bytes: int = 1000000) -> Dict:
    """Read text content from a file."""
    try:
        dbx = get_dropbox_client()
        metadata, response = dbx.files_download(path)
        
        content = response.content[:max_bytes]
        truncated = len(response.content) > max_bytes
        
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
        
        return {
            "success": True,
            "name": metadata.name,
            "path": metadata.path_display,
            "size": metadata.size,
            "content": text,
            "truncated": truncated,
            "bytes_read": len(content)
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def upload_file(path: str, content: str, is_base64: bool = False, overwrite: bool = True) -> Dict:
    """Upload a file to Dropbox."""
    try:
        dbx = get_dropbox_client()
        
        if is_base64:
            import base64
            data = base64.b64decode(content)
        else:
            data = content.encode('utf-8')
        
        mode = WriteMode.overwrite if overwrite else WriteMode.add
        
        metadata = dbx.files_upload(data, path, mode=mode)
        
        return {
            "success": True,
            "name": metadata.name,
            "path": metadata.path_display,
            "size": metadata.size,
            "size_human": format_size(metadata.size),
            "rev": metadata.rev
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def create_folder(path: str) -> Dict:
    """Create a folder in Dropbox."""
    try:
        dbx = get_dropbox_client()
        metadata = dbx.files_create_folder_v2(path)
        
        return {
            "success": True,
            "name": metadata.metadata.name,
            "path": metadata.metadata.path_display
        }
    except ApiError as e:
        if "path/conflict/folder" in str(e):
            return {"success": True, "message": "Folder already exists", "path": path}
        return {"success": False, "error": str(e)}

def move_file(from_path: str, to_path: str) -> Dict:
    """Move or rename a file/folder."""
    try:
        dbx = get_dropbox_client()
        metadata = dbx.files_move_v2(from_path, to_path)
        
        return {
            "success": True,
            "from_path": from_path,
            "to_path": metadata.metadata.path_display
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def copy_file(from_path: str, to_path: str) -> Dict:
    """Copy a file/folder."""
    try:
        dbx = get_dropbox_client()
        metadata = dbx.files_copy_v2(from_path, to_path)
        
        return {
            "success": True,
            "from_path": from_path,
            "to_path": metadata.metadata.path_display
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def delete_file(path: str) -> Dict:
    """Delete a file/folder (moves to trash)."""
    try:
        dbx = get_dropbox_client()
        metadata = dbx.files_delete_v2(path)
        
        return {
            "success": True,
            "deleted_path": metadata.metadata.path_display,
            "note": "File moved to trash - can be recovered from Dropbox"
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def get_shared_link(path: str, create_if_missing: bool = True) -> Dict:
    """Get or create a shared link."""
    try:
        dbx = get_dropbox_client()
        
        # Try to get existing links
        try:
            links = dbx.sharing_list_shared_links(path=path, direct_only=True)
            if links.links:
                link = links.links[0]
                return {
                    "success": True,
                    "url": link.url,
                    "path": link.path_lower,
                    "existing": True
                }
        except ApiError:
            pass
        
        # Create new link if requested
        if create_if_missing:
            settings = dropbox.sharing.SharedLinkSettings(
                requested_visibility=dropbox.sharing.RequestedVisibility.public
            )
            link = dbx.sharing_create_shared_link_with_settings(path, settings)
            return {
                "success": True,
                "url": link.url,
                "path": link.path_lower,
                "existing": False
            }
        
        return {"success": False, "error": "No existing shared link found"}
    except ApiError as e:
        return {"success": False, "error": str(e)}

def list_revisions(path: str, limit: int = 10) -> Dict:
    """List file revisions."""
    try:
        dbx = get_dropbox_client()
        result = dbx.files_list_revisions(path, limit=limit)
        
        revisions = []
        for rev in result.entries:
            revisions.append({
                "rev": rev.rev,
                "size": rev.size,
                "size_human": format_size(rev.size),
                "modified": rev.server_modified.isoformat() if rev.server_modified else None
            })
        
        return {
            "success": True,
            "path": path,
            "count": len(revisions),
            "revisions": revisions
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def get_space_usage() -> Dict:
    """Get account storage usage."""
    try:
        dbx = get_dropbox_client()
        usage = dbx.users_get_space_usage()
        
        used = usage.used
        if usage.allocation.is_individual():
            allocated = usage.allocation.get_individual().allocated
        elif usage.allocation.is_team():
            allocated = usage.allocation.get_team().allocated
        else:
            allocated = None
        
        return {
            "success": True,
            "used": used,
            "used_human": format_size(used),
            "allocated": allocated,
            "allocated_human": format_size(allocated) if allocated else "Unlimited",
            "percent_used": round((used / allocated) * 100, 2) if allocated else None
        }
    except ApiError as e:
        return {"success": False, "error": str(e)}

def test_connection() -> Dict:
    """Test Dropbox connection."""
    try:
        dbx = get_dropbox_client()
        account = dbx.users_get_current_account()
        
        return {
            "success": True,
            "account_id": account.account_id,
            "name": account.name.display_name,
            "email": account.email,
            "account_type": str(account.account_type),
            "team": account.team.name if account.team else None
        }
    except AuthError as e:
        return {"success": False, "error": f"Authentication failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    if size_bytes is None:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def call_tool(name: str, arguments: Dict) -> Dict:
    """Route tool calls to implementations."""
    tool_map = {
        "list_folder": list_folder,
        "search_files": search_files,
        "get_file_metadata": get_file_metadata,
        "download_file": download_file,
        "read_text_file": read_text_file,
        "upload_file": upload_file,
        "create_folder": create_folder,
        "move_file": move_file,
        "copy_file": copy_file,
        "delete_file": delete_file,
        "get_shared_link": get_shared_link,
        "list_revisions": list_revisions,
        "get_space_usage": get_space_usage,
        "test_connection": test_connection
    }
    
    if name not in tool_map:
        return {"success": False, "error": f"Unknown tool: {name}"}
    
    try:
        return tool_map[name](**arguments)
    except Exception as e:
        logger.error(f"Tool {name} error: {e}")
        return {"success": False, "error": str(e)}

# ============================================================================
# MCP ROUTES
# ============================================================================

@app.route("/", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "service": "dropbox-mcp",
        "status": "healthy",
        "version": "1.0.0",
        "tools": len(TOOLS),
        "api_configured": bool(DROPBOX_ACCESS_TOKEN or DROPBOX_REFRESH_TOKEN)
    })

@app.route("/mcp", methods=["POST"])
def mcp_handler():
    """MCP JSON-RPC handler."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), 400
        
        method = data.get("method")
        params = data.get("params", {})
        msg_id = data.get("id", 1)
        
        logger.info(f"MCP request: {method}")
        
        if method == "initialize":
            return jsonify({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": "dropbox-mcp", "version": "1.0.0"}
                }
            })
        
        elif method == "notifications/initialized":
            return jsonify({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        
        elif method == "tools/list":
            return jsonify({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS}
            })
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            result = call_tool(tool_name, arguments)
            
            return jsonify({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
                }
            })
        
        else:
            return jsonify({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            })
    
    except Exception as e:
        logger.error(f"MCP error: {e}")
        return jsonify({
            "jsonrpc": "2.0",
            "id": data.get("id", 1) if data else 1,
            "error": {"code": -32603, "message": str(e)}
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Dropbox MCP on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
