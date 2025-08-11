"""Concurrent blob processing workers."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Callable, Optional
from tqdm import tqdm
from ..storage.s3_backend import S3Backend
from ..storage.quay_storage import QuayStorage


class BlobWorker:
    """Worker for processing individual blobs."""
    
    def __init__(self, worker_id: int, s3_backend: S3Backend, quay_storage: QuayStorage, 
                 namespace_prefix: str):
        self.worker_id = worker_id
        self.s3_backend = s3_backend
        self.quay_storage = quay_storage
        self.namespace_prefix = namespace_prefix
        self.processed_count = 0
        self.error_count = 0
        self.bytes_processed = 0
    
    def backup_blob(self, blob_info: Dict[str, Any], force_blobs: bool = False) -> Dict[str, Any]:
        """Backup a single blob to S3."""
        blob_digest = blob_info['blob_digest']
        cas_path = blob_info['cas_path']
        
        result = {
            'worker_id': self.worker_id,
            'blob_digest': blob_digest,
            'success': False,
            'skipped': False,
            'error': None,
            'bytes_processed': 0
        }
        
        try:
            if not force_blobs and self.s3_backend.blob_exists(self.namespace_prefix, blob_digest):
                result['skipped'] = True
                result['success'] = True
                return result
            
            blob_data = self.quay_storage.read_blob(cas_path)
            if blob_data is None:
                result['error'] = f"Failed to read blob from Quay storage: {cas_path}"
                return result
            
            self.s3_backend.upload_blob(self.namespace_prefix, blob_digest, blob_data)
            
            result['success'] = True
            result['bytes_processed'] = len(blob_data)
            self.processed_count += 1
            self.bytes_processed += len(blob_data)
            
        except Exception as e:
            result['error'] = str(e)
            self.error_count += 1
        
        return result
    
    def restore_blob(self, blob_digest: str, cas_path: str, force_blobs: bool = False) -> Dict[str, Any]:
        """Restore a single blob from S3."""
        result = {
            'worker_id': self.worker_id,
            'blob_digest': blob_digest,
            'success': False,
            'skipped': False,
            'error': None,
            'bytes_processed': 0
        }
        
        try:
            if not force_blobs and self.quay_storage.blob_exists(cas_path):
                result['skipped'] = True
                result['success'] = True
                return result
            
            blob_data = self.s3_backend.download_blob(self.namespace_prefix, blob_digest)
            
            if self.quay_storage.write_blob(cas_path, blob_data):
                result['success'] = True
                result['bytes_processed'] = len(blob_data)
                self.processed_count += 1
                self.bytes_processed += len(blob_data)
            else:
                result['error'] = f"Failed to write blob to Quay storage: {cas_path}"
                
        except Exception as e:
            result['error'] = str(e)
            self.error_count += 1
        
        return result


class BlobWorkerPool:
    """Pool of workers for concurrent blob processing."""
    
    def __init__(self, s3_backend: S3Backend, quay_storage: QuayStorage, 
                 namespace_prefix: str, num_workers: int = 5):
        self.s3_backend = s3_backend
        self.quay_storage = quay_storage
        self.namespace_prefix = namespace_prefix
        self.num_workers = num_workers
        self.workers = []
        
    def backup_blobs(self, blob_list: List[Dict[str, Any]], force_blobs: bool = False,
                    progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Backup multiple blobs using worker pool."""
        results = {
            'total_blobs': len(blob_list),
            'processed_blobs': 0,
            'skipped_blobs': 0,
            'failed_blobs': 0,
            'total_bytes': 0,
            'errors': []
        }
        
        if not blob_list:
            return results
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            workers = [
                BlobWorker(i, self.s3_backend, self.quay_storage, self.namespace_prefix)
                for i in range(self.num_workers)
            ]
            
            with tqdm(total=len(blob_list), desc="Backing up blobs", unit="blob") as pbar:
                future_to_blob = {
                    executor.submit(workers[i % self.num_workers].backup_blob, blob, force_blobs): blob
                    for i, blob in enumerate(blob_list)
                }
                
                for future in as_completed(future_to_blob):
                    result = future.result()
                    blob_info = future_to_blob[future]
                    
                    if result['success']:
                        if result['skipped']:
                            results['skipped_blobs'] += 1
                        else:
                            results['processed_blobs'] += 1
                            results['total_bytes'] += result['bytes_processed']
                    else:
                        results['failed_blobs'] += 1
                        results['errors'].append({
                            'blob_digest': result['blob_digest'],
                            'error': result['error']
                        })
                    
                    pbar.update(1)
                    if progress_callback:
                        progress_callback(result)
        
        return results
    
    def restore_blobs(self, blob_list: List[Dict[str, Any]], force_blobs: bool = False,
                     progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Restore multiple blobs using worker pool."""
        results = {
            'total_blobs': len(blob_list),
            'processed_blobs': 0,
            'skipped_blobs': 0,
            'failed_blobs': 0,
            'total_bytes': 0,
            'errors': []
        }
        
        if not blob_list:
            return results
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            workers = [
                BlobWorker(i, self.s3_backend, self.quay_storage, self.namespace_prefix)
                for i in range(self.num_workers)
            ]
            
            with tqdm(total=len(blob_list), desc="Restoring blobs", unit="blob") as pbar:
                future_to_blob = {
                    executor.submit(
                        workers[i % self.num_workers].restore_blob,
                        blob['blob_digest'],
                        blob['cas_path'],
                        force_blobs
                    ): blob
                    for i, blob in enumerate(blob_list)
                }
                
                for future in as_completed(future_to_blob):
                    result = future.result()
                    blob_info = future_to_blob[future]
                    
                    if result['success']:
                        if result['skipped']:
                            results['skipped_blobs'] += 1
                        else:
                            results['processed_blobs'] += 1
                            results['total_bytes'] += result['bytes_processed']
                    else:
                        results['failed_blobs'] += 1
                        results['errors'].append({
                            'blob_digest': result['blob_digest'],
                            'error': result['error']
                        })
                    
                    pbar.update(1)
                    if progress_callback:
                        progress_callback(result)
        
        return results