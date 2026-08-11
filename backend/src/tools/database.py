"""Database tools for SQL query execution and schema retrieval.

Provides LangChain tools wrapping DatabaseManager for use in agent workflows.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
from langchain_core.tools import tool

from src.config.database import DatabaseSettings
from src.config.database_registry import get_active_profile_from_context
from src.service.database import DatabaseManager
from src.service.observability import trace_tool
from src.utils.context import thread_id_context

logger = logging.getLogger(__name__)

# Per-user database manager cache
# Key: "profile_name" for shared DBs, "profile_name:username" for per-user DBs
_db_managers: dict[str, DatabaseManager] = {}
_MAX_CACHED_MANAGERS = 50


def get_database_manager() -> DatabaseManager:
    """Get or create database manager for the active registry profile.

    Uses database_id_context (request-scoped) with fallback to global state.

    Returns:
        DatabaseManager instance for active profile
    """
    global _db_managers

    profile = get_active_profile_from_context()
    cache_key = profile.name

    if cache_key not in _db_managers:
        # Evict oldest if cache is full
        if len(_db_managers) >= _MAX_CACHED_MANAGERS:
            oldest_key = next(iter(_db_managers))
            try:
                _db_managers[oldest_key].close()
            except Exception:
                pass
            del _db_managers[oldest_key]

        settings = DatabaseSettings.from_profile(profile)
        _db_managers[cache_key] = DatabaseManager(settings)
        logger.info(f"Database manager created for: {cache_key}")

    return _db_managers[cache_key]


def reset_database_manager() -> None:
    """Reset all cached database managers.

    Call this after changing the active database profile to force
    recreation on next access.
    """
    global _db_managers
    for manager in _db_managers.values():
        try:
            manager.close()
        except Exception:
            pass
    _db_managers.clear()


@trace_tool
@tool
def execute_sql_query(query: str) -> str:
    """Executes a given SQL query against the database and returns the result.

    Args:
        query: The SQL query string to be executed.

    Returns:
        A string representation of the query result (dataframe) or an error message.
    """
    try:
        logger.info(f"Executing SQL query: {query[:100]}...")

        # Get database manager
        db_manager = get_database_manager()

        # Execute query and get results as DataFrame for better formatting
        result_df = db_manager.execute_query_df(query)

        if result_df.empty:
            return "Query executed successfully but returned no results."

        # Format the results as a readable string
        result_str = f"Query executed successfully. Results ({len(result_df)} rows):\n\n"
        result_str += result_df.to_string(index=False, max_rows=100)

        if len(result_df) > 100:
            result_str += f"\n\n... (showing first 100 rows of {len(result_df)} total rows)"

        logger.info(f"SQL query executed successfully, returned {len(result_df)} rows")
        return result_str

    except TimeoutError as e:
        error_msg = (
            f"SQL query execution timed out: {str(e)}\n\n"
            f"This query may be too complex or the database may be locked. "
            f"Consider:\n"
            f"- Simplifying the query (reduce JOINs, add more specific WHERE clauses)\n"
            f"- Adding LIMIT clauses to reduce result set size\n"
            f"- Breaking the query into smaller parts\n"
            f"- Checking if other processes are accessing the database"
        )
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error executing SQL query: {str(e)}"
        logger.error(error_msg)
        return error_msg


@trace_tool
@tool
def execute_sql_query_and_save(query: str, description: str = "") -> str:
    """Executes a SQL query and saves the full results to a CSV file for downstream processing.

    This tool provides a hybrid approach: shows meaningful summary and preview in the message
    while saving complete data to file for detailed analysis by specialized agents.

    Args:
        query: The SQL query string to be executed.
        description: Optional description of what the query does (for file naming).

    Returns:
        A string containing summary, key insights, preview, and file path information.
    """
    try:
        logger.info(f"Executing SQL query and saving results: {query[:100]}...")

        # Get database manager
        db_manager = get_database_manager()

        # Execute query and get results as DataFrame
        result_df = db_manager.execute_query_df(query)

        if result_df.empty:
            return "Query executed successfully but returned no results."

        # Get user_id and thread_id from context
        # Extract thread_id from context variable
        thread_id = thread_id_context.get()

        # Extract user_id from thread_id if format is user_id:conversation_id
        user_id = None
        if thread_id and ":" in thread_id:
            user_id = thread_id.split(":")[0] if thread_id.split(":")[0] != "anonymous" else None

        # Generate a unique filename based on query content
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_id = str(uuid.uuid4())[:8]

        # Try to infer content type from query for better naming
        query_lower = query.lower()
        content_type = "data"

        if "antigen_species" in query_lower:
            content_type = "antigen_species"
        elif "antigen_epitope" in query_lower or "epitope" in query_lower:
            content_type = "epitope"
        elif "mhc_class" in query_lower:
            content_type = "mhc_class"
        elif "chains" in query_lower:
            content_type = "chains"
        elif description:
            # Clean description for filename
            clean_desc = "".join(
                c for c in description if c.isalnum() or c in (" ", "_", "-")
            ).rstrip()
            content_type = clean_desc.replace(" ", "_")[:30]  # Max 30 chars

        filename = f"query_results_{content_type}_{timestamp}_{query_id}.csv"

        # Determine S3 bucket and key
        from src.config.settings import settings

        s3_bucket = settings.aws_default_bucket
        s3_key = None
        file_path = None
        file_id = query_id

        if s3_bucket:
            # Generate S3 key with user_id prefix
            if user_id:
                s3_key = f"users/{user_id}/query_results/{filename}"
            else:
                s3_key = f"users/anonymous/query_results/{filename}"

            # Save to S3 via FileStorageService
            from src.service.storage.file_storage_service import FileStorageService
            from src.models.file_storage import FileRecordCreate, FileType

            file_storage_service = FileStorageService()
            file_data = FileRecordCreate(
                user_id=user_id,
                thread_id=thread_id,
                file_type=FileType.QUERY_RESULT,
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                content_type=content_type,
                size_bytes=0,  # Will be calculated automatically
                metadata={
                    "query": query,
                    "description": description,
                    "row_count": len(result_df),
                    "column_count": len(result_df.columns),
                    "columns": result_df.columns.tolist(),
                },
            )
            saved_result = file_storage_service.save_file_from_dataframe(result_df, file_data)
            file_id = saved_result.file_id
        else:
            # Fallback to local filesystem if S3 bucket not configured
            logger.warning("AWS_DEFAULT_BUCKET not set, falling back to local filesystem")
            outputs_dir = "outputs"
            os.makedirs(outputs_dir, exist_ok=True)
            file_path = os.path.join(outputs_dir, filename)
            result_df.to_csv(file_path, index=False)

        # Generate meaningful summary and insights
        total_rows = len(result_df)
        total_cols = len(result_df.columns)

        # Provide intelligent preview based on dataset size
        if total_rows <= 20:
            # Small dataset: show all rows
            preview_rows = total_rows
            preview_note = "(complete dataset)"
            preview = result_df.to_string(index=False)
        elif total_rows <= 100:
            # Medium dataset: show first 20 rows
            preview_rows = 20
            preview_note = f"(showing first {preview_rows} rows)"
            preview = result_df.head(preview_rows).to_string(index=False)
        else:
            # Large dataset: show first 15 rows + summary statistics
            preview_rows = 15
            preview_note = f"(showing first {preview_rows} rows)"
            preview = result_df.head(preview_rows).to_string(index=False)

        # Generate key insights for numeric columns
        insights = []
        numeric_cols = result_df.select_dtypes(include=["number"]).columns
        if len(numeric_cols) > 0:
            insights.append("\nKey Insights:")
            for col in numeric_cols[:3]:  # Limit to first 3 numeric columns
                col_stats = result_df[col].describe()
                insights.append(
                    f"- {col}: Mean={col_stats['mean']:.2f}, Std={col_stats['std']:.2f}, "
                    f"Range=[{col_stats['min']:.2f}, {col_stats['max']:.2f}]"
                )

        # Check for categorical patterns
        categorical_cols = result_df.select_dtypes(include=["object"]).columns
        if len(categorical_cols) > 0 and len(categorical_cols) <= 3:
            insights.append("\nData Distribution:")
            for col in categorical_cols:
                unique_count = result_df[col].nunique()
                if unique_count <= 10:  # Only show for columns with reasonable number of categories
                    top_values = result_df[col].value_counts().head(3)
                    insights.append(
                        f"- {col}: {unique_count} unique values, top: {dict(top_values)}"
                    )

        insights_text = "\n".join(insights) if insights else ""

        # Create comprehensive result string
        if s3_key:
            # S3 path
            file_path_display = f"s3://{s3_bucket}/{s3_key}"
            file_path_note = f"S3 path: {file_path_display}"
            load_instructions = (
                f"The complete dataset ({total_rows:,} rows) has been saved to S3 at '{file_path_display}' "
                f"and can be loaded by specialized analysis agents using S3 file loading tools.\n\n"
                f"Next Steps for Analysis Agents:\n"
                f"- Use `read_file_from_s3(bucket='{s3_bucket}', key='{s3_key}')` to read the file\n"
                f"- Use `read_csv_file('s3://{s3_bucket}/{s3_key}')` if the tool supports S3 paths\n"
                f'- Reference this dataset as "File #{file_id}" in subsequent analysis'
            )
        else:
            # Local filesystem fallback
            file_path_display = file_path
            file_path_note = f"Local path: {os.path.abspath(file_path)}"
            load_instructions = (
                f"The complete dataset ({total_rows:,} rows) has been saved to '{file_path}' "
                f"and can be loaded by specialized analysis agents using file loading tools.\n\n"
                f"Next Steps for Analysis Agents:\n"
                f"- Use `read_csv_file('{file_path}')` to inspect the dataset structure\n"
                f"- Use `load_csv_as_dataframe('{file_path}')` to get loading code for the complete dataset\n"
                f'- Reference this dataset as "File #{query_id}" in subsequent analysis'
            )

        result_str = f"""Query executed successfully and results saved to storage.

Summary:
- Total rows: {total_rows:,}
- Total columns: {total_cols}
- Columns: {", ".join(result_df.columns.tolist())}

DATASET FILE #{file_id if s3_key else query_id}: `{file_path_display}`
{file_path_note}
FILE ID: {file_id if s3_key else query_id}
DESCRIPTION: {description if description else "Data analysis results"}{insights_text}

Data Preview {preview_note}:
{preview}

For Detailed Analysis:
{load_instructions}"""

        if total_rows > 100:
            result_str += (
                f"\n\nNote: This message shows a preview for context. "
                f"The complete dataset with all {total_rows:,} rows is available in the saved file for comprehensive analysis."
            )

        if s3_key:
            logger.info(
                f"SQL query executed successfully, {len(result_df)} rows saved to S3: s3://{s3_bucket}/{s3_key}"
            )
        else:
            logger.info(
                f"SQL query executed successfully, {len(result_df)} rows saved to {file_path}"
            )
        return result_str

    except TimeoutError as e:
        error_msg = (
            f"SQL query execution timed out: {str(e)}\n\n"
            f"This query may be too complex or the database may be locked. "
            f"Consider:\n"
            f"- Simplifying the query (reduce JOINs, add more specific WHERE clauses)\n"
            f"- Adding LIMIT clauses to reduce result set size\n"
            f"- Breaking the query into smaller parts\n"
            f"- Checking if other processes are accessing the database"
        )
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error executing SQL query and saving results: {str(e)}"
        logger.error(error_msg)
        return error_msg


@trace_tool
@tool
def get_database_schema() -> str:
    """Returns the schema description of the active database.

    This tool reads the schema from a YAML file and does NOT require
    a database connection. It works even if the database is unavailable
    or configured with an S3 path.

    Returns:
        A string containing the database schema description.
    """
    try:
        logger.info("Fetching database schema...")

        # Get active profile for whitelist filtering
        profile = get_active_profile_from_context()

        # Get database manager (uses lazy connection - no DB connection yet)
        db_manager = get_database_manager()

        # Load schema description with optional whitelist filtering
        schema_description = db_manager.load_schema_description(
            allowed_tables=profile.allowed_tables,
        )

        logger.info("Database schema fetched successfully")
        return schema_description

    except Exception as e:
        error_msg = f"Error fetching database schema: {str(e)}"
        logger.error(error_msg)
        return error_msg


@trace_tool
@tool
def get_random_subsamples(tables: List[Dict[str, Any]], sample_size: int = 5) -> str:
    """Retrieve random data samples from specified database tables.

    Args:
        tables: List of tables with their columns to sample.
                Format: [{"table_name": "table1", "noun_columns": ["col1", "col2"]}, ...]
        sample_size: Number of random rows to retrieve per table (default: 5).

    Returns:
        A string containing the sample data or an error message.
    """
    try:
        logger.info(f"Getting random subsamples from {len(tables)} tables, {sample_size} rows each")

        # Get active profile for whitelist filtering
        profile = get_active_profile_from_context()

        # Get database manager and its settings
        db_manager = get_database_manager()
        db_settings = db_manager.settings

        # Helper function to get database-specific random function
        def get_random_function() -> str:
            SQL_RANDOM_FUNCTIONS = {
                "sqlite": "RANDOM()",
                "athena": "rand()",
                "postgres": "RANDOM()",
                "mysql": "RAND()",
                "mssql": "NEWID()",
            }
            db_type = db_settings.database_type.value.lower()
            return SQL_RANDOM_FUNCTIONS.get(db_type, "RANDOM()")

        # Helper function to get database-specific limit syntax
        def get_limit_syntax() -> Dict[str, str]:
            db_type = db_settings.database_type.value.lower()
            if db_type == "mssql":
                return {"select_prefix": f"TOP {sample_size}", "limit_suffix": ""}
            else:
                return {"select_prefix": "", "limit_suffix": f"LIMIT {sample_size}"}

        samples = {}
        limit_syntax = get_limit_syntax()
        random_func = get_random_function()

        # Build allowed set for whitelist enforcement
        allowed_set = (
            {t.lower() for t in profile.allowed_tables} if profile.allowed_tables else None
        )

        for table in tables:
            table_name = table["table_name"]
            noun_columns = table["noun_columns"]

            # Enforce table whitelist if configured
            # Strip schema prefix for comparison (e.g., "schema.table" → "table")
            bare_name = table_name.split(".")[-1].lower()
            if allowed_set and bare_name not in allowed_set:
                samples[table_name] = []
                logger.warning(f"Table '{table_name}' not in allowed tables, skipping")
                continue

            query = f"""
                SELECT {limit_syntax["select_prefix"]} {", ".join(noun_columns)}
                FROM {table_name}
                ORDER BY {random_func}
                {limit_syntax["limit_suffix"]}
            """

            try:
                # Execute query and get results as DataFrame
                result_df = db_manager.execute_query_df(query.strip())

                if not result_df.empty:
                    # Convert DataFrame to list of dictionaries
                    samples[table_name] = result_df.to_dict("records")
                else:
                    samples[table_name] = []

            except Exception as e:
                logger.error(f"Error sampling table {table_name}: {str(e)}")
                samples[table_name] = []

        # Format results as a readable string
        if not samples or all(not sample_list for sample_list in samples.values()):
            return "No sample data could be retrieved from any of the specified tables."

        result_str = "Random sample data retrieved:\n\n"

        for table_name, sample_list in samples.items():
            result_str += f"**{table_name}** ({len(sample_list)} rows):\n"

            if sample_list:
                # Create a DataFrame for better formatting
                sample_df = pd.DataFrame(sample_list)
                result_str += sample_df.to_string(index=False)
            else:
                result_str += "  No data available or error occurred"

            result_str += "\n\n"

        logger.info(f"Random subsamples retrieved successfully from {len(samples)} tables")
        return result_str

    except Exception as e:
        error_msg = f"Error retrieving random samples: {str(e)}"
        logger.error(error_msg)
        return error_msg
