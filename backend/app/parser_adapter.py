import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parent / "main_v9.py"


@dataclass
class ParserOutcome:
    status: str
    rows: list[dict]
    reason: str | None = None
    error: str | None = None


class LegacyParserAdapter:
    def parse_pdf_bytes(self, filename: str, content: bytes) -> ParserOutcome:
        with tempfile.TemporaryDirectory(prefix="novo_afi_parser_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            input_dir = temp_dir / "nfs_analise"
            output_dir = temp_dir / "output_dfs"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            (input_dir / filename).write_bytes(content)

            process = subprocess.run(
                ["python", str(SCRIPT_PATH)],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )

            logs = self._read_log_entries(temp_dir / "log.json")
            spreadsheet = self._find_output_spreadsheet(output_dir)

            if spreadsheet is not None:
                dataframe = pd.read_excel(spreadsheet)
                rows = dataframe.where(pd.notna(dataframe), None).to_dict(orient="records")
                if rows:
                    return ParserOutcome(status="processado", rows=rows)

            if process.returncode != 0:
                return ParserOutcome(
                    status="erro_parsing",
                    rows=[],
                    error=(process.stderr or process.stdout or "Falha ao executar o parser legado.").strip(),
                )

            return ParserOutcome(
                status=self._map_status(logs),
                rows=[],
                reason=self._extract_reason(logs),
                error=self._extract_error(logs),
            )

    def _read_log_entries(self, log_path: Path) -> list[dict]:
        if not log_path.exists():
            return []

        entries = []
        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return entries

    def _find_output_spreadsheet(self, output_dir: Path) -> Path | None:
        spreadsheets = sorted(output_dir.glob("*.xlsx"))
        return spreadsheets[0] if spreadsheets else None

    def _map_status(self, logs: list[dict]) -> str:
        statuses = [entry.get("status") for entry in logs if entry.get("status")]
        if not statuses:
            return "erro_parsing"
        if "processado" in statuses:
            return "processado"
        if "rejeitado" in statuses:
            return "rejeitado"
        return "erro_parsing"

    def _extract_reason(self, logs: list[dict]) -> str | None:
        for entry in reversed(logs):
            reason = entry.get("movivo") or entry.get("status_reason")
            if reason:
                return str(reason)
        return None

    def _extract_error(self, logs: list[dict]) -> str | None:
        for entry in reversed(logs):
            error = entry.get("erro")
            if error:
                return str(error)
        return None
