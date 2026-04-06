import json
import shutil
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
    timeline: list[str] | None = None
    debug_dir: str | None = None


class LegacyParserAdapter:
    def parse_pdf_bytes(self, filename: str, content: bytes, debug_dir: Path | None = None) -> ParserOutcome:
        with tempfile.TemporaryDirectory(prefix="novo_afi_parser_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            input_dir = temp_dir / "nfs_analise"
            output_dir = temp_dir / "output_dfs"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            (input_dir / filename).write_bytes(content)
            timeline = [
                "Upload salvo no backend.",
                "main_v9.py iniciado.",
            ]

            process = subprocess.run(
                ["python", str(SCRIPT_PATH)],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )

            logs = self._read_log_entries(temp_dir / "log.json")
            spreadsheet = self._find_output_spreadsheet(output_dir)
            persisted_debug_dir = self._persist_debug_artifacts(
                temp_dir=temp_dir,
                debug_dir=debug_dir,
                stdout_text=process.stdout,
                stderr_text=process.stderr,
            )
            timeline.append(f"main_v9.py retornou com código {process.returncode}.")

            if spreadsheet is not None:
                dataframe = pd.read_excel(spreadsheet)
                rows = dataframe.where(pd.notna(dataframe), None).to_dict(orient="records")
                if rows:
                    timeline.append(f"Parser encontrou {len(rows)} linha(s) na planilha.")
                    if persisted_debug_dir:
                        timeline.append(f"Saída temporária salva em {persisted_debug_dir}.")
                    return ParserOutcome(
                        status="processado",
                        rows=rows,
                        timeline=timeline,
                        debug_dir=persisted_debug_dir,
                    )

            if process.returncode != 0:
                timeline.append("Parser encerrou com erro.")
                if persisted_debug_dir:
                    timeline.append(f"Saída temporária salva em {persisted_debug_dir}.")
                return ParserOutcome(
                    status="erro_parsing",
                    rows=[],
                    error=(process.stderr or process.stdout or "Falha ao executar o parser legado.").strip(),
                    timeline=timeline,
                    debug_dir=persisted_debug_dir,
                )

            timeline.append("Parser não retornou planilha com linhas.")
            if persisted_debug_dir:
                timeline.append(f"Saída temporária salva em {persisted_debug_dir}.")
            return ParserOutcome(
                status=self._map_status(logs),
                rows=[],
                reason=self._extract_reason(logs),
                error=self._extract_error(logs),
                timeline=timeline,
                debug_dir=persisted_debug_dir,
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

    def _persist_debug_artifacts(
        self,
        temp_dir: Path,
        debug_dir: Path | None,
        stdout_text: str,
        stderr_text: str,
    ) -> str | None:
        if debug_dir is None:
            return None

        debug_dir.mkdir(parents=True, exist_ok=True)

        files_to_copy = [
            temp_dir / "log.json",
            temp_dir / "output_dfs",
        ]

        for source in files_to_copy:
            if not source.exists():
                continue
            target = debug_dir / source.name
            if source.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)

        (debug_dir / "stdout.txt").write_text(stdout_text or "", encoding="utf-8")
        (debug_dir / "stderr.txt").write_text(stderr_text or "", encoding="utf-8")
        return str(debug_dir)
