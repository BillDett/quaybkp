# Quay Blob Backup and Restore Tool

## Objective
A simple CLI tool that will back up or restore all blobs from/to a Quay namespace.

## Usage

    $ # Environment variables
	$ QUAY_CONFIG=$(QUAY)/config.yaml
	$ S3_ACCESS_KEY_ID=<r/w key for backup S3 account>
	$ S3_SECRET_ACCESS_KEY=<secret for key>
	$ S3_ENDPOINT_URL=<URL for S3 endpoint>

	$ quaybkp --help
    Backs up and restores image storage for a Quay namespace to/from an S3 compatible endpoint.

    Usage:
      quaybkp [command] [options]

    Available Commands:
      backup        Back up a namespace
      restore       Restore a namespace
      unlock        Remove a lock on a backup bucket
      verify        Verify a backup against Quay

    Options:
      --help            help for quaybkp
      --bucket-name     Name of the bucket where backups are stored (default is 'quaybackup')

    $ quaybkp backup --help
    Back up the image blobs for a specific namespace in Quay to an S3 compatible endpoint.

    Description:
      Back up the image blobs for a specific namespace in Quay to an S3 compatible endpoint.
    
    Usage:
      quaybkp backup NAMESPACE [options]
    
    Options:
       --force-blobs     Transfer and write image blobs even if they already exist in backup destination.
      --num-workers     Number of backup workers to operate in parallel while doing the backup (default 5)

	
    $ quaybkp restore --help
    Restores a backup for a specific namespace in Quay from an S3 compatible endpoint.

    Description:
      Restores a backup for a specific namespace in Quay from an S3 compatible endpoint.
    
    Usage:
      quaybkp restore NAMESPACE [options]
    
    Options:
      --dry-run         Don't actually transfer or write blobs, just list what actions would take place
      --force-blobs     Transfer and write image blobs even if they already exist in backup destination.
      --repository      Name of a single repository to restore (default is all repositories).
      --from            Backup number to restore (default is latest)
      --num-workers     Number of backup workers to operate in parallel while doing the restore (default 5)

    $ quaybkp verify --help
    Verifies a backup for a specific namespace from an S3 compatible endpoint against contents in Quay.

    Description:
      Verifies a backup for a specific namespace from an S3 compatible endpoint against contents in Quay.
    
    Usage:
      quaybkp verify NAMESPACE [options]
    
    Options:
      --from            Backup number to verify (default is latest)

    $ quaybkp unlock --help
    Removes a lockfile from a backup bucket.

    Description:
      Removes a lockfile from a backup bucket. Use with caution as removing a lock while a backup is running could allow for inventory file corruption.
    
    Usage:
      quaybkp unlock NAMESPACE


## Design

The tool operates on a single Quay namespace at a time. From the backup, it can 'restore' the full namespace's worth of image data. This avoids the need to backup a Quay installation's entire image blob storage (which could be substantial). All it needs is a Quay config bundle, and read/write to an S3-compatible endpoint.

### Backup Structure

In the backup S3, a bucket called `quaybackup` (or whatever is provided by the `--bucket-name` option) is created if it does not exist. The bucket contains all of the image blobs owned by the namespace, along with a set of backup inventory files that are created at the time of each backup.

All resources in the backup bucket are prefaced with the name of the namespace as found in Quay's `user` table.

Each inventory file is named according to the monotonically increasing backup number. The highest numbered inventory file corresponds to the latest backup performed. Inventory files are prefaced with `backup/` to make them easier to list in the bucket.

The bucket also contains a single `backup/lock` file which indicates that a backup is currently in progress. This file is removed when a backup completes.

Image blobs are prefaced with `sha256/` and the first two significant digits of the digest to make it easier to list blobs in the bucket.

For example:

    quaybackup
            openshift-release-dev/backup/lock
            openshift-release-dev/backup/1.json
            openshift-release-dev/backup/2.json
            openshift-release-dev/backup/3.json
            openshift-release-dev/sha256/99/99e349980bc1457ce7b7b954f41f5a99cc6968e5a06c0839baff26a3d76e7451
            openshift-release-dev/sha256/00/00c6ae7a48f2a1e04cd9354ea2dc928b1c865ffc3cf90e13552de6991cbccf74

Blobs in the backup bucket are never removed, even if a blob is removed from Quay's storage. This is intentional to keep the backup tool as simple as possible. At some point in the future a `prune` command could be issued that would remove any blobs not found in the latest inventory file.


### Making Backups

Backups should be easy to run manually or within automation. When performing a backup, the tool will first query the backup bucket to determine if a `backup/lock` file exists. If so, the tool exits, otherwise it chooses the next backup number based on the inventory files (using `1` if no inventory files are found). It will then confirm the namespace given exists in Quay, and then starts walking through all repositories and all manifests in each repository, fetching the image blobs from Quay's storage and writing them to the backup bucket.

Because a Quay namespace might contain a large amount of data to be transferred, it would be too slow to serially transfer each blob one at a time. Internally, the tool creates multiple backup workers. Each worker will be assigned a set of blobs to be transferred. The worker should first check if the blob exists in the backup bucket and only read/transfer the blobs if it doesn't exist or the `--force-blobs` option is enabled. Each worker should provide a visual indication its progress towards finishing all of its assigned blobs.


Once the tool has completed scanning all repositories and manifests it will output an inventory file named according to the backup number performed. The inventory file will list all repositories, their manifests, child manifests, and the related blobs for the namespace. It should be sufficient to provide a full record to allow a restore of the namespace with the listed blobs.

For example, the fifteenth inventory might be (`backup/15.json`):

    {
        "User": "openshift-release-dev",
        "Id": "392",
        "Repositories": [
            {
                "Name": "ocp-art4-dev",
                "Id": "24233",
                "Manifests": [
                    "3799eb368ae8fbc4871741b2e04655b24ded8b2e4e829ff91e8adf5b40ea12d5": [
                        "7808182d8e618bbf9f82415e96a7f56c5f33d10aa3077fe2b007d3f7568d2912",
                        "0469e3718eaf2c7a14ef2af3e50d9b6147bb8e2111f50d33b202676e8fcb0b53",
                        ...
                    ],
                    ...
                ]
            }
        ],
        "Summary": {
            "Completed": "Friday, Aug 8, 2025 14:45",
            "Status": "Success",
            "RepositoriesCreated": "3",
            "ManifestsCreated": "23",
            "Data": {
                "Blobs": "56",
                "BytesWritten": "3827323"
            }
        }
    }

The inventory file 'flattens' child manifests as it's not critical to preserve manifest list structures simply to restore blobs. The tool should run idempotently with the exception of the creation of a new inventory file each time. This allows us to simply retry in the event of an interrupted backup process.

Once the backup itself is completed, the `backup/lock` file is then removed from the bucket.


### Restoring Backups

Restores should be done manually. When restoring a namespace, first a check is made whether a `backup/lock` file exists in the backup bucket. If so, the restore is cancelled. 

The tool should then which inventory file to use based on what was given through the `--from` option or the highest number found. The tool should  fail if attempting to restore from a failed backup, meaning an inventory file where the "Status" field is "Failed" or missing.

Reading the inventory file, blobs are copied from the S3 endpoint into Quay's storage. Before a blob is read/transferred, the tool first checks if the blob exists in Quay's storage. If it does, and the `--force-blobs` flag is not enabled, the blob is transferred, otherwise it is skipped. 

Internally, the tool creates multiple restore workers that are assigned a set of blobs from the backup bucket. The number of workers can be set with the `--num-workers` option. Each worker should provide a visual indication of its progress towards restoring its assigned blobs.

Upon completion, the tool will output a report to the console:

     {
        "User": "openshift-release-dev",
        "Id": "392",
        "Restore Summary": {
            "Completed": "Monday, Aug 11, 2025 11:15",
            "Status": "Success",
            "RepositoriesCreated": "25",
            "ManifestsCreated": "578",
            "Data": {
                "Blobs": "2534",
                "BytesWritten": "8760543273938"
            }
        }
    }

Multiple restores from the same inventory file should be idempotent. It should be possible to re-start a failed restore from an inventory and existing blobs will be ignored (unless `--force-blobs` is enabled).

### Verifying backups

When verifying a backup, the tool will confirm that all of the blobs seen in Quay's storage for the given namespace are present in the inventory file given (or the last inventory if none is given). If any blobs are missing in the backup, it is considered "Incomplete", otherwise it is considered "Complete". If the inventory file Status is not "Success", the verification is still performed but a warning is provided. 

Upon completion, the tool will output a report to the console:

     {
        "User": "openshift-release-dev",
        "Id": "392",
        "Verify Summary": {
            "Completed": "Monday, Aug 11, 2025 11:55",
            "Inventory": "15",
            "Status": "Complete",
            "RepositoriesSeen": "25",
            "ManifestsSeen": "578",
            "Data": {
                "Blobs": "2534",
                "BytesSeen": "8760543273938"
            }
        }
    }


### Unlocking backups

If a `backup/lock` file needs to be removed due to a failed backup process, the `quaybkp unlock` command should be used. This just removes the file from the bucket and does not check if a backup is actually occurring. Use caution with this command as unlocking a bucket while a backup is happening will not affect the backup however if another backup against that namespace is attempted at the same time, the inventory file might be corrupted.

### TODO

* Consider a single pooled `sha256` prefix so that we can avoid having to do restores entirely by pointing a Quay instance at the backup bucket directly
* Consider a `prune` command that will keep the backup bucket from growing forever.
* Should we introduce the concept of blob deduplication so we only really process each blob once?
