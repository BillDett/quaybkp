"""Quay storage interface for reading blobs."""

import os
import hashlib
import boto3
from typing import Optional, Dict, Any, Tuple
from botocore.exceptions import ClientError, NoCredentialsError
from ..config.settings import Config


class QuayStorage:
    """Interface to Quay's distributed storage system."""
    
    def __init__(self, config: Config):
        self.config = config
        self.storage_backends = self._initialize_storage_backends()
    
    def _initialize_storage_backends(self) -> Dict[str, Dict[str, Any]]:
        """Initialize storage backends from Quay configuration."""
        backends = {}
        storage_config = self.config.storage_config
        
        for location_id, storage_config_tuple in storage_config.items():
            driver_name = storage_config_tuple[0]
            driver_config = storage_config_tuple[1] if len(storage_config_tuple) > 1 else {}
            
            backend_info = {
                'driver': driver_name,
                'config': driver_config,
                'client': None
            }
            
            if driver_name == 'LocalStorage':
                backend_info['storage_path'] = driver_config.get('storage_path', '/datastorage/registry')
            elif driver_name in ['S3Storage', 'CloudFrontedS3Storage']:
                backend_info['client'] = self._create_s3_client(driver_config)
                backend_info['bucket'] = driver_config.get('s3_bucket')
                backend_info['storage_path'] = driver_config.get('storage_path', '/datastorage/registry')
            elif driver_name == 'GoogleCloudStorage':
                backend_info['bucket'] = driver_config.get('bucket_name')
                backend_info['storage_path'] = driver_config.get('storage_path', '/datastorage/registry')
            elif driver_name == 'AzureStorage':
                backend_info['container'] = driver_config.get('azure_container')
                backend_info['storage_path'] = driver_config.get('storage_path', '/datastorage/registry')
            
            backends[location_id] = backend_info
        
        return backends
    
    def _create_s3_client(self, driver_config: Dict[str, Any]):
        """Create S3 client from driver configuration."""
        s3_config = {
            'aws_access_key_id': driver_config.get('s3_access_key'),
            'aws_secret_access_key': driver_config.get('s3_secret_key'),
            'region_name': driver_config.get('s3_region', 'us-east-1')
        }
        
        if driver_config.get('host'):
            s3_config['endpoint_url'] = f"https://{driver_config['host']}"
        
        return boto3.client('s3', **s3_config)
    
    def _get_storage_backend(self, storage_location: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """Get storage backend configuration."""
        if not storage_location and self.storage_backends:
            storage_location = list(self.storage_backends.keys())[0]
        
        if storage_location not in self.storage_backends:
            raise ValueError(f"Storage location '{storage_location}' not configured")
        
        return storage_location, self.storage_backends[storage_location]
    
    def _construct_blob_path(self, cas_path: str, storage_path: str) -> str:
        """Construct full blob path following Quay's storage conventions."""
        if cas_path.startswith('/'):
            return os.path.join(storage_path, cas_path[1:])
        return os.path.join(storage_path, cas_path)
    
    def _construct_object_key(self, cas_path: str, storage_path: str) -> str:
        """Construct object key for object storage following Quay's conventions."""
        if storage_path and not storage_path.endswith('/'):
            storage_path += '/'
        
        if cas_path.startswith('/'):
            cas_path = cas_path[1:]
        
        return f"{storage_path}{cas_path}" if storage_path else cas_path
    
    def read_blob(self, cas_path: str, storage_location: Optional[str] = None) -> Optional[bytes]:
        """Read blob data from Quay storage."""
        try:
            location_id, backend = self._get_storage_backend(storage_location)
            driver = backend['driver']
            
            if driver == 'LocalStorage':
                return self._read_blob_local(cas_path, backend)
            elif driver in ['S3Storage', 'CloudFrontedS3Storage']:
                return self._read_blob_s3(cas_path, backend)
            elif driver == 'GoogleCloudStorage':
                return self._read_blob_gcs(cas_path, backend)
            elif driver == 'AzureStorage':
                return self._read_blob_azure(cas_path, backend)
            else:
                raise ValueError(f"Unsupported storage driver: {driver}")
                
        except Exception as e:
            return None
    
    def _read_blob_local(self, cas_path: str, backend: Dict[str, Any]) -> Optional[bytes]:
        """Read blob from local storage."""
        blob_path = self._construct_blob_path(cas_path, backend['storage_path'])
        
        if not os.path.exists(blob_path):
            return None
        
        try:
            with open(blob_path, 'rb') as f:
                return f.read()
        except (IOError, OSError):
            return None
    
    def _read_blob_s3(self, cas_path: str, backend: Dict[str, Any]) -> Optional[bytes]:
        """Read blob from S3 storage."""
        try:
            object_key = self._construct_object_key(cas_path, backend['storage_path'])
            response = backend['client'].get_object(
                Bucket=backend['bucket'],
                Key=object_key
            )
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise
    
    def _read_blob_gcs(self, cas_path: str, backend: Dict[str, Any]) -> Optional[bytes]:
        """Read blob from Google Cloud Storage."""
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(backend['bucket'])
            object_key = self._construct_object_key(cas_path, backend['storage_path'])
            blob = bucket.blob(object_key)
            return blob.download_as_bytes()
        except Exception:
            return None
    
    def _read_blob_azure(self, cas_path: str, backend: Dict[str, Any]) -> Optional[bytes]:
        """Read blob from Azure Storage."""
        try:
            from azure.storage.blob import BlobServiceClient
            client = BlobServiceClient.from_connection_string(backend['config'].get('azure_connection_string'))
            object_key = self._construct_object_key(cas_path, backend['storage_path'])
            blob_client = client.get_blob_client(
                container=backend['container'],
                blob=object_key
            )
            return blob_client.download_blob().readall()
        except Exception:
            return None
    
    def write_blob(self, cas_path: str, blob_data: bytes, storage_location: Optional[str] = None) -> bool:
        """Write blob data to Quay storage."""
        try:
            location_id, backend = self._get_storage_backend(storage_location)
            driver = backend['driver']
            
            if driver == 'LocalStorage':
                return self._write_blob_local(cas_path, blob_data, backend)
            elif driver in ['S3Storage', 'CloudFrontedS3Storage']:
                return self._write_blob_s3(cas_path, blob_data, backend)
            elif driver == 'GoogleCloudStorage':
                return self._write_blob_gcs(cas_path, blob_data, backend)
            elif driver == 'AzureStorage':
                return self._write_blob_azure(cas_path, blob_data, backend)
            else:
                raise ValueError(f"Unsupported storage driver: {driver}")
                
        except Exception:
            return False
    
    def _write_blob_local(self, cas_path: str, blob_data: bytes, backend: Dict[str, Any]) -> bool:
        """Write blob to local storage."""
        blob_path = self._construct_blob_path(cas_path, backend['storage_path'])
        
        try:
            os.makedirs(os.path.dirname(blob_path), exist_ok=True)
            with open(blob_path, 'wb') as f:
                f.write(blob_data)
            return True
        except (IOError, OSError):
            return False
    
    def _write_blob_s3(self, cas_path: str, blob_data: bytes, backend: Dict[str, Any]) -> bool:
        """Write blob to S3 storage."""
        try:
            object_key = self._construct_object_key(cas_path, backend['storage_path'])
            backend['client'].put_object(
                Bucket=backend['bucket'],
                Key=object_key,
                Body=blob_data,
                ContentType='application/octet-stream'
            )
            return True
        except ClientError:
            return False
    
    def _write_blob_gcs(self, cas_path: str, blob_data: bytes, backend: Dict[str, Any]) -> bool:
        """Write blob to Google Cloud Storage."""
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(backend['bucket'])
            object_key = self._construct_object_key(cas_path, backend['storage_path'])
            blob = bucket.blob(object_key)
            blob.upload_from_string(blob_data, content_type='application/octet-stream')
            return True
        except Exception:
            return False
    
    def _write_blob_azure(self, cas_path: str, blob_data: bytes, backend: Dict[str, Any]) -> bool:
        """Write blob to Azure Storage."""
        try:
            from azure.storage.blob import BlobServiceClient
            client = BlobServiceClient.from_connection_string(backend['config'].get('azure_connection_string'))
            object_key = self._construct_object_key(cas_path, backend['storage_path'])
            blob_client = client.get_blob_client(
                container=backend['container'],
                blob=object_key
            )
            blob_client.upload_blob(blob_data, content_type='application/octet-stream', overwrite=True)
            return True
        except Exception:
            return False
    
    def blob_exists(self, cas_path: str, storage_location: Optional[str] = None) -> bool:
        """Check if blob exists in Quay storage."""
        try:
            location_id, backend = self._get_storage_backend(storage_location)
            driver = backend['driver']
            
            if driver == 'LocalStorage':
                blob_path = self._construct_blob_path(cas_path, backend['storage_path'])
                return os.path.exists(blob_path)
            elif driver in ['S3Storage', 'CloudFrontedS3Storage']:
                object_key = self._construct_object_key(cas_path, backend['storage_path'])
                try:
                    backend['client'].head_object(Bucket=backend['bucket'], Key=object_key)
                    return True
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        return False
                    raise
            elif driver == 'GoogleCloudStorage':
                from google.cloud import storage
                client = storage.Client()
                bucket = client.bucket(backend['bucket'])
                object_key = self._construct_object_key(cas_path, backend['storage_path'])
                blob = bucket.blob(object_key)
                return blob.exists()
            elif driver == 'AzureStorage':
                from azure.storage.blob import BlobServiceClient
                client = BlobServiceClient.from_connection_string(backend['config'].get('azure_connection_string'))
                object_key = self._construct_object_key(cas_path, backend['storage_path'])
                blob_client = client.get_blob_client(
                    container=backend['container'],
                    blob=object_key
                )
                return blob_client.exists()
            else:
                return False
                
        except Exception:
            return False
    
    def verify_blob_checksum(self, cas_path: str, expected_checksum: str, 
                           storage_location: Optional[str] = None) -> bool:
        """Verify blob checksum matches expected value."""
        blob_data = self.read_blob(cas_path, storage_location)
        if blob_data is None:
            return False
        
        if expected_checksum.startswith('sha256:'):
            expected_checksum = expected_checksum[7:]
        
        actual_checksum = hashlib.sha256(blob_data).hexdigest()
        return actual_checksum == expected_checksum