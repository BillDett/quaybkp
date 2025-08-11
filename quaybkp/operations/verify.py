"""Verify operations for Quay namespace backups."""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

from ..database.connection import DatabaseConnection
from ..database.queries import QuayQueries
from ..storage.s3_backend import S3Backend
from ..models.inventory import BackupInventory, VerifySummary
from ..config.settings import Config


logger = logging.getLogger(__name__)


class VerifyOperation:
    """Handles verification of backup completeness."""
    
    def __init__(self, config: Config, bucket_name: str = "quaybackup"):
        self.config = config
        self.db_connection = DatabaseConnection(config)
        self.queries = QuayQueries(self.db_connection)
        self.s3_backend = S3Backend(config, bucket_name)
    
    def verify_backup(self, namespace_name: str, backup_number: Optional[int] = None) -> Dict[str, Any]:
        """Verify backup completeness against current Quay state."""
        logger.info(f"Starting verification for namespace: {namespace_name}")
        
        namespace = self.queries.get_namespace_by_name(namespace_name)
        if not namespace:
            raise ValueError(f"Namespace '{namespace_name}' not found")
        
        namespace_prefix = self.s3_backend.get_namespace_prefix(
            str(namespace['id']), namespace['name']
        )
        
        try:
            inventory_data = self.s3_backend.load_inventory(namespace_prefix, backup_number)
            inventory = BackupInventory.from_dict(inventory_data)
            
            used_backup_number = backup_number or self.s3_backend.get_latest_backup_number(namespace_prefix)
            
            if inventory.summary.status != "Success":
                logger.warning(f"Verifying backup with status: {inventory.summary.status}")
            
            logger.info(f"Loaded inventory from backup {used_backup_number}")
            
            current_blobs = self._get_current_namespace_blobs(namespace['id'])
            backup_blobs = self._get_backup_blobs(inventory)
            
            verification_result = self._compare_blob_sets(current_blobs, backup_blobs, namespace_prefix)
            
            verify_summary = VerifySummary(
                completed=datetime.now().strftime("%A, %b %d, %Y %H:%M"),
                inventory=str(used_backup_number),
                status="Complete" if verification_result['missing_blobs'] == 0 else "Incomplete",
                repositories_seen=str(len(current_blobs['repositories'])),
                manifests_seen=str(verification_result['total_manifests']),
                data={
                    "Blobs": str(verification_result['total_current_blobs']),
                    "BytesSeen": str(verification_result['total_bytes'])
                }
            )
            
            return {
                'namespace': namespace_name,
                'backup_number': used_backup_number,
                'inventory_status': inventory.summary.status,
                'verify_summary': verify_summary,
                'verification_details': verification_result
            }
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            raise
    
    def _get_current_namespace_blobs(self, namespace_id: int) -> Dict[str, Any]:
        """Get current blobs in Quay for the namespace."""
        all_blobs = self.queries.get_all_namespace_blobs(namespace_id)
        
        repositories = set()
        blob_digests = set()
        manifest_digests = set()
        
        for blob_info in all_blobs:
            repositories.add(blob_info['repository_name'])
            manifest_digests.add(blob_info['manifest_digest'])
            
            blob_digest = blob_info['blob_digest']
            if blob_digest.startswith('sha256:'):
                blob_digest = blob_digest[7:]
            blob_digests.add(blob_digest)
        
        return {
            'repositories': repositories,
            'manifests': manifest_digests,
            'blobs': blob_digests,
            'blob_details': all_blobs
        }
    
    def _get_backup_blobs(self, inventory: BackupInventory) -> Set[str]:
        """Extract all blob digests from backup inventory."""
        backup_blobs = set()
        
        for repo in inventory.repositories:
            for manifest_digest, blob_digests in repo.manifests.items():
                for blob_digest in blob_digests:
                    backup_blobs.add(blob_digest)
        
        return backup_blobs
    
    def _compare_blob_sets(self, current_blobs: Dict[str, Any], backup_blobs: Set[str],
                          namespace_prefix: str) -> Dict[str, Any]:
        """Compare current Quay blobs with backup inventory."""
        current_blob_set = current_blobs['blobs']
        
        missing_blobs = current_blob_set - backup_blobs
        extra_blobs = backup_blobs - current_blob_set
        
        total_bytes = 0
        for blob_info in current_blobs['blob_details']:
            if blob_info['image_size']:
                total_bytes += blob_info['image_size']
        
        missing_in_s3 = []
        for blob_digest in missing_blobs:
            if not self.s3_backend.blob_exists(namespace_prefix, blob_digest):
                missing_in_s3.append(blob_digest)
        
        return {
            'total_current_blobs': len(current_blob_set),
            'total_backup_blobs': len(backup_blobs),
            'total_manifests': len(current_blobs['manifests']),
            'total_bytes': total_bytes,
            'missing_blobs': len(missing_blobs),
            'extra_blobs': len(extra_blobs),
            'missing_in_s3': len(missing_in_s3),
            'missing_blob_list': list(missing_blobs)[:10],  # First 10 for debugging
            'extra_blob_list': list(extra_blobs)[:10],      # First 10 for debugging
            'missing_in_s3_list': missing_in_s3[:10]        # First 10 for debugging
        }