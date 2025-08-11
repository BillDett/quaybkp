"""Progress reporting utilities."""

import sys
from typing import Any, Dict
from tqdm import tqdm


class ProgressReporter:
    """Progress reporting for long-running operations."""
    
    def __init__(self, total: int, description: str = "Processing", unit: str = "items"):
        self.total = total
        self.description = description
        self.unit = unit
        self.progress_bar = None
        self.processed = 0
        self.errors = 0
    
    def start(self):
        """Start progress reporting."""
        self.progress_bar = tqdm(
            total=self.total,
            desc=self.description,
            unit=self.unit,
            file=sys.stdout
        )
    
    def update(self, result: Dict[str, Any]):
        """Update progress with operation result."""
        if self.progress_bar:
            if result.get('success', False):
                self.processed += 1
            else:
                self.errors += 1
            
            self.progress_bar.set_postfix({
                'processed': self.processed,
                'errors': self.errors
            })
            self.progress_bar.update(1)
    
    def finish(self):
        """Finish progress reporting."""
        if self.progress_bar:
            self.progress_bar.close()
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finish()