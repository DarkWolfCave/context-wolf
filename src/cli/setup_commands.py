"""
Setup commands that run WITHOUT a database connection.
Used for initial setup (cm init) and diagnostics (cm doctor).
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def cmd_init(args):
    """Interactive setup wizard for new users."""
    print("🚀 ContextWolf - Setup")
    print()

    config_path = Path.home() / '.context' / 'config.yaml'

    if config_path.exists():
        print(f"⚠️  Config already exists: {config_path}")
        response = input("   Overwrite? (y/N) ").strip().lower()
        if response != 'y':
            print("   Aborted.")
            return

    # Ask: Docker or external?
    print("How do you want to run PostgreSQL?")
    print()
    print("  [1] Local Docker (recommended - we start it for you)")
    print("  [2] External server (you already have PostgreSQL running)")
    print()
    choice = input("Choice (1/2): ").strip()

    if choice == '1':
        _init_docker(config_path)
    elif choice == '2':
        _init_external(config_path)
    else:
        print("❌ Invalid choice.")
        return

    # Test connection
    print()
    print("🔍 Testing connection...")
    try:
        from src.core.config import Config
        from src.core.database import Database
        config = Config()
        db = Database(config=config)
        result = db.fetchone("SELECT 1 as ok")
        db.close()
        if result and result['ok'] == 1:
            print("✅ Connection successful!")
        else:
            print("❌ Connection test failed.")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print(f"   Check your config: {config_path}")
        return

    print()
    print("🎉 Setup complete!")
    print()
    print("Next steps:")
    print("  cm stats                 # Verify everything works")
    print("  cm setup-mcp             # Configure Claude Code integration")


def _init_docker(config_path):
    """Start PostgreSQL via docker compose and write config."""
    # Check docker is available
    if not shutil.which('docker'):
        print("❌ Docker not found. Install Docker Desktop first.")
        return

    # Find docker-compose.yml
    compose_file = Path(__file__).parent.parent.parent / 'docker-compose.yml'
    if not compose_file.exists():
        print(f"❌ docker-compose.yml not found at {compose_file}")
        return

    print()
    print("Starting PostgreSQL + pgvector...")
    result = subprocess.run(
        ['docker', 'compose', '-f', str(compose_file), 'up', '-d'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"❌ Docker failed: {result.stderr}")
        return

    print("✅ PostgreSQL container started (port 5432)")

    # Write config
    _write_config(config_path, host='localhost', port=5432,
                  database='context_manager', user='cm_user', password='changeme')


def _init_external(config_path):
    """Ask for external PostgreSQL credentials and write config."""
    print()
    print("Enter your PostgreSQL connection details:")
    host = input("  Host [localhost]: ").strip() or 'localhost'
    port = input("  Port [5432]: ").strip() or '5432'
    database = input("  Database [context_manager]: ").strip() or 'context_manager'
    user = input("  User [cm_user]: ").strip() or 'cm_user'
    password = input("  Password: ").strip()

    _write_config(config_path, host=host, port=int(port),
                  database=database, user=user, password=password)


def _write_config(config_path, host, port, database, user, password):
    """Write ~/.context/config.yaml"""
    config_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""database:
  backend: postgres
  postgres:
    host: {host}
    port: {port}
    database: {database}
    user: {user}
    password: {password}
"""
    config_path.write_text(content)
    os.chmod(config_path, 0o600)  # Restrict permissions (contains password)
    print(f"✅ Config written: {config_path} (mode 600)")


def cmd_doctor(args):
    """Check prerequisites and system health."""
    print("🩺 ContextWolf - Doctor")
    print()
    issues = 0

    # 1. Python version
    py_version = sys.version_info
    if py_version >= (3, 10):
        print(f"✅ Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        print(f"❌ Python {py_version.major}.{py_version.minor} - need 3.10+")
        issues += 1

    # 2. uv
    if shutil.which('uv'):
        result = subprocess.run(['uv', '--version'], capture_output=True, text=True)
        print(f"✅ {result.stdout.strip()}")
    else:
        print("⚠️  uv not found (optional, but recommended)")

    # 3. Docker
    if shutil.which('docker'):
        print("✅ Docker available")
    else:
        print("⚠️  Docker not found (needed for local PostgreSQL)")

    # 4. Config file
    config_path = Path.home() / '.context' / 'config.yaml'
    if config_path.exists():
        print(f"✅ Config: {config_path}")
    else:
        print(f"❌ Config missing: {config_path}")
        print("   Run: cm init")
        issues += 1

    # 5. PostgreSQL connection
    try:
        from src.core.config import Config
        from src.core.database import Database
        config = Config()
        db = Database(config=config)
        result = db.fetchone("SELECT version() as v")
        pg_version = result['v'].split(',')[0] if result else 'unknown'
        db.close()
        print(f"✅ PostgreSQL: {pg_version}")
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        print(f"❌ PostgreSQL: {error_msg}")
        issues += 1

    # 6. pgvector extension
    try:
        from src.core.config import Config
        from src.core.database import Database
        config = Config()
        db = Database(config=config)
        result = db.fetchone("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        if result:
            print(f"✅ pgvector: {result['extversion']}")
        else:
            print("⚠️  pgvector not installed (semantic search won't work)")
        db.close()
    except Exception:
        pass  # Already reported above

    # 7. MCP config
    claude_json = Path.home() / '.claude.json'
    if claude_json.exists():
        import json
        try:
            data = json.loads(claude_json.read_text())
            mcp_servers = data.get('mcpServers', {})
            if 'context-manager' in mcp_servers:
                print("✅ MCP: configured in ~/.claude.json")
            else:
                print("⚠️  MCP: not configured (run: cm setup-mcp)")
        except Exception:
            print("⚠️  MCP: ~/.claude.json exists but can't be parsed")
    else:
        print("⚠️  MCP: ~/.claude.json not found")

    # 8. Embedding model
    model_path = Path(__file__).parent.parent.parent / 'embedding_worker' / 'model' / 'model.onnx'
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"✅ Embedding model: {size_mb:.0f}MB")
    else:
        print("⚠️  Embedding model not downloaded (semantic search won't work)")

    # Summary
    print()
    if issues == 0:
        print("🎉 Everything looks good!")
    else:
        print(f"⚠️  {issues} issue(s) found. Fix them and run cm doctor again.")


def cmd_setup_mcp(args):
    """Configure MCP server in ~/.claude.json"""
    import json

    claude_json = Path.home() / '.claude.json'
    project_dir = Path(__file__).parent.parent.parent.resolve()

    mcp_entry = {
        "type": "stdio",
        "command": "uv",
        "args": [
            "--directory", str(project_dir),
            "run", "cm-mcp"
        ]
    }

    if claude_json.exists():
        data = json.loads(claude_json.read_text())
    else:
        data = {}

    if 'mcpServers' not in data:
        data['mcpServers'] = {}

    old = data['mcpServers'].get('context-manager')
    data['mcpServers']['context-manager'] = mcp_entry

    claude_json.write_text(json.dumps(data, indent=2) + '\n')

    if old:
        print("✅ MCP config updated in ~/.claude.json")
    else:
        print("✅ MCP config added to ~/.claude.json")

    print(f"   Server: uv --directory {project_dir} run cm-mcp")
    print()
    print("Restart Claude Code to apply changes.")
