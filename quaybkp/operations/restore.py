"""Restore operations for Quay namespaces."""

import logging
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

from ..database.connection import DatabaseConnection
from ..database.queries import QuayQueries
from ..storage.s3_backend import S3Backend
from ..storage.quay_storage import QuayStorage
from ..workers.blob_worker import BlobWorkerPool
from ..models.inventory import BackupInventory, RestoreSummary
from ..config.settings import Config


logger = logging.getLogger(__name__)


class RestoreOperation:
    """Handles restore operations for Quay namespaces."""
    
    def __init__(self, config: Config, bucket_name: str = "quaybackup"):
        self.config = config
        self.db_connection = DatabaseConnection(config)
        self.queries = QuayQueries(self.db_connection)
        self.s3_backend = S3Backend(config, bucket_name)
        self.quay_storage = QuayStorage(config)
    
    def restore_namespace(self, namespace_name: str, backup_number: Optional[int] = None,
                         repository_filter: Optional[str] = None, dry_run: bool = False,
                         force_blobs: bool = False, num_workers: int = 5) -> Dict[str, Any]:
        """Restore namespace from backup."""
        logger.info(f"Starting restore for namespace: {namespace_name}")
        
        namespace = self.queries.get_namespace_by_name(namespace_name)
        if not namespace:
            raise ValueError(f"Namespace '{namespace_name}' not found")
        
        namespace_prefix = self.s3_backend.get_namespace_prefix(
            str(namespace['id']), namespace['name']
        )
        
        if self.s3_backend.check_lock_exists(namespace_prefix):
            raise RuntimeError(f"Backup in progress for namespace {namespace_name}. "
                             f"Cannot restore while backup is running.")
        
        try:
            inventory_data = self.s3_backend.load_inventory(namespace_prefix, backup_number)
            inventory = BackupInventory.from_dict(inventory_data)
            
            if inventory.summary.status != "Success":
                logger.warning(f"Restoring from backup with status: {inventory.summary.status}")
                if inventory.summary.status == "Failed":
                    raise RuntimeError("Cannot restore from a failed backup")
            
            logger.info(f"Loaded inventory from backup {backup_number or 'latest'}")
            
            blobs_to_restore = self._prepare_restore_blobs(inventory, repository_filter)
            logger.info(f"Found {len(blobs_to_restore)} blobs to restore")
            
            if dry_run:
                return self._dry_run_report(inventory, blobs_to_restore, repository_filter)
            
            worker_pool = BlobWorkerPool(
                self.s3_backend, self.quay_storage, namespace_prefix, num_workers
            )
            
            restore_results = worker_pool.restore_blobs(blobs_to_restore, force_blobs)
            
            restore_summary = RestoreSummary(
                completed=datetime.now().strftime("%A, %b %d, %Y %H:%M"),
                status="Success" if restore_results['failed_blobs'] == 0 else "Failed",
                repositories_created=str(self._count_repositories(inventory, repository_filter)),
                manifests_created=str(self._count_manifests(inventory, repository_filter)),
                data={
                    "Blobs": str(restore_results['processed_blobs']),
                    "BytesWritten": str(restore_results['total_bytes'])
                }
            )
            
            return {
                'namespace': namespace_name,
                'backup_number': backup_number,
                'repository_filter': repository_filter,
                'restore_summary': restore_summary,
                'restore_results': restore_results
            }
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise
    
    def _prepare_restore_blobs(self, inventory: BackupInventory, 
                              repository_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Prepare list of blobs to restore."""
        blobs_to_restore = []
        
        for repo in inventory.repositories:
            if repository_filter and repo.name != repository_filter:
                continue
            
            for manifest_digest, blob_digests in repo.manifests.items():
                for blob_digest in blob_digests:
                    blobs_to_restore.append({
                        'repository_name': repo.name,
                        'manifest_digest': manifest_digest,
                        'blob_digest': blob_digest,
                        'cas_path': f"sha256/{blob_digest[:2]}/{blob_digest[2:4]}/{blob_digest}"
                    })
        
        return self._deduplicate_blobs(blobs_to_restore)
    
    def _deduplicate_blobs(self, all_blobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate blobs from the list."""
        seen_blobs = set()
        unique_blobs = []
        
        for blob in all_blobs:
            blob_digest = blob['blob_digest']
            if blob_digest not in seen_blobs:
                seen_blobs.add(blob_digest)
                unique_blobs.append(blob)
        
        return unique_blobs
    
    def _count_repositories(self, inventory: BackupInventory, repository_filter: Optional[str] = None) -> int:
        """Count repositories that would be restored."""
        if repository_filter:
            return 1 if any(repo.name == repository_filter for repo in inventory.repositories) else 0
        return len(inventory.repositories)
    
    def _count_manifests(self, inventory: BackupInventory, repository_filter: Optional[str] = None) -> int:
        """Count manifests that would be restored."""
        count = 0
        for repo in inventory.repositories:
            if repository_filter and repo.name != repository_filter:
                continue
            count += len(repo.manifests)
        return count
    
    def _dry_run_report(self, inventory: BackupInventory, blobs_to_restore: List[Dict[str, Any]],
                       repository_filter: Optional[str] = None) -> Dict[str, Any]:
        """Generate dry run report."""
        total_size = 0
        existing_blobs = 0
        missing_blobs = 0
        
        for blob in blobs_to_restore:
            if self.quay_storage.blob_exists(blob['cas_path']):
                existing_blobs += 1
            else:
                missing_blobs += 1
        
        return {
            'namespace': inventory.user,
            'backup_number': 'latest',
            'repository_filter': repository_filter,
            'dry_run': True,
            'summary': {
                'repositories_to_restore': self._count_repositories(inventory, repository_filter),
                'manifests_to_restore': self._count_manifests(inventory, repository_filter),
                'total_blobs': len(blobs_to_restore),
                'existing_blobs': existing_blobs,
                'blobs_to_download': missing_blobs,
            },
            'actions': [
                f"Would restore {missing_blobs} blobs from backup",
                f"Would skip {existing_blobs} existing blobs",
                f"Would process {len(blobs_to_restore)} total blobs"
            ]
        }