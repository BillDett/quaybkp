"""Configuration management for quaybkp."""

import os
import yaml
from typing import Dict, Any, Optional


class Config:
    """Configuration manager for quaybkp."""
    
    def __init__(self):
        self.quay_config_path = os.environ.get('QUAY_CONFIG')
        self.s3_access_key_id = os.environ.get('S3_ACCESS_KEY_ID')
        self.s3_secret_access_key = os.environ.get('S3_SECRET_ACCESS_KEY')
        self.s3_endpoint_url = os.environ.get('S3_ENDPOINT_URL')
        
        self._quay_config = None
        self._validate_environment()
    
    def _validate_environment(self):
        """Validate required environment variables."""
        required_vars = [
            'QUAY_CONFIG',
            'S3_ACCESS_KEY_ID', 
            'S3_SECRET_ACCESS_KEY',
            'S3_ENDPOINT_URL'
        ]
        
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    @property
    def quay_config(self) -> Dict[str, Any]:
        """Load and cache Quay configuration."""
        if self._quay_config is None:
            if not os.path.exists(self.quay_config_path):
                raise FileNotFoundError(f"Quay config file not found: {self.quay_config_path}")
            
            with open(self.quay_config_path, 'r') as f:
                self._quay_config = yaml.safe_load(f)
        
        return self._quay_config
    
    @property
    def database_uri(self) -> str:
        """Get database URI from Quay config."""
        db_config = self.quay_config.get('DB_URI')
        if not db_config:
            raise ValueError("DB_URI not found in Quay configuration")
        return db_config
    
    @property
    def storage_config(self) -> Dict[str, Any]:
        """Get storage configuration from Quay config."""
        storage_config = self.quay_config.get('DISTRIBUTED_STORAGE_CONFIG', {})
        if not storage_config:
            raise ValueError("DISTRIBUTED_STORAGE_CONFIG not found in Quay configuration")
        return storage_config
    
    def get_storage_path(self, storage_uuid: str) -> Optional[str]:
        """Get storage path for a given storage UUID."""
        for location_id, config in self.storage_config.items():
            if config[0] == 'LocalStorage':
                return config[1].get('storage_path')
        return None