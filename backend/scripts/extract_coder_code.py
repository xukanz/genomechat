"""Extract executed code from a conversation's LangGraph checkpoint.

Usage:
    uv run python scripts/extract_coder_code.py <thread_id>
"""

import json
import sys

from langgraph.checkpoint.mongodb import MongoDBSaver

from src.config.settings import settings
from src.service.database.connections.mongodb_connection import get_mongodb_client


def extract_code_from_checkpoint(thread_id: str) -> None:
    """Load checkpoint messages and extract execute_code tool calls."""
    client = get_mongodb_client()
    db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
    saver = MongoDBSaver(client, db_name=db_name)

    config = {"configurable": {"thread_id": thread_id}}

    # Get the latest checkpoint
    checkpoint_tuple = saver.get_tuple(config)
    if not checkpoint_tuple:
        print(f"No checkpoint found for thread_id: {thread_id}")
        return

    checkpoint = checkpoint_tuple.checkpoint
    channel_values = checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])

    print(f"Found {len(messages)} messages in checkpoint\n")
    print("=" * 80)

    code_blocks = []
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        msg_name = getattr(msg, "name", None)

        # Look for AIMessage with tool_calls containing execute_code
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "execute_code":
                    args = tc.get("args", {})
                    source = args.get("source", "")
                    if source:
                        code_blocks.append(source)
                        print(f"\n{'=' * 80}")
                        print(
                            f"CODE BLOCK #{len(code_blocks)} (from message [{i}] {msg_type}"
                            f" name={msg_name})"
                        )
                        print(f"{'=' * 80}")
                        # Print s3_inputs/s3_outputs if present
                        if args.get("s3_inputs"):
                            print(f"S3 Inputs: {json.dumps(args['s3_inputs'], indent=2)}")
                        if args.get("s3_outputs"):
                            print(f"S3 Outputs: {json.dumps(args['s3_outputs'], indent=2)}")
                        print(f"{'─' * 80}")
                        print(source)
                        print(f"{'─' * 80}\n")

        # Also look for ToolMessage results from execute_code
        if msg_name == "execute_code" and msg_type == "ToolMessage":
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            # Truncate long outputs
            if len(content) > 2000:
                content = content[:2000] + f"\n... [truncated, {len(content)} total chars]"
            print(f"\n{'=' * 80}")
            print(f"EXECUTION RESULT (message [{i}])")
            print(f"{'=' * 80}")
            print(content)
            print()

    print(f"\n{'=' * 80}")
    print(f"Total code blocks executed: {len(code_blocks)}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default to the survival analysis conversation
        thread_id = "40a63857-7a96-4b77-914b-ce222112fe17:27764550-18cb-49e8-a3a9-2d1205561d80"
        print(f"Using default thread_id: {thread_id}")
    else:
        thread_id = sys.argv[1]

    extract_code_from_checkpoint(thread_id)
