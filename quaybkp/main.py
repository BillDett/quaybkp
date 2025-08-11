"""Main CLI entry point for quaybkp."""

import argparse
import json
import sys
import logging
from typing import Dict, Any

from .config.settings import Config
from .operations.backup import BackupOperation
from .operations.restore import RestoreOperation
from .operations.verify import VerifyOperation
from .operations.unlock import UnlockOperation
from .utils.logger import setup_logging


logger = logging.getLogger(__name__)


def print_json_output(data: Dict[str, Any]):
    """Print formatted JSON output."""
    print(json.dumps(data, indent=2))


def handle_backup(args):
    """Handle backup command."""
    try:
        config = Config()
        backup_op = BackupOperation(config, args.bucket_name)
        
        result = backup_op.backup_namespace(
            namespace_name=args.namespace,
            force_blobs=args.force_blobs,
            num_workers=args.num_workers
        )
        
        output = {
            "Operation": "Backup",
            "Namespace": result['namespace'],
            "BackupNumber": result['backup_number'],
            "Summary": {
                "Completed": result['summary'].completed,
                "Status": result['summary'].status,
                "RepositoriesCreated": result['summary'].repositories_created,
                "ManifestsCreated": result['summary'].manifests_created,
                "Data": result['summary'].data
            }
        }
        
        if result['backup_results']['errors']:
            output["Errors"] = result['backup_results']['errors'][:5]  # Show first 5 errors
        
        print_json_output(output)
        
        if result['backup_results']['failed_blobs'] > 0:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        print_json_output({
            "Operation": "Backup",
            "Status": "Failed",
            "Error": str(e)
        })
        sys.exit(1)


def handle_restore(args):
    """Handle restore command."""
    try:
        config = Config()
        restore_op = RestoreOperation(config, args.bucket_name)
        
        result = restore_op.restore_namespace(
            namespace_name=args.namespace,
            backup_number=getattr(args, 'from', None),
            repository_filter=args.repository,
            dry_run=args.dry_run,
            force_blobs=args.force_blobs,
            num_workers=args.num_workers
        )
        
        if args.dry_run:
            output = {
                "Operation": "Restore (Dry Run)",
                "Namespace": result['namespace'],
                "Summary": result['summary']
            }
            if 'actions' in result:
                output["Actions"] = result['actions']
        else:
            output = {
                "Operation": "Restore",
                "Namespace": result['namespace'],
                "Restore Summary": {
                    "Completed": result['restore_summary'].completed,
                    "Status": result['restore_summary'].status,
                    "RepositoriesCreated": result['restore_summary'].repositories_created,
                    "ManifestsCreated": result['restore_summary'].manifests_created,
                    "Data": result['restore_summary'].data
                }
            }
            
            if result['restore_results']['errors']:
                output["Errors"] = result['restore_results']['errors'][:5]  # Show first 5 errors
        
        print_json_output(output)
        
        if not args.dry_run and result['restore_results']['failed_blobs'] > 0:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        print_json_output({
            "Operation": "Restore",
            "Status": "Failed",
            "Error": str(e)
        })
        sys.exit(1)


def handle_verify(args):
    """Handle verify command."""
    try:
        config = Config()
        verify_op = VerifyOperation(config, args.bucket_name)
        
        result = verify_op.verify_backup(
            namespace_name=args.namespace,
            backup_number=getattr(args, 'from', None)
        )
        
        output = {
            "Operation": "Verify",
            "Namespace": result['namespace'],
            "Verify Summary": {
                "Completed": result['verify_summary'].completed,
                "Inventory": result['verify_summary'].inventory,
                "Status": result['verify_summary'].status,
                "RepositoriesSeen": result['verify_summary'].repositories_seen,
                "ManifestsSeen": result['verify_summary'].manifests_seen,
                "Data": result['verify_summary'].data
            }
        }
        
        if result['verification_details']['missing_blobs'] > 0:
            output["IncompleteDetails"] = {
                "MissingBlobs": result['verification_details']['missing_blobs'],
                "ExampleMissingBlobs": result['verification_details']['missing_blob_list']
            }
        
        print_json_output(output)
        
        if result['verify_summary'].status != "Complete":
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Verify failed: {e}")
        print_json_output({
            "Operation": "Verify",
            "Status": "Failed",
            "Error": str(e)
        })
        sys.exit(1)


def handle_unlock(args):
    """Handle unlock command."""
    try:
        config = Config()
        unlock_op = UnlockOperation(config, args.bucket_name)
        
        result = unlock_op.unlock_namespace(args.namespace)
        
        output = {
            "Operation": "Unlock",
            "Namespace": result['namespace'],
            "LockExisted": result['lock_existed'],
            "Message": result['message']
        }
        
        print_json_output(output)
        
    except Exception as e:
        logger.error(f"Unlock failed: {e}")
        print_json_output({
            "Operation": "Unlock",
            "Status": "Failed",
            "Error": str(e)
        })
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='quaybkp',
        description='Backs up and restores image storage for a Quay namespace to/from an S3 compatible endpoint.'
    )
    
    parser.add_argument(
        '--bucket-name',
        default='quaybackup',
        help='Name of the bucket where backups are stored (default: quaybackup)'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )
    parser.add_argument(
        '--log-file',
        help='Log to file in addition to console'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Backup command
    backup_parser = subparsers.add_parser(
        'backup',
        help='Back up a namespace',
        description='Back up the image blobs for a specific namespace in Quay to an S3 compatible endpoint.'
    )
    backup_parser.add_argument('namespace', help='Namespace to backup')
    backup_parser.add_argument(
        '--force-blobs',
        action='store_true',
        help='Transfer and write image blobs even if they already exist in backup destination'
    )
    backup_parser.add_argument(
        '--num-workers',
        type=int,
        default=5,
        help='Number of backup workers to operate in parallel (default: 5)'
    )
    backup_parser.set_defaults(func=handle_backup)
    
    # Restore command
    restore_parser = subparsers.add_parser(
        'restore',
        help='Restore a namespace',
        description='Restores a backup for a specific namespace in Quay from an S3 compatible endpoint.'
    )
    restore_parser.add_argument('namespace', help='Namespace to restore')
    restore_parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Don't actually transfer or write blobs, just list what actions would take place"
    )
    restore_parser.add_argument(
        '--force-blobs',
        action='store_true',
        help='Transfer and write image blobs even if they already exist in destination'
    )
    restore_parser.add_argument(
        '--repository',
        help='Name of a single repository to restore (default: all repositories)'
    )
    restore_parser.add_argument(
        '--from',
        dest='from',
        type=int,
        help='Backup number to restore (default: latest)'
    )
    restore_parser.add_argument(
        '--num-workers',
        type=int,
        default=5,
        help='Number of restore workers to operate in parallel (default: 5)'
    )
    restore_parser.set_defaults(func=handle_restore)
    
    # Verify command
    verify_parser = subparsers.add_parser(
        'verify',
        help='Verify a backup',
        description='Verifies a backup for a specific namespace from an S3 compatible endpoint against contents in Quay.'
    )
    verify_parser.add_argument('namespace', help='Namespace to verify')
    verify_parser.add_argument(
        '--from',
        dest='from',
        type=int,
        help='Backup number to verify (default: latest)'
    )
    verify_parser.set_defaults(func=handle_verify)
    
    # Unlock command
    unlock_parser = subparsers.add_parser(
        'unlock',
        help='Remove a lock on a backup bucket',
        description='Removes a lockfile from a backup bucket. Use with caution as removing a lock while a backup is running could allow for inventory file corruption.'
    )
    unlock_parser.add_argument('namespace', help='Namespace to unlock')
    unlock_parser.set_defaults(func=handle_unlock)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    setup_logging(args.log_level, args.log_file)
    
    args.func(args)


if __name__ == '__main__':
    main()