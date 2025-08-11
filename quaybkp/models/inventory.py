"""Backup inventory data models."""

from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass, asdict


@dataclass
class BackupSummary:
    """Summary information for a backup operation."""
    completed: str
    status: str  # "Success", "Failed", "In Progress"
    repositories_created: str
    manifests_created: str
    data: Dict[str, str]  # "Blobs", "BytesWritten"


@dataclass
class RepositoryBackup:
    """Repository backup information."""
    name: str
    id: str
    manifests: Dict[str, List[str]]  # manifest_digest -> [blob_digests]


@dataclass
class BackupInventory:
    """Complete backup inventory."""
    user: str
    id: str
    repositories: List[RepositoryBackup]
    summary: BackupSummary
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "User": self.user,
            "Id": self.id,
            "Repositories": [
                {
                    "Name": repo.name,
                    "Id": repo.id,
                    "Manifests": repo.manifests
                }
                for repo in self.repositories
            ],
            "Summary": {
                "Completed": self.summary.completed,
                "Status": self.summary.status,
                "RepositoriesCreated": self.summary.repositories_created,
                "ManifestsCreated": self.summary.manifests_created,
                "Data": self.summary.data
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BackupInventory':
        """Create from dictionary loaded from JSON."""
        repositories = []
        for repo_data in data.get("Repositories", []):
            repositories.append(RepositoryBackup(
                name=repo_data["Name"],
                id=repo_data["Id"],
                manifests=repo_data["Manifests"]
            ))
        
        summary_data = data.get("Summary", {})
        summary = BackupSummary(
            completed=summary_data.get("Completed", ""),
            status=summary_data.get("Status", "Failed"),
            repositories_created=summary_data.get("RepositoriesCreated", "0"),
            manifests_created=summary_data.get("ManifestsCreated", "0"),
            data=summary_data.get("Data", {})
        )
        
        return cls(
            user=data.get("User", ""),
            id=data.get("Id", ""),
            repositories=repositories,
            summary=summary
        )


@dataclass
class RestoreSummary:
    """Summary information for a restore operation."""
    completed: str
    status: str
    repositories_created: str
    manifests_created: str
    data: Dict[str, str]


@dataclass
class VerifySummary:
    """Summary information for a verify operation."""
    completed: str
    inventory: str
    status: str  # "Complete", "Incomplete"
    repositories_seen: str
    manifests_seen: str
    data: Dict[str, str]