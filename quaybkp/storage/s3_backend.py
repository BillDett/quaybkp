"""S3 backend for backup storage operations."""

import boto3
import json
import os
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError, NoCredentialsError
from ..config.settings import Config


class S3Backend:
    """S3 storage backend for backups."""
    
    def __init__(self, config: Config, bucket_name: str = "quaybackup"):
        self.config = config
        self.bucket_name = bucket_name
        self._client = None
        self._ensure_bucket_exists()
    
    @property
    def client(self):
        """Lazy initialization of S3 client."""
        if self._client is None:
            self._client = boto3.client(
                's3',
                aws_access_key_id=self.config.s3_access_key_id,
                aws_secret_access_key=self.config.s3_secret_access_key,
                endpoint_url=self.config.s3_endpoint_url
            )
        return self._client
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                try:
                    self.client.create_bucket(Bucket=self.bucket_name)
                except ClientError as create_error:
                    raise RuntimeError(f"Failed to create bucket {self.bucket_name}: {create_error}")
            else:
                raise RuntimeError(f"Error accessing bucket {self.bucket_name}: {e}")
    
    def get_namespace_prefix(self, namespace_id: str, namespace_name: str) -> str:
        """Get S3 prefix for namespace."""
        return f"{namespace_id}-{namespace_name}"
    
    def check_lock_exists(self, namespace_prefix: str) -> bool:
        """Check if backup lock file exists."""
        lock_key = f"{namespace_prefix}/backup/lock"
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=lock_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    def create_lock(self, namespace_prefix: str):
        """Create backup lock file."""
        lock_key = f"{namespace_prefix}/backup/lock"
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=lock_key,
            Body=b"",
            ContentType="text/plain"
        )
    
    def remove_lock(self, namespace_prefix: str):
        """Remove backup lock file."""
        lock_key = f"{namespace_prefix}/backup/lock"
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=lock_key)
        except ClientError as e:
            if e.response['Error']['Code'] != '404':
                raise
    
    def get_latest_backup_number(self, namespace_prefix: str) -> int:
        """Get the highest backup number for a namespace."""
        prefix = f"{namespace_prefix}/backup/"
        
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            backup_numbers = []
            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.endswith('.json'):
                    filename = key.split('/')[-1]
                    try:
                        backup_num = int(filename.replace('.json', ''))
                        backup_numbers.append(backup_num)
                    except ValueError:
                        continue
            
            return max(backup_numbers) if backup_numbers else 0
        except ClientError:
            return 0
    
    def save_inventory(self, namespace_prefix: str, backup_number: int, inventory: Dict[str, Any]):
        """Save backup inventory file."""
        inventory_key = f"{namespace_prefix}/backup/{backup_number}.json"
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=inventory_key,
            Body=json.dumps(inventory, indent=2),
            ContentType="application/json"
        )
    
    def load_inventory(self, namespace_prefix: str, backup_number: Optional[int] = None) -> Dict[str, Any]:
        """Load backup inventory file."""
        if backup_number is None:
            backup_number = self.get_latest_backup_number(namespace_prefix)
            if backup_number == 0:
                raise FileNotFoundError("No backup inventory files found")
        
        inventory_key = f"{namespace_prefix}/backup/{backup_number}.json"
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=inventory_key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"Backup inventory {backup_number} not found")
            raise
    
    def blob_exists(self, namespace_prefix: str, blob_digest: str) -> bool:
        """Check if blob exists in backup storage."""
        blob_key = f"{namespace_prefix}/blob/{blob_digest[:2]}/{blob_digest}"
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=blob_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    def upload_blob(self, namespace_prefix: str, blob_digest: str, blob_data: bytes):
        """Upload blob to backup storage."""
        blob_key = f"{namespace_prefix}/blob/{blob_digest[:2]}/{blob_digest}"
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=blob_key,
            Body=blob_data,
            ContentType="application/octet-stream"
        )
    
    def download_blob(self, namespace_prefix: str, blob_digest: str) -> bytes:
        """Download blob from backup storage."""
        blob_key = f"{namespace_prefix}/blob/{blob_digest[:2]}/{blob_digest}"
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=blob_key)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"Blob {blob_digest} not found in backup")
            raise
    
    def list_backup_inventories(self, namespace_prefix: str) -> List[int]:
        """List all available backup numbers for a namespace."""
        prefix = f"{namespace_prefix}/backup/"
        
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            backup_numbers = []
            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.endswith('.json'):
                    filename = key.split('/')[-1]
                    try:
                        backup_num = int(filename.replace('.json', ''))
                        backup_numbers.append(backup_num)
                    except ValueError:
                        continue
            
            return sorted(backup_numbers)
        except ClientError:
            return []