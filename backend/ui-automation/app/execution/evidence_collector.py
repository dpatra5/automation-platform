import structlog
from pathlib import Path
from typing import Optional

logger = structlog.get_logger(__name__)

class EvidenceCollector:
    """Collects evidence like network/console logs."""
    def __init__(self, run_id: str, artifacts_dir: str):
        self.run_id = run_id
        self.artifacts_dir = Path(artifacts_dir) / run_id
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.console_logs = []
        self.network_logs = []

    def log_console(self, msg: str):
        self.console_logs.append(msg)

    def log_network(self, request: str):
        self.network_logs.append(request)

    def save(self) -> dict:
        """Persist logs to disk."""
        console_path = self.artifacts_dir / "console.log"
        network_path = self.artifacts_dir / "network.log"
        
        console_path.write_text("\n".join(self.console_logs))
        network_path.write_text("\n".join(self.network_logs))
        
        logger.info("saved_evidence", run_id=self.run_id)
        return {
            "console": str(console_path),
            "network": str(network_path)
        }
