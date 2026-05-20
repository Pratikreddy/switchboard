"""Shared framework defaults."""

DEFAULT_NODE_PORT = 8020

DEFAULT_EXCLUDE_GLOBS = [
    "venv",
    ".venv",
    "__pycache__",
    "node_modules",
    ".git",
    "dist",
    "build",
    "tmp",
    "temp",
    "generated_docs",
    ".env",
    ".env.*",
    ".npmrc",
    "*.pyc",
]

DEFAULT_SECRET_PATTERNS = [
    ".env",
    ".env.*",
    "*secret*",
    "*password*",
    "*credential*",
    "*.pem",
    "*.key",
    "id_rsa",
    "authorized_keys",
]

SAFE_REMOTE_COMMANDS = {
    "hostname": "hostname",
    "whoami": "whoami",
    "date": "date -Is",
    "uname": "uname -a",
    "pwd": "pwd",
    "ports": "ss -ltnp",
    "firewall": "ufw status",
    "services": "systemctl list-units --type=service --state=running --no-pager --no-legend",
    "docker": "docker ps --format '{{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
}

GIT_STATUS_COMMANDS = {
    "branch": "git -C {path} branch --show-current",
    "status": "git -C {path} status --short",
    "last_commit": "git -C {path} log -1 --format=%H%x09%cI%x09%s",
    "remotes": "git -C {path} remote -v",
    "rev_parse": "git -C {path} rev-parse --show-toplevel",
}
