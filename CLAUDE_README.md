# Quay Blob Backup and Restore Tool

A Python CLI tool for backing up and restoring Quay namespace image blobs to/from S3-compatible storage.

## Installation

```bash
# Basic installation
pip install -e .

# With Google Cloud Storage support
pip install -e ".[gcs]"

# With Azure Storage support  
pip install -e ".[azure]"

# With all cloud storage backends
pip install -e ".[all]"
```

## Configuration

Set the following environment variables:

```bash
export QUAY_CONFIG=/path/to/quay/config.yaml
export S3_ACCESS_KEY_ID=your_access_key
export S3_SECRET_ACCESS_KEY=your_secret_key
export S3_ENDPOINT_URL=https://your-s3-endpoint.com
```

## Usage

```bash
# Backup a namespace
quaybkp backup my-namespace

# Restore a namespace
quaybkp restore my-namespace

# Verify a backup
quaybkp verify my-namespace

# Unlock a stuck backup
quaybkp unlock my-namespace
```

## Architecture

The tool consists of several key components:

- **Database Layer**: Connects to Quay's PostgreSQL database to identify blobs
- **Storage Backends**: Interfaces for both Quay storage and S3 backup storage
- **Worker Pools**: Concurrent processing for efficient blob transfer
- **Operations**: High-level backup, restore, verify, and unlock operations
- **CLI Interface**: User-friendly command-line interface

## Features

- **Multi-Storage Backend Support**: Works with Quay's distributed storage including:
  - Local filesystem storage
  - S3-compatible object storage (S3, CloudFront S3)
  - Google Cloud Storage
  - Azure Blob Storage
- **Concurrent Processing**: Multi-threaded blob transfers for better performance
- **Lock Management**: Prevents concurrent backups with lock files
- **Incremental Backups**: Only transfers blobs that don't already exist
- **Verification**: Compare backup completeness against current Quay state
- **Dry Run**: Preview restore operations before execution
- **Progress Reporting**: Visual progress bars for long-running operations
- **Error Handling**: Comprehensive error reporting and recovery

## Backup Structure

Backups are stored in S3 with the following structure:

```
bucket/
├── {namespace_id}-{namespace_name}/
│   ├── backup/
│   │   ├── lock              # Backup in progress indicator
│   │   ├── 1.json           # Backup inventory files
│   │   ├── 2.json
│   │   └── 3.json
│   └── blob/
│       ├── ab/              # First 2 chars of digest
│       │   └── abc123...    # Full blob digest
│       └── cd/
│           └── cdef456...
```

## Development

The codebase follows a modular architecture:

- `config/`: Configuration management
- `database/`: Database connections and queries
- `storage/`: S3 and Quay storage interfaces
- `operations/`: High-level operations (backup, restore, etc.)
- `workers/`: Concurrent blob processing
- `models/`: Data models for inventory and namespace objects
- `utils/`: Logging and progress reporting utilities