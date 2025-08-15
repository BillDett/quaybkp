"""Backup operations for Quay namespaces."""

import logging
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict

from ..database.connection import DatabaseConnection
from ..database.queries import QuayQueries
from ..storage.s3_backend import S3Backend
from ..storage.quay_storage import QuayStorage
from ..workers.blob_worker import BlobWorkerPool
from ..models.inventory import BackupInventory, RepositoryBackup, BackupSummary
from ..config.settings import Config


logger = logging.getLogger(__name__)


class BackupOperation:
    """Handles backup operations for Quay namespaces."""
    
    def __init__(self, config: Config, bucket_name: str):
        self.config = config
        self.db_connection = DatabaseConnection(config)
        self.queries = QuayQueries(self.db_connection)
        self.s3_backend = S3Backend(config, bucket_name)
        self.quay_storage = QuayStorage(config)
    
    def backup_namespace(self, namespace_name: str, force_blobs: bool = False, 
                        num_workers: int = 5) -> Dict[str, Any]:
        """Backup all blobs for a namespace."""
        logger.info(f"Starting backup for namespace: {namespace_name}")
        
        namespace = self.queries.get_namespace_by_name(namespace_name)
        if not namespace:
            raise ValueError(f"Namespace '{namespace_name}' not found")
        
        namespace_prefix = self.s3_backend.get_namespace_prefix(
            str(namespace['id']), namespace['name']
        )
        
        if self.s3_backend.check_lock_exists(namespace_prefix):
            raise RuntimeError(f"Backup in progress for namespace {namespace_name}. "
                             f"Use 'unlock' command if backup is stuck.")
        
        try:
            self.s3_backend.create_lock(namespace_prefix)
            logger.info("Created backup lock")
            
            backup_number = self.s3_backend.get_latest_backup_number(namespace_prefix) + 1
            logger.info(f"Using backup number: {backup_number}")
            
            repositories = self._get_namespace_repositories(namespace['id'])
            logger.info(f"Found {len(repositories)} repositories")
            
            repository_backups = []
            all_blobs = []
            
            for repo in repositories:
                repo_backup = self._backup_repository(repo)
                repository_backups.append(repo_backup)
                
                for manifest_digest, blob_digests in repo_backup.manifests.items():
                    for blob_digest in blob_digests:
                        all_blobs.append({
                            'repository_id': repo['id'],
                            'repository_name': repo['name'],
                            'manifest_digest': manifest_digest,
                            'blob_digest': blob_digest,
                            'cas_path': f"sha256/{blob_digest[:2]}/{blob_digest}"
                        })
            
            unique_blobs = self._deduplicate_blobs(all_blobs)
            logger.info(f"Processing {len(unique_blobs)} unique blobs")
            
            worker_pool = BlobWorkerPool(
                self.s3_backend, self.quay_storage, namespace_prefix, num_workers
            )
            
            backup_results = worker_pool.backup_blobs(unique_blobs, force_blobs)
            
            inventory = BackupInventory(
                user=namespace['name'],
                id=str(namespace['id']),
                repositories=repository_backups,
                summary=BackupSummary(
                    completed=datetime.now().strftime("%A, %b %d, %Y %H:%M"),
                    status="Success" if backup_results['failed_blobs'] == 0 else "Failed",
                    repositories_created=str(len(repositories)),
                    manifests_created=str(sum(len(r.manifests) for r in repository_backups)),
                    data={
                        "Blobs": str(backup_results['processed_blobs']),
                        "BytesWritten": str(backup_results['total_bytes'])
                    }
                )
            )
            
            self.s3_backend.save_inventory(namespace_prefix, backup_number, inventory.to_dict())
            logger.info(f"Saved backup inventory {backup_number}")
            
            return {
                'backup_number': backup_number,
                'namespace': namespace_name,
                'summary': inventory.summary,
                'backup_results': backup_results
            }
            
        finally:
            self.s3_backend.remove_lock(namespace_prefix)
            logger.info("Removed backup lock")
    
    def _get_namespace_repositories(self, namespace_id: int) -> List[Dict[str, Any]]:
        """Get all repositories for a namespace."""
        return self.queries.get_namespace_repositories(namespace_id)
    
    def _backup_repository(self, repository: Dict[str, Any]) -> RepositoryBackup:
        """Backup a single repository."""
        logger.info(f"Processing repository: {repository['name']}")
        
        manifests = self.queries.get_repository_manifests(repository['id'])
        manifest_blobs = {}
        
        for manifest in manifests:
            logger.info(f"Getting blobs for manifest {manifest['id']}")
            blobs = self.queries.get_manifest_blobs(manifest['id'])
            blob_digests = []
            
            for blob in blobs:
                blob_digest = blob['content_checksum']
                if blob_digest.startswith('sha256:'):
                    blob_digest = blob_digest[7:]
                blob_digests.append(blob_digest)
            
            child_manifests = self.queries.get_manifest_child_manifests(manifest['id'])
            for child in child_manifests:
                child_blobs = self.queries.get_manifest_blobs(child['id'])
                for blob in child_blobs:
                    blob_digest = blob['content_checksum']
                    if blob_digest.startswith('sha256:'):
                        blob_digest = blob_digest[7:]
                    blob_digests.append(blob_digest)
            
            manifest_digest = manifest['digest']
            if manifest_digest.startswith('sha256:'):
                manifest_digest = manifest_digest[7:]
            
            manifest_blobs[manifest_digest] = blob_digests
        
        return RepositoryBackup(
            name=repository['name'],
            id=str(repository['id']),
            manifests=manifest_blobs
        )
    
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