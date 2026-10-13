"""Partitions temporelles et empreintes.

L'unité de partition est le fichier mensuel officiel (les bornes de fichiers se
recouvrent de quelques secondes, ce recouvrement est donc traité comme une seule
partition par mois) ; pour les entrées finales 2026, un seul fichier couvre quatre
mois et le mois est déduit de MVT_TIME_UTC_mvt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


@dataclass(frozen=True)
class Protocol:
    all_months: tuple[str, ...]
    reserve_months: tuple[str, ...]
    dev_val_months: tuple[str, ...]
    final_months: tuple[str, ...] = ("2026-01", "2026-02", "2026-06", "2026-07")
    witness_months: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, cfg: dict) -> "Protocol":
        p = cfg["protocol"] if "protocol" in cfg else cfg
        return cls(
            all_months=tuple(p["all_months"]),
            reserve_months=tuple(p["reserve_months"]),
            dev_val_months=tuple(p["dev_val_months"]),
            final_months=tuple(p["final"]["months"]),
            witness_months=tuple(p.get("witness_months", ())),
        )

    def train_months(self, val_month: str) -> tuple[str, ...]:
        excluded = set(self.reserve_months) | {val_month}
        return tuple(m for m in self.all_months if m not in excluded)

    def reserve_train_months(self) -> tuple[str, ...]:
        return tuple(m for m in self.all_months if m not in set(self.reserve_months))

    def folds(self) -> list[tuple[str, tuple[str, ...], str]]:
        return [(f"hold-{m}", self.train_months(m), m) for m in self.dev_val_months]

    def witness_folds(self) -> list[tuple[str, tuple[str, ...], str]]:
        """Pli de controle elargi : meme mecanique, autres mois tenus hors.

        Ces mois ne departagent jamais deux recettes ; ils elastiquent l'estimation.
        La reserve (reserve_months) en reste exclue, comme partout ailleurs.
        """
        return [(f"wit-{m}", self.train_months(m), m) for m in self.witness_months]


def month_ids(path: Path, phase: str = "DEP", id_col: str = "MVT_ID_mvt") -> list[float]:
    """Identifiants de la population évaluée d'un fichier (départs uniquement)."""
    table = pq.read_table(path, columns=[id_col, "PHASE_mvt"])
    import pyarrow.compute as pc

    dep = table.filter(pc.equal(table["PHASE_mvt"], phase))
    return dep[id_col].to_pylist()


def _sha256_of_ids(ids: list[float]) -> str:
    h = hashlib.sha256()
    for value in sorted(ids):
        h.update(f"{value:.0f}\n".encode())
    return h.hexdigest()


def fingerprint(protocol: Protocol, official_dir: Path) -> dict:
    """Empreinte des partitions de développement et de la réserve (identifiants triés)."""
    out: dict[str, Any] = {"files": {}, "splits": {}}
    per_month: dict[str, list[float]] = {}
    for month in protocol.all_months:
        from src.config import training_file

        path = training_file(official_dir, month)
        ids = month_ids(path)
        per_month[month] = ids
        out["files"][path.name] = {"phase": "DEP", "n_dep": len(ids), "sha256_ids": _sha256_of_ids(ids)}

    def split_ids(months: list[str] | tuple[str, ...]) -> list[float]:
        return [i for m in months for i in per_month[m]]

    out["splits"]["reserve"] = {
        "months": list(protocol.reserve_months),
        "n_dep": len(split_ids(protocol.reserve_months)),
        "sha256_ids": _sha256_of_ids(split_ids(protocol.reserve_months)),
    }
    for name, train, val in protocol.folds():
        out["splits"][name] = {
            "train_months": list(train),
            "val_month": val,
            "n_train_dep": len(split_ids(train)),
            "n_val_dep": len(split_ids([val])),
            "sha256_val_ids": _sha256_of_ids(split_ids([val])),
        }
    return out


def save_fingerprint(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
