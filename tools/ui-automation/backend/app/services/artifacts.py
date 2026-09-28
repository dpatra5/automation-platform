"""Removing the files a deleted run leaves behind.

Every run writes a directory of its own under the artifacts root - screenshots,
video, trace, console and network logs. Deleting only the database row would
leave that behind, and a few hundred abandoned runs is gigabytes of video
nobody can reach from the dashboard any more.
"""

import logging
import shutil
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _under(path: Path, parent: Path) -> bool:
    """Whether a path really sits directly inside the directory it should.

    Ids come from the database rather than from a request, but a delete that
    walks out of the artifacts tree is the one mistake here that cannot be
    undone, so the check is made anyway.
    """
    try:
        return path.resolve().parent == parent.resolve()
    except OSError:
        return False


def _remove(directory: Path, parent: Path) -> bool:
    if not _under(directory, parent) or not directory.is_dir():
        return False
    try:
        shutil.rmtree(directory)
        return True
    except OSError as e:
        # A file still held open by a video encoder that has not exited yet.
        # The run is gone from the dashboard either way, and leftovers are not
        # worth failing the request for.
        logger.warning("Could not remove %s: %s", directory, e)
        return False


def remove_run_artifacts(run_id: str) -> bool:
    """Delete the evidence directory of one run."""
    root = Path(settings.artifacts_dir)
    return _remove(root / run_id, root)


def remove_batch_artifacts(batch_id: str) -> bool:
    """Delete the consolidated report written for one sequence."""
    batches = Path(settings.artifacts_dir) / "batches"
    return _remove(batches / batch_id, batches)
