"""Namespace and repository data models."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Namespace:
    """Represents a Quay namespace/user."""
    id: int
    name: str
    organization: bool


@dataclass
class Repository:
    """Represents a Quay repository."""
    id: int
    name: str
    namespace_user: int
    visibility: str
    description: Optional[str] = None


@dataclass
class Manifest:
    """Represents a container manifest."""
    id: int
    repository_id: int
    digest: str
    media_type: str


@dataclass
class Blob:
    """Represents a container blob."""
    blob_id: int
    uuid: str
    image_size: int
    checksum: str
    cas_path: str
    uploading: bool = False