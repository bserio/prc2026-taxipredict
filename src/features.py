"""Construction de features, tout ajustement appris sur le train du pli uniquement.

Piste « causal » : aucune information postérieure à l'off-block. Les compteurs de
congestion utilisent les horaires PUBLIÉS (SCHED_TIME) de la période évaluée, connus
à l'avance ; la capacité par aéroport est une constante historique estimée sur les
mois d'entraînement. La géométrie stand/piste est apprise du taxi-in des arrivées.

Piste « hybrid » : ajoute le proxy MVT_TIME - AOBT_3, la piste réellement utilisée et
les débits réellement réalisés sur la période évaluée.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.prepare import diff_minutes, epoch, slot

CAT_COLS = ["ADEP_mvt", "AIRCRAFT_TYPE_mvt", "AIRCRAFT_TYPE_flt", "WK_TBL_CAT_flt",
            "MARKET_SEGMENT_flt", "FLIGHT_RULE_mvt", "FLIGHT_RULE_flt", "FLIGHT_TYPE_flt"]
HYBRID_CATS = ["RUNWAY_mvt"]
TE_KEYS = {
    "te_ap_stand": ["ADEP_mvt", "STAND_mvt"],
    "te_ap_hour": ["ADEP_mvt", "hour"],
    "te_ap_dow_slot": ["ADEP_mvt", "dow", "slot_group"],
    "te_ac_mvt": ["AIRCRAFT_TYPE_mvt"],
    "te_operator": ["AIRCRAFT_OPERATOR_flt"],
}
SHRINK_K = 200.0
MIN_GEO_OBS = 20


def _codes(series: pd.Series, categories: list[str]) -> np.ndarray:
    idx = {v: i for i, v in enumerate(categories)}
    return series.astype("object").map(idx).fillna(-1).to_numpy(dtype="int32")


def _key_frame(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    out = df[keys].copy()
    for k in keys:
        if not pd.api.types.is_integer_dtype(out[k]):
            out[k] = out[k].astype("object").fillna("__na__")
    return out


@dataclass
class FeatureSpec:
    track: str = "causal"
    use_runway_actual: bool = False
    use_dest_pressure: bool = False                 # mesuré nuisible (D-016), conserve pour reproduction
    use_regime_flag: bool = False                   # 1 si le vol n'a AUCUNE information reseau (D-025)
    use_stand: bool = True                          # a False : plus AUCUNE variable deduite de STAND_mvt (D-035)
    use_lobt: bool = True                           # a False : ni ecart a LOBT_flt ni indicateur d'absence (D-035)
    epoch_seconds: bool = False                     # faux = fidele aux specs gelees avant D-034 (echelle ms)
    cats: dict = field(default_factory=dict)        # colonne -> catégories triées
    enc: dict = field(default_factory=dict)         # nom -> (table, valeur de repli)
    geo_mu: dict = field(default_factory=dict)      # aéroport -> taxi-in moyen (s)
    geo_rwy: dict = field(default_factory=dict)     # (aéroport, piste) -> offset (s)
    geo_stand: dict = field(default_factory=dict)   # aéroport -> {stand: offset (s)}
    geo_exp: dict = field(default_factory=dict)     # (aéroport, stand, heure) -> offset piste espéré (s)
    capacity: dict = field(default_factory=dict)    # aéroport -> p95 d'arrivées réalisées par créneau

    def _epoch(self, series: pd.Series) -> np.ndarray:
        """Secondes vraies si `epoch_seconds` ; sinon l'echelle historique des specs gelees (D-034).

        Les modeles fournis ont ete regles avant la correction d'echelle : leurs specifications
        restent reproduites a l'identique tant qu'elles portent `epoch_seconds = false` (defaut).
        """
        s = pd.to_datetime(series, utc=True)
        if self.epoch_seconds:
            out = np.array((s - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds(),
                           dtype="float64", copy=True)
        else:
            out = s.astype("int64").to_numpy(dtype="float64") / 1e9
        out[np.asarray(pd.isna(s))] = np.nan
        return out

    # ------------------------------------------------------------------ apprentissage
    def fit(self, dep_train: pd.DataFrame, arr_train: pd.DataFrame, y: np.ndarray) -> "FeatureSpec":
        keep = np.isfinite(y) & (y > 60) & (y < 7200)
        dtr = dep_train.loc[keep].copy()
        ytr = np.asarray(y, dtype="float64")[keep]
        sched = pd.to_datetime(dtr["SCHED_TIME_UTC_mvt"], utc=True)
        dtr["hour"] = sched.dt.hour.astype("int32")
        dtr["dow"] = sched.dt.dayofweek.astype("int32")
        dtr["slot_group"] = (sched.dt.hour // 4).astype("int32")

        for col in CAT_COLS + (HYBRID_CATS if self.use_runway_actual else []):
            values = dtr[col].dropna().astype("object").unique().tolist()
            self.cats[col] = sorted(map(str, values))

        for name, keys in self._te_keys().items():
            frame = _key_frame(dtr, keys)
            frame["_y"] = ytr
            grp = frame.groupby(keys, dropna=False)["_y"].agg(["mean", "count"])
            parent = float(ytr.mean())
            smoothed = (grp["mean"] * grp["count"] + parent * SHRINK_K) / (grp["count"] + SHRINK_K)
            table = {}
            for key, value in smoothed.items():
                table[key if len(keys) > 1 else key[0]] = float(value)
            self.enc[name] = (table, parent)

        if self.use_stand:
            self._fit_geometry(arr_train)
            self._fit_expected_runway(dtr)
        self._fit_capacity(arr_train)
        return self

    def _te_keys(self) -> dict[str, list[str]]:
        """Encodages par cible effectivement presents dans cette variante de spec (D-035)."""
        if self.use_stand:
            return TE_KEYS
        return {k: v for k, v in TE_KEYS.items() if k != "te_ap_stand"}

    def _fit_geometry(self, arr: pd.DataFrame) -> None:
        """taxi_in ~ mu_aeroport + offset_piste + offset_stand (3 passes, seuil d'observations)."""
        a = arr.dropna(subset=["ADES_mvt", "RUNWAY_mvt", "STAND_mvt", "TAXITIME_SEC_mvt"]).copy()
        a = a[(a.TAXITIME_SEC_mvt > 60) & (a.TAXITIME_SEC_mvt < 7200)]
        if a.empty:
            return
        a["rw"] = a.RUNWAY_mvt.astype(str)
        a["st"] = a.STAND_mvt.astype(str)
        for ap, g in a.groupby("ADES_mvt"):
            ap = str(ap)
            t = g.TAXITIME_SEC_mvt.to_numpy(dtype="float64")
            mu = float(t.mean())
            self.geo_mu[ap] = mu
            r_idx = pd.Index(sorted(g.rw.unique()))
            s_idx = pd.Index(sorted(g.st.unique()))
            r_off = pd.Series(0.0, index=r_idx)
            s_off = pd.Series(0.0, index=s_idx)
            rw = g.rw.to_numpy()
            st = g.st.to_numpy()
            for _ in range(3):
                res = pd.Series(t - mu - s_off.reindex(st).fillna(0.0).to_numpy(), index=rw)
                r_off = res.groupby(level=0).mean().where(res.groupby(level=0).size() >= MIN_GEO_OBS, 0.0)
                r_off = r_off.reindex(r_idx).fillna(0.0)
                res = pd.Series(t - mu - r_off.reindex(rw).fillna(0.0).to_numpy(), index=st)
                s_off = res.groupby(level=0).mean().where(res.groupby(level=0).size() >= MIN_GEO_OBS, 0.0)
                s_off = s_off.reindex(s_idx).fillna(0.0)
            self.geo_rwy.update({(ap, str(k)): float(v) for k, v in r_off.items()})
            self.geo_stand[ap] = {str(k): float(v) for k, v in s_off.items()}

    def _fit_expected_runway(self, dtr: pd.DataFrame) -> None:
        """E[offset piste | aéroport, stand, heure] à partir des départs du train."""
        d = dtr.dropna(subset=["RUNWAY_mvt", "STAND_mvt"]).copy()
        if d.empty:
            return
        d["rwy_off"] = [self.geo_rwy.get((str(a), str(r)), 0.0) for a, r in zip(d.ADEP_mvt, d.RUNWAY_mvt)]
        agg = d.groupby(["ADEP_mvt", "STAND_mvt", "hour"], dropna=False).rwy_off.mean()
        self.geo_exp = {(str(a), str(s), int(h)): float(v) for (a, s, h), v in agg.items()}

    def _fit_capacity(self, arr: pd.DataFrame) -> None:
        a = arr.dropna(subset=["ADES_mvt", "MVT_TIME_UTC_mvt"])
        if a.empty:
            return
        e = self._epoch(a.MVT_TIME_UTC_mvt)
        ok = np.isfinite(e)
        counts = (pd.DataFrame({"ap": a.ADES_mvt.astype("object").to_numpy()[ok], "slot": slot(e[ok])})
                  .groupby(["ap", "slot"]).size())
        self.capacity = {str(ap): float(max(v, 1.0)) for ap, v in counts.groupby(level=0).quantile(0.95).items()}

    # ------------------------------------------------------------------ transformation
    def transform(self, dep: pd.DataFrame, arr_period: pd.DataFrame | None) -> pd.DataFrame:
        sched = pd.to_datetime(dep["SCHED_TIME_UTC_mvt"], utc=True)
        hour = sched.dt.hour.astype("int32")
        dow = sched.dt.dayofweek.astype("int32")
        X = pd.DataFrame(index=range(len(dep)), dtype="float32")
        X["hour"] = hour.to_numpy()
        X["dow"] = dow.to_numpy()
        X["month"] = sched.dt.month.to_numpy()
        X["dom"] = sched.dt.day.to_numpy()
        X["is_weekend"] = (dow.to_numpy() >= 5).astype("int8")
        X["hour_sin"] = np.sin(2 * np.pi * hour / 24).to_numpy(dtype="float32")
        X["hour_cos"] = np.cos(2 * np.pi * hour / 24).to_numpy(dtype="float32")

        for col in CAT_COLS + (HYBRID_CATS if self.use_runway_actual else []):
            if col in dep.columns:
                X[f"c_{col}"] = _codes(dep[col], self.cats.get(col, []))

        for out, col in (("d_eobt_min", "EOBT_1_flt"), ("d_iobt_min", "IOBT_flt"), ("d_lobt_min", "LOBT_flt")):
            if out == "d_lobt_min" and not self.use_lobt:
                continue                                        # variante sans LOBT (D-035)
            v = diff_minutes(dep[col], dep["SCHED_TIME_UTC_mvt"])
            X[out] = np.clip(np.where(np.isfinite(v), v, np.nan), -180.0, 900.0).astype("float32")
            X[f"miss_{col}"] = (~np.isfinite(v)).astype("int8")

        if self.use_regime_flag:
            # Vol sans AUCUNE fiche reseau : marqueur pris cote planification (EOBT_1 absent), ce qui
            # designe la meme population que l'audit (D-025) sans toucher a une donnee realisee.
            X["regime_sans_reseau"] = dep["EOBT_1_flt"].isna().to_numpy().astype("int8")

        aps = dep["ADEP_mvt"].astype("object").to_numpy()
        sts = dep["STAND_mvt"].astype("object").to_numpy()
        if self.use_stand:
            stand_off = np.array([float((self.geo_stand.get(str(a)) or {}).get(str(s), 0.0)) for a, s in zip(aps, sts)],
                                 dtype="float32")
            exp_rwy = np.array([self._expected_runway(a, s, h) for a, s, h in zip(aps, sts, hour.to_numpy())],
                               dtype="float32")
            X["geo_stand_sec"] = stand_off
            X["geo_exp_rwy_sec"] = exp_rwy
            X["geo_exp_total_sec"] = (stand_off + exp_rwy).astype("float32")
        else:                                                   # variante sans poste : rien ne vient du stand (D-035)
            stand_off = np.zeros(len(dep), dtype="float32")

        tmp = dep.copy()
        tmp["hour"] = hour.to_numpy()
        tmp["dow"] = dow.to_numpy()
        tmp["slot_group"] = (hour // 4).to_numpy()
        for name, keys in self._te_keys().items():
            table, parent = self.enc.get(name, ({}, float("nan")))
            frame = _key_frame(tmp, keys)
            if len(keys) == 1:
                mapped = frame[keys[0]].map(table)
            else:
                keys_list = list(map(tuple, frame.to_numpy()))
                mapped = pd.Series([table.get(k, np.nan) for k in keys_list], index=frame.index)
            X[name] = mapped.fillna(parent).to_numpy(dtype="float32")

        for name, values in self._congestion(dep, arr_period, realized=False).items():
            X[name] = values.astype("float32")
        if self.track == "hybrid":
            for name, values in self._congestion(dep, arr_period, realized=True).items():
                X[name] = values.astype("float32")
            proxy = diff_minutes(dep["MVT_TIME_UTC_mvt"], dep["AOBT_3_flt"]) * 60.0
            X["proxy_sec"] = np.where(np.isfinite(proxy), proxy, np.nan).astype("float32")
            X["d_aobt_min"] = diff_minutes(dep["AOBT_3_flt"], dep["SCHED_TIME_UTC_mvt"]).astype("float32")
            if self.use_runway_actual:
                rwy_off = np.array([self.geo_rwy.get((str(a), str(r)), 0.0)
                                    for a, r in zip(aps, dep.RUNWAY_mvt.astype("object"))], dtype="float32")
                X["geo_act_total_sec"] = (stand_off + rwy_off).astype("float32")
        return X

    def _expected_runway(self, ap: str, stand, hour) -> float:
        if not self.geo_exp:
            return 0.0
        v = self.geo_exp.get((str(ap), str(stand), int(hour)))
        if v is not None:
            return float(v)
        cands = [val for (a, s, _h), val in self.geo_exp.items() if a == str(ap) and s == str(stand)]
        return float(np.mean(cands)) if cands else 0.0

    def _congestion(self, dep: pd.DataFrame, arr_period: pd.DataFrame | None, realized: bool) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        sched = pd.to_datetime(dep["SCHED_TIME_UTC_mvt"], utc=True)
        self_slot = slot(self._epoch(sched))
        ap = dep["ADEP_mvt"].astype("object").to_numpy()
        suffix = "real" if realized else "sched"

        counts: pd.DataFrame | None = None
        if arr_period is not None and len(arr_period):
            col = "MVT_TIME_UTC_mvt" if realized else "SCHED_TIME_UTC_mvt"
            e = self._epoch(arr_period[col])
            ok = np.isfinite(e)
            counts = (pd.DataFrame({"ap": arr_period["ADES_mvt"].astype("object").to_numpy()[ok], "slot": slot(e[ok])})
                      .groupby(["ap", "slot"]).size().rename("n").reset_index())
            now = None
            for lag, tag in ((-1, "prev"), (0, "now"), (1, "next")):
                key = pd.DataFrame({"ap": ap, "slot": self_slot + lag})
                merged = key.merge(counts, on=["ap", "slot"], how="left")["n"].fillna(0.0).to_numpy(dtype="float32")
                out[f"arr_{tag}_{suffix}"] = merged
                if tag == "now":
                    now = merged
            cap = np.array([self.capacity.get(str(a), np.nan) for a in ap], dtype="float32")
            with np.errstate(invalid="ignore", divide="ignore"):
                out["arr_load_ratio"] = np.where(cap > 0, now / cap, np.nan).astype("float32")

        dep_counts = (pd.DataFrame({"ap": ap, "slot": self_slot}).groupby(["ap", "slot"]).size()
                      .rename("n").reset_index())
        key = pd.DataFrame({"ap": ap, "slot": self_slot})
        out["dep_now"] = (key.merge(dep_counts, on=["ap", "slot"], how="left")["n"].fillna(1).to_numpy(dtype="float32") - 1.0)

        # Pression cote destination : un vol dont l'aero d'arrivee est sature est retenu au sol.
        # Mesure nuisible en dev (D-016) : desactivee sauf config explicite features.dest_pressure.
        if self.use_dest_pressure:
            ades = dep["ADES_mvt"].astype("object").to_numpy() if "ADES_mvt" in dep.columns else ap
            dkey = pd.DataFrame({"ap": ades, "slot": self_slot})
            if counts is not None:
                out[f"dest_arr_{suffix}"] = dkey.merge(counts, on=["ap", "slot"], how="left")["n"].fillna(0.0).to_numpy(dtype="float32")
            out[f"dest_dep_{suffix}"] = (dkey.merge(dep_counts, on=["ap", "slot"], how="left")["n"].fillna(1.0)
                                         .to_numpy(dtype="float32") - 1.0)
        return out

    def categorical_names(self) -> list[str]:
        return [f"c_{c}" for c in self.cats]

    # ------------------------------------------------------------------ persistance
    def to_dict(self) -> dict:
        def enc_keys(table: dict) -> dict:
            return {"|".join(str(p) for p in k) if isinstance(k, tuple) else str(k): v for k, v in table.items()}

        return {
            "track": self.track,
            "use_runway_actual": self.use_runway_actual,
            "use_dest_pressure": self.use_dest_pressure,
            "use_regime_flag": self.use_regime_flag,
            "use_stand": self.use_stand,
            "use_lobt": self.use_lobt,
            "epoch_seconds": self.epoch_seconds,
            "cats": self.cats,
            "enc": {name: [enc_keys(table), parent] for name, (table, parent) in self.enc.items()},
            "geo_mu": self.geo_mu,
            "geo_rwy": {f"{a}|{r}": v for (a, r), v in self.geo_rwy.items()},
            "geo_stand": self.geo_stand,
            "geo_exp": {f"{a}|{s}|{h}": v for (a, s, h), v in self.geo_exp.items()},
            "capacity": self.capacity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureSpec":
        spec = cls(track=data["track"], use_runway_actual=data["use_runway_actual"],
                   use_dest_pressure=bool(data.get("use_dest_pressure", False)),
                   use_regime_flag=bool(data.get("use_regime_flag", False)),
                   use_stand=bool(data.get("use_stand", True)),
                   use_lobt=bool(data.get("use_lobt", True)),
                   epoch_seconds=bool(data.get("epoch_seconds", False)))
        spec.cats = {k: list(v) for k, v in data["cats"].items()}
        spec.enc = {}
        for name, (table, parent) in data["enc"].items():
            keys = TE_KEYS[name]
            restored = {}
            for k, v in table.items():
                parts = k.split("|")
                if len(keys) == 1:
                    restored[parts[0]] = v
                else:
                    restored[tuple(int(p) if p.lstrip("-").isdigit() and keys[i] in ("hour", "dow", "slot_group")
                                   else p for i, p in enumerate(parts))] = v
            spec.enc[name] = (restored, parent)
        spec.geo_mu = dict(data["geo_mu"])
        spec.geo_rwy = {tuple(k.split("|")): v for k, v in data["geo_rwy"].items()}
        spec.geo_stand = {k: dict(v) for k, v in data["geo_stand"].items()}
        spec.geo_exp = {}
        for k, v in data["geo_exp"].items():
            a, s, h = k.split("|")
            spec.geo_exp[(a, s, int(h))] = v
        spec.capacity = dict(data["capacity"])
        return spec
