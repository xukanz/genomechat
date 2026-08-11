"""Database context prompt utilities."""

from pathlib import Path


def get_database_context_path(context_file: str) -> Path:
    """Get the full path to a database context file.

    Args:
        context_file: Name of the context file (e.g., "clinvar_context.md")

    Returns:
        Path to the context file
    """
    return Path(__file__).parent / context_file


def load_database_context(context_file: str) -> str:
    """Load database context from file.

    Args:
        context_file: Name of the context file (e.g., "clinvar_context.md")

    Returns:
        Content of the context file

    Raises:
        FileNotFoundError: If context file doesn't exist
    """
    path = get_database_context_path(context_file)
    if not path.exists():
        raise FileNotFoundError(f"Database context file not found: {path}")
    return path.read_text()
