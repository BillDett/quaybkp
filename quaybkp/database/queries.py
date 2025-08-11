"""Database queries for Quay blob identification."""

from typing import List, Dict, Any, Optional
from .connection import DatabaseConnection


class QuayQueries:
    """Database queries for accessing Quay data."""
    
    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection
    
    def get_namespace_by_name(self, namespace_name: str) -> Optional[Dict[str, Any]]:
        """Get namespace/user by name."""
        query = """
        SELECT id, username as name, organization
        FROM "user" 
        WHERE username = %s
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (namespace_name,))
            return cursor.fetchone()
    
    def get_namespace_repositories(self, namespace_id: int) -> List[Dict[str, Any]]:
        """Get all repositories for a namespace."""
        query = """
        SELECT id, name, namespace_user, visibility, description
        FROM repository 
        WHERE namespace_user = %s
        AND state = 0  -- NORMAL state
        ORDER BY name
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (namespace_id,))
            return cursor.fetchall()
    
    def get_repository_manifests(self, repository_id: int) -> List[Dict[str, Any]]:
        """Get all manifests for a repository."""
        query = """
        SELECT id, repository_id, digest, media_type
        FROM manifest 
        WHERE repository_id = %s
        ORDER BY id
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (repository_id,))
            return cursor.fetchall()
    
    def get_manifest_blobs(self, manifest_id: int) -> List[Dict[str, Any]]:
        """Get all blobs for a manifest via ManifestBlob relationship."""
        query = """
        SELECT mb.blob_id, ist.uuid, ist.image_size, ist.checksum, ist.uploading, ist.cas_path
        FROM manifestblob mb
        JOIN imagestorage ist ON mb.blob_id = ist.id
        WHERE mb.manifest_id = %s
        AND ist.uploading = false
        ORDER BY mb.blob_index
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (manifest_id,))
            return cursor.fetchall()
    
    def get_blob_storage_info(self, blob_uuid: str) -> Optional[Dict[str, Any]]:
        """Get storage details for a blob."""
        query = """
        SELECT ist.uuid, ist.image_size, ist.checksum, ist.cas_path,
               isp.location_id, isp.storage_metadata
        FROM imagestorage ist
        LEFT JOIN imagestorageplacement isp ON ist.id = isp.storage_id
        WHERE ist.uuid = %s
        AND ist.uploading = false
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (blob_uuid,))
            return cursor.fetchone()
    
    def get_all_namespace_blobs(self, namespace_id: int) -> List[Dict[str, Any]]:
        """Get all unique blobs for a namespace with repository/manifest context."""
        query = """
        SELECT DISTINCT 
            r.id as repository_id,
            r.name as repository_name,
            m.id as manifest_id,
            m.digest as manifest_digest,
            ist.uuid as blob_uuid,
            ist.checksum as blob_digest,
            ist.image_size,
            ist.cas_path
        FROM "user" u
        JOIN repository r ON u.id = r.namespace_user
        JOIN manifest m ON r.id = m.repository_id
        JOIN manifestblob mb ON m.id = mb.manifest_id
        JOIN imagestorage ist ON mb.blob_id = ist.id
        WHERE u.id = %s
        AND r.state = 0  -- NORMAL state
        AND ist.uploading = false
        ORDER BY r.name, m.digest, ist.uuid
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (namespace_id,))
            return cursor.fetchall()
    
    def get_manifest_child_manifests(self, manifest_id: int) -> List[Dict[str, Any]]:
        """Get child manifests for a manifest list."""
        query = """
        SELECT cm.id, cm.digest, cm.media_type
        FROM manifest cm
        JOIN manifestchild mc ON cm.id = mc.child_manifest_id
        WHERE mc.manifest_id = %s
        ORDER BY cm.id
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (manifest_id,))
            return cursor.fetchall()
    
    def get_repository_tags(self, repository_id: int) -> List[Dict[str, Any]]:
        """Get all tags for a repository."""
        query = """
        SELECT name, manifest_id, lifetime_start, lifetime_end
        FROM tag
        WHERE repository_id = %s
        AND lifetime_end IS NULL  -- Active tags only
        ORDER BY name
        """
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, (repository_id,))
            return cursor.fetchall()