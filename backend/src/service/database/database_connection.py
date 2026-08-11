import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class DatabaseConnection(ABC):
    @abstractmethod
    def connect(self) -> Any:
        """Establish a connection to the database."""
        pass

    @abstractmethod
    def execute_query(self, query: str) -> Tuple[List[str], List[Any]]:
        """Execute a SQL query and return results as (columns, data) tuple."""
        logger.info("⎄ Executing query...")
        pass

    @abstractmethod
    def execute_query_df(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return results as a pandas DataFrame."""
        logger.info("⎄ Executing query as DataFrame...")
        pass

    def close(self) -> None:
        """Close the database connection. Override in subclasses if needed."""
        pass

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()
        return False
