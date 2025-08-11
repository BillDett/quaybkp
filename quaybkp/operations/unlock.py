"""Unlock operations for removing backup locks."""

import logging
from typing import Dict, Any

from ..database.connection import DatabaseConnection
from ..database.queries import QuayQueries
from ..storage.s3_backend import S3Backend
from ..config.settings import Config


logger = logging.getLogger(__name__)


class UnlockOperation:
    """Handles unlock operations for backup locks."""
    
    def __init__(self, config: Config, bucket_name: str = "quaybackup"):
        self.config = config
        self.db_connection = DatabaseConnection(config)
        self.queries = QuayQueries(self.db_connection)
        self.s3_backend = S3Backend(config, bucket_name)
    
    def unlock_namespace(self, namespace_name: str) -> Dict[str, Any]:
        """Remove backup lock for a namespace."""
        logger.info(f"Unlocking namespace: {namespace_name}")
        
        namespace = self.queries.get_namespace_by_name(namespace_name)
        if not namespace:
            raise ValueError(f"Namespace '{namespace_name}' not found")
        
        namespace_prefix = self.s3_backend.get_namespace_prefix(
            str(namespace['id']), namespace['name']
        )
        
        lock_existed = self.s3_backend.check_lock_exists(namespace_prefix)
        
        if lock_existed:
            self.s3_backend.remove_lock(namespace_prefix)
            logger.info(f"Removed lock for namespace {namespace_name}")
            message = f"Successfully removed backup lock for namespace '{namespace_name}'"
        else:
            logger.info(f"No lock found for namespace {namespace_name}")
            message = f"No backup lock found for namespace '{namespace_name}'"
        
        return {
            'namespace': namespace_name,
            'lock_existed': lock_existed,
            'message': message
        }