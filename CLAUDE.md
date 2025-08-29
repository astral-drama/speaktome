
## Quick Workspace Creation

To create a new Docker workspace for development, use the CLI command:

```bash
filter workspace create <name> [--template <template-name>]
```

### Template Selection

```bash
# List available templates
filter workspace create --list-templates

# Create with default template (full-stack: Postgres + Claude)
filter workspace create myproject

# Create with specific templates
filter workspace create frontend --template minimal  # Claude only
filter workspace create datalab --template python    # Python + Jupyter + Postgres
```

### Examples

```bash
# Full-stack development workspaces
filter workspace create v4                # Default template
filter workspace create api --template default

# Lightweight workspaces (no database)
filter workspace create ui --template minimal
filter workspace create frontend --template minimal

# Python/Data Science workspaces  
filter workspace create ml --template python
filter workspace create analytics --template python
filter workspace create jupyter --template python

# Project-specific workspaces
filter workspace create auth-feature
filter workspace create microservice --template minimal
```

## Workspace Structure

Each created workspace follows this structure:

```
workspaces/<name>/
├── Dockerfile              # Claude container with dev tools
├── docker-compose.yml      # Postgres + Claude services
└── workspace/
    ├── .env                # Database credentials
    └── kanban/             # Full kanban directory copy
        ├── planning/
        ├── in-progress/
        ├── testing/
        ├── pr/
        ├── complete/
        ├── prompts/
        └── stories/
```

## Template Types

### default Template (Full-stack)
- **Services**: PostgreSQL 17 + Claude development container
- **Use case**: General full-stack development with database needs
- **Tools**: Node.js, Python, claude-code, PostgreSQL client, development tools

### minimal Template (Lightweight)
- **Services**: Claude development container only
- **Use case**: Frontend work, simple development tasks, when database isn't needed
- **Tools**: Node.js, Python, claude-code, development tools (no PostgreSQL client)

### python Template (Data Science)
- **Services**: PostgreSQL 17 + Claude container + Jupyter notebook server
- **Use case**: Python development, data science, machine learning projects
- **Tools**: Enhanced Python toolchain, Jupyter, testing tools, database

> 📖 **Complete template specifications**: See [`docker/README.md`](docker/README.md) for detailed template documentation.

## Container Details

### Postgres Container (default, python templates)
- **Image**: postgres:17
- **Container name**: postgres (always the same)
- **Database**: claude / claude / claudepassword321
- **Port**: Auto-detected (starts from 5433)
- **Volume**: `postgres_<workspace>_data`

### Claude Container (all templates)
- **Base**: debian:bookworm-slim
- **Container name**: claude (always the same)
- **Port**: Auto-detected (starts from 8001)
- **Common tools**:
  - Node.js LTS + npm
  - Python 3 + pip + uv + ruff
  - claude-code CLI
  - tmux, nano, emacs
  - sudo (passwordless for claude user)
- **Template-specific tools**:
  - postgresql-client (default, python templates)
  - Enhanced Python tools (python template)

### Jupyter Container (python template only)
- **Port**: Auto-detected (starts from 8888)
- **Access**: Available at `http://localhost:<jupyter_port>`

### Mounts
- `../../home:/home/claude` - Shared home across all workspaces
- `./workspace:/workspace` - Version-specific workspace

## Starting and Using Workspaces

1. **Create workspace**:
   ```bash
   filter workspace create myproject
   ```

2. **Start services**:
   ```bash
   cd workspaces/myproject
   docker compose up -d
   ```

3. **Access container**:
   ```bash
   docker exec -it claude tmux new-session -s claude -c /workspace
   ```

   **Or use the helper commands**:
   ```bash
   filter bash myproject        # Interactive bash shell
   filter claude myproject      # Start Claude session
   ```

4. **Check services**:
   ```bash
   docker compose ps
   ```

## Environment Variables

Environment variables vary by template:

### default Template
```bash
DATABASE_URL=postgresql://claude:claudepassword321@postgres:5432/claude
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=claude
POSTGRES_PASSWORD=claudepassword321
POSTGRES_DB=claude
CLAUDE_HOST_PORT=8001      # Auto-detected
CLAUDE_INTERNAL_PORT=8000
POSTGRES_HOST_PORT=5433    # Auto-detected
```

### minimal Template
```bash
CLAUDE_HOST_PORT=8001      # Auto-detected
CLAUDE_INTERNAL_PORT=8000
```

### python Template
```bash
DATABASE_URL=postgresql://claude:claudepassword321@postgres:5432/claude
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=claude
POSTGRES_PASSWORD=claudepassword321
POSTGRES_DB=claude
CLAUDE_HOST_PORT=8001      # Auto-detected
CLAUDE_INTERNAL_PORT=8000
POSTGRES_HOST_PORT=5433    # Auto-detected
JUPYTER_PORT=8888          # Auto-detected
```

## Common Development Patterns

### Database Connection
```bash
# From within Claude container
psql $DATABASE_URL

# Or using individual vars
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB
```

### Port Information
The CLI automatically finds available ports and reports them:
```
INFO:filter.workspace:Using ports - Postgres: 5433, Claude: 8001
```

### Kanban Access
All kanban files are available in the container at `/workspace/kanban/`:
- `/workspace/kanban/prompts/` - LLM prompts
- `/workspace/kanban/stories/` - Story definitions
- `/workspace/kanban/planning/` - Planned work
- etc.

## Workspace Management

### List Running Services
```bash
docker compose ps
```

### Stop Workspace
```bash
filter workspace down <name>
# OR manually:
docker compose down
```

### Remove Workspace (keeps data)
```bash
filter workspace delete <name>
# OR manually:
docker compose down
rm -rf workspaces/<name>
```

### Remove Workspace + Data (force delete running workspace)
```bash
filter workspace delete <name> --force
# OR manually:
docker compose down -v  # Removes volumes too
rm -rf workspaces/<name>
```

### Multiple Workspaces
You can run multiple workspaces simultaneously since ports are auto-detected:
```bash
filter workspace create api --template default   # Gets ports 5433, 8001
filter workspace create ui --template minimal    # Gets port 8002  
filter workspace create ml --template python     # Gets ports 5434, 8003, 8888
```

## Troubleshooting

### Container Won't Start
- Check if ports are available: `netstat -tuln | grep <port>`
- Check Docker logs: `docker compose logs`
- Rebuild container: `docker compose build --no-cache`

### Port Conflicts
The CLI automatically finds available ports, but if you need specific ports, you can manually edit `docker-compose.yml`.

### Database Issues
- Check Postgres logs: `docker compose logs postgres`
- Reset database: `docker compose down -v && docker compose up -d postgres`

### Shared Home Directory
The `../../home` directory is shared across ALL workspaces. Use it for:
- SSH keys
- Git configuration
- Shared tools/scripts
- Claude Code settings

## Best Practices

1. **Use descriptive workspace names**: `auth-service`, `frontend-v2`, `migration-testing`
2. **One workspace per feature/project** for isolation
3. **Keep shared tools in `home/`** directory
4. **Use the kanban structure** in `/workspace/kanban/` for organization
5. **Clean up unused workspaces** to save disk space
6. **Check ports** with `docker compose ps` before creating new workspaces

## CLI Command Reference

```bash
# Workspace creation
filter workspace create --list-templates           # List available templates
filter workspace create <name>                     # Create with default template
filter workspace create <name> --template <type>   # Create with specific template
filter workspace create <name> --base-dir <dir>    # Custom base directory

# Workspace management
filter workspace down <name>                       # Stop workspace containers
filter workspace delete <name>                     # Delete stopped workspace
filter workspace delete <name> --force             # Force delete running workspace

# Project management
filter project create <name>                       # Create new project with kanban
filter project create <name> --description "desc"  # Create with description
filter project create <name> --git-url <url>       # Create with git URL
filter project create <name> --maintainer <email>  # Create with maintainer
filter project create <name> --no-kanban           # Create project without kanban
filter project list                                # List all projects
filter project delete <name>                       # Delete project
filter project delete <name> --force               # Force delete project

# Story workspaces
filter story <story-name>                          # Create workspace for story
filter story <story-name> --template <template>    # Create with specific template

# Workspace access helpers
filter bash <workspace-name>                              # Interactive bash shell
filter claude <workspace-name>                            # Start Claude session
filter claude <workspace-name> -r                         # Start Claude session with resume
filter bash <workspace-name> -c "command"                 # Run command and exit

# Template rendering (original functionality)
filter template <template> [--var key=val] [--config file] [--env-file file]

# Help
filter --help
filter workspace --help
filter workspace create --help
filter workspace down --help
filter workspace delete --help
filter project --help
filter project create --help
filter project list --help
filter project delete --help
filter bash --help
filter claude --help
filter template --help
```

## Project Management

The Filter system includes project management capabilities for organizing stories and kanban boards by project. This helps keep stories from different projects separate and organized.

### Project Structure

Each project follows this structure:

```
projects/<project-name>/
├── project.yaml           # Project configuration with prefix and metadata
└── kanban/
    ├── planning/
    ├── in-progress/
    ├── testing/
    ├── pr/
    ├── complete/
    ├── prompts/
    └── stories/
```

### Creating Projects

```bash
# Create a new project with kanban structure
filter project create ib-stream

# Create a project with metadata
filter project create marketbridge \
  --description "Multi-market trading bridge system" \
  --git-url "https://github.com/user/marketbridge.git" \
  --maintainer "developer@example.com" \
  --maintainer "lead@example.com"

# Create a project without kanban structure
filter project create simple-tool --no-kanban

# Create project in custom directory
filter project create analytics --base-dir /custom/projects
```

### Managing Projects

```bash
# List all projects
filter project list

# Delete a project
filter project delete old-project

# Force delete without confirmation
filter project delete old-project --force
```

### Project Configuration

Each project includes a `project.yaml` configuration file with:

```yaml
name: marketbridge
prefix: marke                                    # Auto-generated 5-char prefix
description: Multi-market trading bridge system
git_url: https://github.com/user/marketbridge.git
maintainers:
- developer@example.com
- lead@example.com
created_at: null
version: '1.0'
```

### Story Naming with Prefixes

The auto-generated prefix helps create consistent story and branch names:

- **Story examples**: `marke-1`, `marke-2-refactor`, `marke-15-auth-fix`  
- **Branch examples**: `marke-1`, `marke-2-refactor`, `marke-15-auth-fix`
- **Prefix generation**: `ib-stream` → `ibstr`, `marketbridge` → `marke`

### Example Workflow

1. **Create project**: `filter project create ib-stream`
2. **Note the prefix**: Project creates with prefix `ibstr` for story naming
3. **Organize stories**: Create stories like `ibstr-1.md`, `ibstr-2-optimization.md`
4. **Plan work**: Move stories from `stories/` to `planning/` 
5. **Track progress**: Move through `in-progress/` → `testing/` → `pr/` → `complete/`
6. **Branch naming**: Use same prefix for git branches: `ibstr-1`, `ibstr-2-optimization`

### Benefits

- **Story Organization**: Keep stories separated by project
- **Consistent Naming**: Auto-generated prefixes for stories and branches
- **Project Metadata**: Track descriptions, git URLs, and maintainers
- **Kanban Isolation**: Each project has its own kanban board
- **Flexible Structure**: Projects can exist with or without kanban
- **Easy Management**: Simple CLI commands for project lifecycle

## Story Workspaces

The Filter system can create dedicated workspaces for individual stories, providing an isolated development environment with project context.

### Creating Story Workspaces

```bash
# Create workspace for a story (searches all projects)
filter story ibstr-1

# Create with specific template
filter story marke-2-refactor --template python
```

### Story Workspace Features

When you create a story workspace:

1. **Automatic Discovery**: Finds the story across all projects
2. **Project Context**: Workspace is named after the story (e.g., `ibstr-1`)
3. **Kanban Mounting**: Project's kanban directory is mounted at `/workspace/kanban`
4. **Environment Variables**: Story context available in `.env`:
   ```bash
   PROJECT_NAME=ib-stream
   STORY_NAME=ibstr-1
   STORY_PATH=kanban/stories/ibstr-1.md
   ```

### Example Story Workspace

```bash
# Create story workspace
filter story ibstr-1

# Output shows project context
# Story workspace 'ibstr-1' created at: /path/to/workspaces/ibstr-1
# Project: ib-stream
# Story file: stories/ibstr-1.md

# Start the workspace
cd /path/to/workspaces/ibstr-1
docker compose up -d

# Access your story file
filter claude ibstr-1
# Story file available at: /workspace/kanban/stories/ibstr-1.md
```

### Benefits

- **Story-Focused Development**: Workspace named and configured for specific story
- **Project Context**: Full access to project's kanban structure
- **Environment Integration**: Story details available as environment variables
- **Consistent Naming**: Workspace name matches story name and git branch conventions

This workspace system provides isolated, reproducible development environments with automatic port management and full kanban integration.

---

> 📖 **Additional Resources:**
> - [`docker/README.md`](docker/README.md) - Complete template documentation and customization guide
> - [`README.md`](README.md) - Main project documentation and getting started guide