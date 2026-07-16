from __future__ import annotations

from pathlib import PurePosixPath


SPECIAL_FILES = {
    "dockerfile": "Dockerfile",
    "makefile": "Makefile",
    "jenkinsfile": "Jenkins Pipeline",
    "gemfile": "Ruby",
    "rakefile": "Ruby",
    "cargo.lock": "Rust",
    "package-lock.json": "JSON",
    "pnpm-lock.yaml": "YAML",
    "yarn.lock": "Yarn Lock",
    "poetry.lock": "TOML",
}

EXTENSIONS = {
    ".py": "Python", ".pyi": "Python", ".pyx": "Cython",
    ".js": "JavaScript", ".jsx": "JavaScript/React", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript/React", ".d.ts": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".go": "Go", ".rs": "Rust", ".c": "C", ".h": "C/C++ Header",
    ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++ Header",
    ".cs": "C#", ".php": "PHP", ".rb": "Ruby", ".swift": "Swift",
    ".scala": "Scala", ".dart": "Dart", ".lua": "Lua", ".r": "R",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".fish": "Shell", ".ps1": "PowerShell",
    ".sql": "SQL", ".html": "HTML", ".htm": "HTML", ".css": "CSS",
    ".scss": "SCSS", ".sass": "Sass", ".less": "Less", ".vue": "Vue", ".svelte": "Svelte",
    ".xml": "XML", ".json": "JSON", ".jsonc": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".ini": "INI", ".cfg": "Config", ".conf": "Config",
    ".md": "Markdown", ".mdx": "Markdown", ".rst": "reStructuredText", ".txt": "Text",
    ".tex": "LaTeX", ".ipynb": "Jupyter Notebook", ".gradle": "Gradle",
    ".tf": "Terraform", ".tfvars": "Terraform", ".hcl": "HCL", ".proto": "Protocol Buffers",
    ".graphql": "GraphQL", ".gql": "GraphQL", ".sol": "Solidity", ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".hrl": "Erlang", ".clj": "Clojure", ".cljs": "ClojureScript",
}


def classify_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    lower_name = pure.name.lower()
    if lower_name in SPECIAL_FILES:
        return SPECIAL_FILES[lower_name]
    if lower_name.endswith(".d.ts"):
        return "TypeScript"
    suffix = pure.suffix.lower()
    return EXTENSIONS.get(suffix, "Other")


def file_type(path: str) -> str:
    """Stable, human-readable type for filtering the current HEAD."""
    pure = PurePosixPath(path.replace("\\", "/"))
    name = pure.name.lower()
    if name in SPECIAL_FILES:
        return name
    if name.endswith(".d.ts"):
        return ".d.ts"
    return pure.suffix.lower() or "[ohne Endung]"


def top_directory(path: str) -> str:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return parts[0] if len(parts) > 1 else "[root]"
