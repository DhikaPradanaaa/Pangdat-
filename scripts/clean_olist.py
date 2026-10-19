from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


CSV_FILES = [
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
    "olist_products_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_geolocation_dataset.csv",
]

BRAZIL_STATES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
}

RULES = {
    "GEO_EXACT_DUPLICATE": ("Redundancy", "warning", "Baris geolokasi identik dihapus saat kanonisasi."),
    "GEO_COORDINATE_OUTSIDE_BRAZIL": ("Accuracy", "error", "Koordinat berada di luar bounding box perkiraan Brasil."),
    "GEO_PREFIX_NO_VALID_COORDINATES": ("Completeness", "error", "Prefix kode pos tidak mempunyai koordinat yang lolos validasi."),
    "GEO_PREFIX_MULTIPLE_CITY_STATE": ("Consistency", "warning", "Satu prefix kode pos memiliki lebih dari satu kombinasi kota dan provinsi."),
    "GEO_PREFIX_NOT_FOUND": ("Adherence to Data Integrity Rules", "warning", "Prefix kode pos tidak ditemukan di referensi geolokasi."),
    "GEO_CITY_STATE_DIFFERS_FROM_CANONICAL": ("Consistency", "warning", "Kota atau provinsi sumber berbeda dari nilai kanonis prefix kode pos."),
    "STATE_OUTSIDE_DOMAIN": ("Domain Integrity", "error", "Kode provinsi tidak termasuk domain resmi negara bagian Brasil."),
    "PRODUCT_CATEGORY_MISSING": ("Completeness", "warning", "Kategori produk kosong dan dipetakan ke sentinel unknown."),
    "PRODUCT_CATEGORY_UNMAPPED": ("Consistency", "warning", "Kategori produk belum memiliki terjemahan bahasa Inggris resmi."),
    "PRODUCT_METADATA_INCOMPLETE": ("Completeness", "warning", "Metadata nama, deskripsi, atau jumlah foto produk tidak lengkap."),
    "PRODUCT_DIMENSION_MISSING": ("Completeness", "warning", "Satu atau lebih ukuran fisik produk kosong."),
    "PRODUCT_WEIGHT_NONPOSITIVE": ("Conformance to Business Rule", "warning", "Berat produk nol atau negatif diubah menjadi kosong."),
    "ORDER_STATUS_OUTSIDE_DOMAIN": ("Domain Integrity", "error", "Status pesanan berada di luar domain yang dikenal."),
    "ORDER_DATE_UNPARSEABLE": ("Data Type", "error", "Nilai tanggal pesanan tidak dapat diubah menjadi datetime."),
    "ORDER_REQUIRED_DATE_MISSING": ("Completeness", "error", "Tanggal wajib untuk status pesanan tidak tersedia."),
    "ORDER_CARRIER_BEFORE_APPROVAL": ("Conformance to Business Rule", "warning", "Tanggal penyerahan ke kurir lebih awal dari persetujuan pesanan."),
    "ORDER_DELIVERY_BEFORE_CARRIER": ("Conformance to Business Rule", "error", "Tanggal diterima pelanggan lebih awal dari penyerahan ke kurir."),
    "ORDER_CANCELED_WITH_DELIVERY": ("Conformance to Business Rule", "warning", "Pesanan dibatalkan tetapi memiliki tanggal diterima pelanggan."),
    "ORDER_WITHOUT_ITEMS": ("Adherence to Data Integrity Rules", "error", "Pesanan aktif tidak mempunyai baris item."),
    "ORDER_WITHOUT_PAYMENT": ("Adherence to Data Integrity Rules", "warning", "Pesanan tidak mempunyai baris pembayaran."),
    "ORDER_PAYMENT_TOTAL_MISMATCH": ("Accuracy", "warning", "Total pembayaran berbeda dari harga item ditambah ongkir lebih dari toleransi."),
    "ITEM_DATE_UNPARSEABLE": ("Data Type", "error", "Batas waktu pengiriman item tidak dapat diubah menjadi datetime."),
    "ITEM_VALUE_NEGATIVE": ("Domain Integrity", "error", "Harga atau ongkir bernilai negatif."),
    "PAYMENT_TYPE_UNKNOWN": ("Clarity", "warning", "Tipe pembayaran not_defined distandardisasi menjadi unknown."),
    "PAYMENT_INSTALLMENT_ZERO": ("Conformance to Business Rule", "warning", "Jumlah cicilan nol untuk kartu kredit distandardisasi menjadi satu."),
    "PAYMENT_VALUE_NEGATIVE": ("Domain Integrity", "error", "Nilai pembayaran negatif."),
    "REVIEW_DUPLICATE_ID_REKEYED": ("Duplication", "warning", "Review ID dipakai untuk pesanan berbeda; review_key komposit ditambahkan."),
    "REVIEW_SCORE_OUTSIDE_DOMAIN": ("Domain Integrity", "error", "Skor ulasan berada di luar rentang 1 sampai 5."),
    "REVIEW_DATE_UNPARSEABLE": ("Data Type", "error", "Tanggal ulasan tidak dapat diubah menjadi datetime."),
    "REVIEW_ANSWER_BEFORE_CREATION": ("Conformance to Business Rule", "error", "Jawaban ulasan tercatat sebelum ulasan dibuat."),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scalar(value):
    if value is None or value is pd.NA:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def normalize_text(series: pd.Series, lower: bool = False, upper: bool = False) -> pd.Series:
    result = series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    result = result.map(lambda x: unicodedata.normalize("NFC", x) if isinstance(x, str) else x)
    if lower:
        result = result.str.lower()
    if upper:
        result = result.str.upper()
    return result


def normalize_zip(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").astype("Int64")
    return numeric.astype("string").str.zfill(5)


def iso_datetime(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    parsed = pd.to_datetime(series, errors="coerce")
    bad = series.notna() & parsed.isna()
    formatted = parsed.dt.strftime("%Y-%m-%d %H:%M:%S").astype("string")
    return formatted, bad


class QualityTracker:
    def __init__(self):
        self.issues: list[dict] = []
        self.row_flags: dict[str, dict[int, list[tuple[str, str, str]]]] = defaultdict(lambda: defaultdict(list))
        self.rule_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.transformations: list[dict] = []

    def record_transformation(self, table: str, action: str, affected_rows: int, detail: str):
        self.transformations.append({
            "table": table,
            "action": action,
            "affected_rows": int(affected_rows),
            "detail": detail,
        })

    def flag(
        self,
        table: str,
        df: pd.DataFrame,
        mask: pd.Series,
        rule_id: str,
        key_columns: list[str],
        column: str,
        action: str,
        disposition: str = "open",
        original_column: str | None = None,
        detail: str = "",
    ):
        mask = mask.fillna(False)
        dimension, severity, description = RULES[rule_id]
        indices = df.index[mask]
        self.rule_counts[rule_id]["detected"] += len(indices)
        self.rule_counts[rule_id][disposition] += len(indices)
        for idx in indices:
            key = "|".join(str(scalar(df.at[idx, col])) for col in key_columns)
            original = scalar(df.at[idx, original_column or column]) if (original_column or column) in df.columns else ""
            self.issues.append({
                "table": table,
                "record_key": key,
                "rule_id": rule_id,
                "dimension": dimension,
                "severity": severity,
                "column": column,
                "original_value": original,
                "action": action,
                "disposition": disposition,
                "detail": detail or description,
            })
            self.row_flags[table][int(idx)].append((rule_id, severity, disposition))

    def flag_records(
        self,
        table: str,
        records: list[dict],
        rule_id: str,
        disposition: str,
    ):
        dimension, severity, description = RULES[rule_id]
        self.rule_counts[rule_id]["detected"] += len(records)
        self.rule_counts[rule_id][disposition] += len(records)
        for row in records:
            self.issues.append({
                "table": table,
                "record_key": row.get("record_key", ""),
                "rule_id": rule_id,
                "dimension": dimension,
                "severity": severity,
                "column": row.get("column", ""),
                "original_value": row.get("original_value", ""),
                "action": row.get("action", "review"),
                "disposition": disposition,
                "detail": row.get("detail", description),
            })

    def attach_status(self, table: str, df: pd.DataFrame) -> pd.DataFrame:
        statuses = []
        codes = []
        for idx in df.index:
            flags = self.row_flags[table].get(int(idx), [])
            codes.append(";".join(sorted({item[0] for item in flags})))
            if any(severity == "error" and disposition in {"open", "quarantined"} for _, severity, disposition in flags):
                statuses.append("error")
            elif any(disposition in {"open", "quarantined"} for _, _, disposition in flags):
                statuses.append("warning")
            elif flags:
                statuses.append("corrected")
            else:
                statuses.append("valid")
        result = df.copy()
        result["dq_status"] = statuses
        result["dq_issue_codes"] = codes
        return result

    def rule_results(self) -> pd.DataFrame:
        rows = []
        for rule_id, (dimension, severity, description) in RULES.items():
            counts = self.rule_counts.get(rule_id, {})
            detected = int(counts.get("detected", 0))
            corrected = int(counts.get("corrected", 0))
            quarantined = int(counts.get("quarantined", 0))
            open_count = int(counts.get("open", 0))
            rows.append({
                "rule_id": rule_id,
                "dimension": dimension,
                "severity": severity,
                "description": description,
                "detected_count": detected,
                "corrected_count": corrected,
                "quarantined_count": quarantined,
                "open_count": open_count,
                "result": "PASS" if detected == 0 else ("CORRECTED" if open_count == 0 else "REVIEW"),
            })
        return pd.DataFrame(rows)


def safe_extract(zip_path: Path, target: Path):
    with zipfile.ZipFile(zip_path) as archive:
        expected = set(CSV_FILES)
        available = {Path(name).name for name in archive.namelist() if not name.endswith("/")}
        missing = expected - available
        if missing:
            raise ValueError(f"Missing expected CSV files: {sorted(missing)}")
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if name not in expected:
                continue
            destination = (target / name).resolve()
            if target.resolve() not in destination.parents:
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def build_dictionary(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    grain = {
        "olist_customers_dataset.csv": "Satu customer_id per pesanan; customer_unique_id menghubungkan pelanggan berulang.",
        "olist_sellers_dataset.csv": "Satu baris per seller_id.",
        "olist_products_dataset.csv": "Satu baris per product_id.",
        "product_category_name_translation.csv": "Satu baris per kategori produk Portugis.",
        "olist_orders_dataset.csv": "Satu baris per order_id.",
        "olist_order_items_dataset.csv": "Satu baris per kombinasi order_id dan order_item_id.",
        "olist_order_payments_dataset.csv": "Satu baris per kombinasi order_id dan payment_sequential.",
        "olist_order_reviews_dataset.csv": "Satu baris per review_key, yaitu review_id dan order_id.",
        "olist_geolocation_dataset.csv": "Satu baris kanonis per geolocation_zip_code_prefix.",
    }
    key_map = {
        "customer_id": "Primary key pelanggan pada level pesanan.",
        "customer_unique_id": "Identitas pelanggan stabil untuk pembelian berulang.",
        "seller_id": "Primary key penjual.",
        "product_id": "Primary key produk.",
        "order_id": "Identitas pesanan dan foreign key ke tabel orders.",
        "order_item_id": "Nomor urut item di dalam pesanan.",
        "payment_sequential": "Nomor urut pembayaran di dalam pesanan.",
        "review_id": "Identitas ulasan dari sumber; tidak unik secara global pada dataset ini.",
        "review_key": "Kunci komposit unik review_id dan order_id.",
        "geolocation_zip_code_prefix": "Prefix kode pos lima digit.",
        "dq_status": "Status kualitas baris: valid, corrected, warning, atau error.",
        "dq_issue_codes": "Daftar rule_id kualitas yang berlaku pada baris.",
    }
    rows = []
    for table, df in cleaned.items():
        for column in df.columns:
            series = df[column]
            dtype = str(series.dtype)
            nullable = bool(series.isna().any())
            description = key_map.get(column, column.replace("_", " ").capitalize())
            domain = ""
            if column.endswith("_state"):
                domain = "Kode provinsi Brasil dua huruf"
            elif column == "order_status":
                domain = "created, approved, invoiced, processing, shipped, delivered, unavailable, canceled"
            elif column == "payment_type":
                domain = "credit_card, boleto, voucher, debit_card, unknown"
            elif column == "review_score":
                domain = "Integer 1-5"
            elif column == "dq_status":
                domain = "valid, corrected, warning, error"
            rows.append({
                "table": table,
                "grain": grain.get(table, ""),
                "column": column,
                "data_type": dtype,
                "nullable_in_output": nullable,
                "description": description,
                "domain_or_format": domain,
            })
    return pd.DataFrame(rows)


def write_csv(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def main():
    parser = argparse.ArgumentParser(description="Clean and quality-check the Olist OLTP dataset.")
    parser.add_argument("--input-zip", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    source_zip = args.input_zip.resolve()
    output_dir = args.output_dir.resolve()
    if not source_zip.is_file():
        raise FileNotFoundError(source_zip)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory must be new or empty: {output_dir}")

    raw_dir = output_dir / "raw"
    clean_dir = output_dir / "clean"
    quarantine_dir = output_dir / "quarantine"
    metadata_dir = output_dir / "metadata"
    for path in (raw_dir, clean_dir, quarantine_dir, metadata_dir):
        path.mkdir(parents=True, exist_ok=True)

    processed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    tracker = QualityTracker()
    safe_extract(source_zip, raw_dir)

    raw: dict[str, pd.DataFrame] = {
        name: pd.read_csv(raw_dir / name, low_memory=False) for name in CSV_FILES
    }
    raw_counts = {name: len(df) for name, df in raw.items()}

    customers = raw["olist_customers_dataset.csv"].copy()
    sellers = raw["olist_sellers_dataset.csv"].copy()
    products = raw["olist_products_dataset.csv"].copy()
    translations = raw["product_category_name_translation.csv"].copy()
    orders = raw["olist_orders_dataset.csv"].copy()
    items = raw["olist_order_items_dataset.csv"].copy()
    payments = raw["olist_order_payments_dataset.csv"].copy()
    reviews = raw["olist_order_reviews_dataset.csv"].copy()
    geo = raw["olist_geolocation_dataset.csv"].copy()

    # Geolocation: standardize, remove exact duplicates, quarantine implausible coordinates,
    # and collapse to one deterministic canonical row per ZIP prefix.
    geo["geolocation_zip_code_prefix"] = normalize_zip(geo["geolocation_zip_code_prefix"])
    geo["geolocation_city"] = normalize_text(geo["geolocation_city"], lower=True)
    geo["geolocation_state"] = normalize_text(geo["geolocation_state"], upper=True)
    geo["geolocation_lat"] = pd.to_numeric(geo["geolocation_lat"], errors="coerce")
    geo["geolocation_lng"] = pd.to_numeric(geo["geolocation_lng"], errors="coerce")
    exact_dupes = geo.duplicated(keep="first")
    tracker.rule_counts["GEO_EXACT_DUPLICATE"]["detected"] = int(exact_dupes.sum())
    tracker.rule_counts["GEO_EXACT_DUPLICATE"]["corrected"] = int(exact_dupes.sum())
    tracker.record_transformation(
        "olist_geolocation_dataset.csv",
        "remove_exact_duplicates_before_canonicalization",
        int(exact_dupes.sum()),
        "Duplikat persis tidak digunakan lebih dari sekali saat membangun referensi kanonis.",
    )
    geo_dedup = geo.loc[~exact_dupes].copy()
    outside = (
        geo_dedup["geolocation_lat"].isna()
        | geo_dedup["geolocation_lng"].isna()
        | (geo_dedup["geolocation_lat"] < -34)
        | (geo_dedup["geolocation_lat"] > 6)
        | (geo_dedup["geolocation_lng"] < -74)
        | (geo_dedup["geolocation_lng"] > -34)
    )
    tracker.flag(
        "olist_geolocation_dataset.csv", geo_dedup, outside,
        "GEO_COORDINATE_OUTSIDE_BRAZIL", ["geolocation_zip_code_prefix"],
        "geolocation_lat", "exclude_from_canonical_coordinate", "quarantined",
        detail="Koordinat dikeluarkan dari perhitungan median kanonis dan disalin ke karantina.",
    )
    geo_quarantine = geo_dedup.loc[outside].copy()
    if not geo_quarantine.empty:
        geo_quarantine["dq_status"] = "error"
        geo_quarantine["dq_issue_codes"] = "GEO_COORDINATE_OUTSIDE_BRAZIL"
        write_csv(geo_quarantine, quarantine_dir / "olist_geolocation_dataset.csv")

    valid_geo = geo_dedup.loc[~outside].copy()
    combo_counts = (
        geo_dedup.groupby(
            ["geolocation_zip_code_prefix", "geolocation_city", "geolocation_state"],
            dropna=False,
        )
        .size()
        .reset_index(name="combo_count")
        .sort_values(
            ["geolocation_zip_code_prefix", "combo_count", "geolocation_city", "geolocation_state"],
            ascending=[True, False, True, True],
        )
    )
    canonical_labels = combo_counts.drop_duplicates("geolocation_zip_code_prefix", keep="first")
    coord_medians = valid_geo.groupby("geolocation_zip_code_prefix", as_index=False).agg(
        geolocation_lat=("geolocation_lat", "median"),
        geolocation_lng=("geolocation_lng", "median"),
        valid_coordinate_count=("geolocation_lat", "size"),
    )
    source_counts = geo_dedup.groupby("geolocation_zip_code_prefix", as_index=False).size().rename(
        columns={"size": "source_point_count"}
    )
    excluded_counts = geo_dedup.loc[outside].groupby(
        "geolocation_zip_code_prefix", as_index=False
    ).size().rename(columns={"size": "excluded_coordinate_count"})
    combination_counts = (
        combo_counts.groupby("geolocation_zip_code_prefix", as_index=False)
        .size()
        .rename(columns={"size": "source_city_state_count"})
    )
    canonical_geo = (
        canonical_labels[
            ["geolocation_zip_code_prefix", "geolocation_city", "geolocation_state"]
        ]
        .merge(coord_medians, on="geolocation_zip_code_prefix", how="left")
        .merge(source_counts, on="geolocation_zip_code_prefix", how="left")
        .merge(excluded_counts, on="geolocation_zip_code_prefix", how="left")
        .merge(combination_counts, on="geolocation_zip_code_prefix", how="left")
        .sort_values("geolocation_zip_code_prefix")
        .reset_index(drop=True)
    )
    canonical_geo["valid_coordinate_count"] = canonical_geo["valid_coordinate_count"].fillna(0).astype(int)
    canonical_geo["excluded_coordinate_count"] = canonical_geo["excluded_coordinate_count"].fillna(0).astype(int)
    canonical_geo["geolocation_conflict_flag"] = canonical_geo["source_city_state_count"].fillna(0).gt(1)
    tracker.record_transformation(
        "olist_geolocation_dataset.csv", "canonicalize_to_one_row_per_zip_prefix",
        len(canonical_geo),
        "Kota/provinsi dipilih berdasarkan frekuensi tertinggi dan koordinat kanonis memakai median titik valid.",
    )
    geo_conflict = canonical_geo["geolocation_conflict_flag"]
    tracker.flag(
        "olist_geolocation_dataset.csv", canonical_geo, geo_conflict,
        "GEO_PREFIX_MULTIPLE_CITY_STATE", ["geolocation_zip_code_prefix"],
        "geolocation_city", "select_most_frequent_city_state", "open",
        detail="Nilai kanonis dipilih berdasarkan frekuensi tertinggi; konflik tetap ditandai untuk peninjauan.",
    )
    no_valid_coordinates = canonical_geo["valid_coordinate_count"].eq(0)
    tracker.flag(
        "olist_geolocation_dataset.csv", canonical_geo, no_valid_coordinates,
        "GEO_PREFIX_NO_VALID_COORDINATES", ["geolocation_zip_code_prefix"],
        "geolocation_lat", "retain_prefix_with_null_coordinates", "quarantined",
        detail="Prefix dipertahankan agar referensi tidak hilang; koordinat dibiarkan kosong dan perlu verifikasi eksternal.",
    )
    canonical_geo = tracker.attach_status("olist_geolocation_dataset.csv", canonical_geo)
    canonical_geo_errors = canonical_geo.loc[canonical_geo["dq_status"].eq("error")]
    if not canonical_geo_errors.empty:
        write_csv(canonical_geo_errors, quarantine_dir / "olist_geolocation_canonical.csv")

    # Customers and sellers: normalize identifiers and addresses, then compare to canonical geography.
    canonical_lookup = canonical_geo.set_index("geolocation_zip_code_prefix")
    for table_name, df, prefix in [
        ("olist_customers_dataset.csv", customers, "customer"),
        ("olist_sellers_dataset.csv", sellers, "seller"),
    ]:
        id_col = f"{prefix}_id"
        zip_col = f"{prefix}_zip_code_prefix"
        city_col = f"{prefix}_city"
        state_col = f"{prefix}_state"
        df[id_col] = normalize_text(df[id_col])
        if prefix == "customer":
            df["customer_unique_id"] = normalize_text(df["customer_unique_id"])
        df[zip_col] = normalize_zip(df[zip_col])
        df[city_col] = normalize_text(df[city_col], lower=True)
        df[state_col] = normalize_text(df[state_col], upper=True)
        df[f"{prefix}_city_canonical"] = df[zip_col].map(canonical_lookup["geolocation_city"])
        df[f"{prefix}_state_canonical"] = df[zip_col].map(canonical_lookup["geolocation_state"])
        tracker.record_transformation(
            table_name, "standardize_location_fields", len(df),
            "Kode pos menjadi teks lima digit; kota dinormalisasi; provinsi menjadi kode dua huruf kapital; kolom kanonis ditambahkan.",
        )
        missing_geo = df[f"{prefix}_city_canonical"].isna()
        tracker.flag(
            table_name, df, missing_geo, "GEO_PREFIX_NOT_FOUND", [id_col], zip_col,
            "retain_source_location_and_flag", "open",
        )
        mismatch = (~missing_geo) & (
            df[city_col].ne(df[f"{prefix}_city_canonical"])
            | df[state_col].ne(df[f"{prefix}_state_canonical"])
        )
        tracker.flag(
            table_name, df, mismatch, "GEO_CITY_STATE_DIFFERS_FROM_CANONICAL", [id_col],
            city_col, "retain_source_and_expose_canonical_columns", "open",
        )
        invalid_state = ~df[state_col].isin(BRAZIL_STATES)
        tracker.flag(
            table_name, df, invalid_state, "STATE_OUTSIDE_DOMAIN", [id_col], state_col,
            "retain_and_quarantine", "quarantined",
        )

    # Product category translations and product metadata.
    translations["product_category_name"] = normalize_text(translations["product_category_name"], lower=True)
    translations["product_category_name_english"] = normalize_text(
        translations["product_category_name_english"], lower=True
    )
    translations["translation_status"] = "mapped"
    products = products.rename(columns={
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    })
    tracker.record_transformation(
        "olist_products_dataset.csv", "rename_misspelled_length_columns", len(products),
        "product_name_lenght dan product_description_lenght diganti menjadi product_name_length dan product_description_length.",
    )
    products["product_id"] = normalize_text(products["product_id"])
    products["product_category_name"] = normalize_text(products["product_category_name"], lower=True)
    missing_category = products["product_category_name"].isna()
    tracker.flag(
        "olist_products_dataset.csv", products, missing_category, "PRODUCT_CATEGORY_MISSING",
        ["product_id"], "product_category_name", "map_to_unknown_sentinel", "corrected",
    )
    products.loc[missing_category, "product_category_name"] = "unknown"
    tracker.record_transformation(
        "olist_products_dataset.csv", "map_missing_category_to_unknown", int(missing_category.sum()),
        "Kategori kosong dipetakan ke sentinel eksplisit unknown; kondisi asal tetap tercatat di quality_issues.",
    )
    numeric_columns = [
        "product_name_length", "product_description_length", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm",
    ]
    for column in numeric_columns:
        products[column] = pd.to_numeric(products[column], errors="coerce")
    metadata_missing = products[
        ["product_name_length", "product_description_length", "product_photos_qty"]
    ].isna().any(axis=1)
    tracker.flag(
        "olist_products_dataset.csv", products, metadata_missing, "PRODUCT_METADATA_INCOMPLETE",
        ["product_id"], "product_name_length", "retain_null_and_flag", "open",
    )
    dimension_columns = ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]
    dimension_missing = products[dimension_columns].isna().any(axis=1)
    tracker.flag(
        "olist_products_dataset.csv", products, dimension_missing, "PRODUCT_DIMENSION_MISSING",
        ["product_id"], "product_weight_g", "retain_null_and_flag", "open",
    )
    weight_nonpositive = products["product_weight_g"].notna() & products["product_weight_g"].le(0)
    tracker.flag(
        "olist_products_dataset.csv", products, weight_nonpositive, "PRODUCT_WEIGHT_NONPOSITIVE",
        ["product_id"], "product_weight_g", "set_to_null", "open",
    )
    products.loc[weight_nonpositive, "product_weight_g"] = np.nan
    mapped_categories = set(translations["product_category_name"].dropna())
    unmapped_category = ~products["product_category_name"].isin(mapped_categories | {"unknown"})
    tracker.flag(
        "olist_products_dataset.csv", products, unmapped_category, "PRODUCT_CATEGORY_UNMAPPED",
        ["product_id"], "product_category_name", "add_unmapped_reference_row", "open",
    )
    extra_categories = sorted(set(products.loc[unmapped_category, "product_category_name"].dropna()))
    additions = [{
        "product_category_name": "unknown",
        "product_category_name_english": "unknown",
        "translation_status": "sentinel",
    }]
    additions.extend({
        "product_category_name": category,
        "product_category_name_english": pd.NA,
        "translation_status": "unmapped",
    } for category in extra_categories)
    translations = pd.concat([translations, pd.DataFrame(additions)], ignore_index=True)
    translations = translations.drop_duplicates("product_category_name", keep="first")
    tracker.record_transformation(
        "product_category_name_translation.csv", "add_unknown_and_unmapped_category_references", len(additions),
        "Menambahkan sentinel unknown dan referensi untuk kategori yang belum memiliki terjemahan resmi.",
    )
    for column in ["product_name_length", "product_description_length", "product_photos_qty"]:
        products[column] = products[column].round().astype("Int64")

    # Orders and event chronology.
    orders["order_id"] = normalize_text(orders["order_id"])
    orders["customer_id"] = normalize_text(orders["customer_id"])
    orders["order_status"] = normalize_text(orders["order_status"], lower=True)
    allowed_statuses = {
        "created", "approved", "invoiced", "processing", "shipped", "delivered",
        "unavailable", "canceled",
    }
    tracker.flag(
        "olist_orders_dataset.csv", orders, ~orders["order_status"].isin(allowed_statuses),
        "ORDER_STATUS_OUTSIDE_DOMAIN", ["order_id"], "order_status", "retain_and_quarantine", "quarantined",
    )
    order_date_columns = [
        "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date",
    ]
    parsed_order_dates = {}
    for column in order_date_columns:
        original = orders[column].copy()
        orders[column], bad = iso_datetime(original)
        parsed_order_dates[column] = pd.to_datetime(orders[column], errors="coerce")
        tracker.flag(
            "olist_orders_dataset.csv", orders.assign(**{f"_{column}_original": original}), bad,
            "ORDER_DATE_UNPARSEABLE", ["order_id"], column, "set_to_null_and_quarantine",
            "quarantined", original_column=f"_{column}_original",
        )
    tracker.record_transformation(
        "olist_orders_dataset.csv", "standardize_order_timestamps", len(orders),
        "Lima kolom waktu pesanan dinormalisasi ke format YYYY-MM-DD HH:MM:SS.",
    )
    approved_required = orders["order_status"].isin({"approved", "invoiced", "processing", "shipped", "delivered"})
    carrier_required = orders["order_status"].isin({"shipped", "delivered"})
    customer_delivery_required = orders["order_status"].eq("delivered")
    required_masks = {
        "order_approved_at": approved_required & parsed_order_dates["order_approved_at"].isna(),
        "order_delivered_carrier_date": carrier_required & parsed_order_dates["order_delivered_carrier_date"].isna(),
        "order_delivered_customer_date": customer_delivery_required & parsed_order_dates["order_delivered_customer_date"].isna(),
    }
    for column, mask in required_masks.items():
        tracker.flag(
            "olist_orders_dataset.csv", orders, mask, "ORDER_REQUIRED_DATE_MISSING",
            ["order_id"], column, "retain_and_quarantine", "quarantined",
        )
    carrier_before_approval = (
        parsed_order_dates["order_delivered_carrier_date"].notna()
        & parsed_order_dates["order_approved_at"].notna()
        & parsed_order_dates["order_delivered_carrier_date"].lt(parsed_order_dates["order_approved_at"])
    )
    tracker.flag(
        "olist_orders_dataset.csv", orders, carrier_before_approval, "ORDER_CARRIER_BEFORE_APPROVAL",
        ["order_id"], "order_delivered_carrier_date", "retain_and_flag", "open",
    )
    delivery_before_carrier = (
        parsed_order_dates["order_delivered_customer_date"].notna()
        & parsed_order_dates["order_delivered_carrier_date"].notna()
        & parsed_order_dates["order_delivered_customer_date"].lt(parsed_order_dates["order_delivered_carrier_date"])
    )
    tracker.flag(
        "olist_orders_dataset.csv", orders, delivery_before_carrier, "ORDER_DELIVERY_BEFORE_CARRIER",
        ["order_id"], "order_delivered_customer_date", "retain_and_quarantine", "quarantined",
    )
    canceled_with_delivery = orders["order_status"].eq("canceled") & parsed_order_dates[
        "order_delivered_customer_date"
    ].notna()
    tracker.flag(
        "olist_orders_dataset.csv", orders, canceled_with_delivery, "ORDER_CANCELED_WITH_DELIVERY",
        ["order_id"], "order_delivered_customer_date", "retain_and_flag", "open",
    )

    # Items.
    for column in ["order_id", "product_id", "seller_id"]:
        items[column] = normalize_text(items[column])
    items["order_item_id"] = pd.to_numeric(items["order_item_id"], errors="coerce").astype("Int64")
    original_shipping = items["shipping_limit_date"].copy()
    items["shipping_limit_date"], bad_shipping = iso_datetime(original_shipping)
    tracker.flag(
        "olist_order_items_dataset.csv", items.assign(_shipping_original=original_shipping), bad_shipping,
        "ITEM_DATE_UNPARSEABLE", ["order_id", "order_item_id"], "shipping_limit_date",
        "set_to_null_and_quarantine", "quarantined", original_column="_shipping_original",
    )
    items["price"] = pd.to_numeric(items["price"], errors="coerce")
    items["freight_value"] = pd.to_numeric(items["freight_value"], errors="coerce")
    negative_item_value = items["price"].lt(0) | items["freight_value"].lt(0)
    tracker.flag(
        "olist_order_items_dataset.csv", items, negative_item_value, "ITEM_VALUE_NEGATIVE",
        ["order_id", "order_item_id"], "price", "retain_and_quarantine", "quarantined",
    )
    items["line_total"] = items["price"] + items["freight_value"]
    tracker.record_transformation(
        "olist_order_items_dataset.csv", "add_line_total", len(items),
        "line_total dihitung sebagai price ditambah freight_value untuk rekonsiliasi pembayaran.",
    )

    # Payments.
    payments["order_id"] = normalize_text(payments["order_id"])
    payments["payment_sequential"] = pd.to_numeric(
        payments["payment_sequential"], errors="coerce"
    ).astype("Int64")
    payments["payment_type"] = normalize_text(payments["payment_type"], lower=True)
    payments["payment_installments"] = pd.to_numeric(
        payments["payment_installments"], errors="coerce"
    ).astype("Int64")
    payments["payment_value"] = pd.to_numeric(payments["payment_value"], errors="coerce")
    undefined_payment = payments["payment_type"].eq("not_defined")
    tracker.flag(
        "olist_order_payments_dataset.csv", payments, undefined_payment, "PAYMENT_TYPE_UNKNOWN",
        ["order_id", "payment_sequential"], "payment_type", "map_to_unknown", "corrected",
    )
    payments.loc[undefined_payment, "payment_type"] = "unknown"
    tracker.record_transformation(
        "olist_order_payments_dataset.csv", "map_undefined_payment_type_to_unknown", int(undefined_payment.sum()),
        "Nilai not_defined diganti sentinel eksplisit unknown.",
    )
    zero_installment = payments["payment_type"].eq("credit_card") & payments["payment_installments"].eq(0)
    tracker.flag(
        "olist_order_payments_dataset.csv", payments, zero_installment, "PAYMENT_INSTALLMENT_ZERO",
        ["order_id", "payment_sequential"], "payment_installments", "replace_zero_with_one", "corrected",
    )
    payments.loc[zero_installment, "payment_installments"] = 1
    tracker.record_transformation(
        "olist_order_payments_dataset.csv", "replace_zero_credit_card_installments_with_one", int(zero_installment.sum()),
        "Pembayaran kartu kredit dengan cicilan nol diperlakukan sebagai satu pembayaran.",
    )
    negative_payment = payments["payment_value"].lt(0)
    tracker.flag(
        "olist_order_payments_dataset.csv", payments, negative_payment, "PAYMENT_VALUE_NEGATIVE",
        ["order_id", "payment_sequential"], "payment_value", "retain_and_quarantine", "quarantined",
    )

    # Reviews: retain every unique review/order pair and add a globally unique composite key.
    reviews["review_id"] = normalize_text(reviews["review_id"])
    reviews["order_id"] = normalize_text(reviews["order_id"])
    reviews["review_key"] = reviews["review_id"] + ":" + reviews["order_id"]
    duplicate_review_id = reviews.duplicated("review_id", keep=False)
    tracker.flag(
        "olist_order_reviews_dataset.csv", reviews, duplicate_review_id, "REVIEW_DUPLICATE_ID_REKEYED",
        ["review_key"], "review_id", "use_review_key_as_primary_key", "corrected",
    )
    tracker.record_transformation(
        "olist_order_reviews_dataset.csv", "add_composite_review_key", int(duplicate_review_id.sum()),
        "review_key dibentuk dari review_id dan order_id agar setiap ulasan dapat diidentifikasi secara unik.",
    )
    reviews["review_score"] = pd.to_numeric(reviews["review_score"], errors="coerce").astype("Int64")
    bad_score = ~reviews["review_score"].between(1, 5)
    tracker.flag(
        "olist_order_reviews_dataset.csv", reviews, bad_score, "REVIEW_SCORE_OUTSIDE_DOMAIN",
        ["review_key"], "review_score", "retain_and_quarantine", "quarantined",
    )
    parsed_review_dates = {}
    for column in ["review_creation_date", "review_answer_timestamp"]:
        original = reviews[column].copy()
        reviews[column], bad = iso_datetime(original)
        parsed_review_dates[column] = pd.to_datetime(reviews[column], errors="coerce")
        tracker.flag(
            "olist_order_reviews_dataset.csv", reviews.assign(**{f"_{column}_original": original}), bad,
            "REVIEW_DATE_UNPARSEABLE", ["review_key"], column, "set_to_null_and_quarantine",
            "quarantined", original_column=f"_{column}_original",
        )
    answer_before_creation = parsed_review_dates["review_answer_timestamp"].lt(
        parsed_review_dates["review_creation_date"]
    )
    tracker.flag(
        "olist_order_reviews_dataset.csv", reviews, answer_before_creation,
        "REVIEW_ANSWER_BEFORE_CREATION", ["review_key"], "review_answer_timestamp",
        "retain_and_quarantine", "quarantined",
    )
    for column in ["review_comment_title", "review_comment_message"]:
        reviews[column] = normalize_text(reviews[column])

    # Cross-table checks and reconciliation.
    item_order_ids = set(items["order_id"].dropna())
    payment_order_ids = set(payments["order_id"].dropna())
    active_without_items = (
        ~orders["order_id"].isin(item_order_ids)
        & ~orders["order_status"].isin({"unavailable", "canceled", "created"})
    )
    tracker.flag(
        "olist_orders_dataset.csv", orders, active_without_items, "ORDER_WITHOUT_ITEMS",
        ["order_id"], "order_id", "retain_and_quarantine", "quarantined",
    )
    without_payment = ~orders["order_id"].isin(payment_order_ids)
    tracker.flag(
        "olist_orders_dataset.csv", orders, without_payment, "ORDER_WITHOUT_PAYMENT",
        ["order_id"], "order_id", "retain_and_flag", "open",
    )
    item_totals = items.groupby("order_id", as_index=False)["line_total"].sum().rename(
        columns={"line_total": "calculated_order_total"}
    )
    payment_totals = payments.groupby("order_id", as_index=False)["payment_value"].sum().rename(
        columns={"payment_value": "recorded_payment_total"}
    )
    order_recon = item_totals.merge(payment_totals, on="order_id", how="inner")
    order_recon["payment_difference"] = (
        order_recon["recorded_payment_total"] - order_recon["calculated_order_total"]
    )
    orders = orders.merge(order_recon, on="order_id", how="left")
    payment_mismatch = orders["payment_difference"].abs().gt(0.02)
    tracker.flag(
        "olist_orders_dataset.csv", orders, payment_mismatch, "ORDER_PAYMENT_TOTAL_MISMATCH",
        ["order_id"], "payment_difference", "retain_and_flag", "open",
        detail="Toleransi rekonsiliasi ditetapkan sebesar 0,02 dalam mata uang sumber.",
    )

    # Attach row-level quality status after all rules have run.
    cleaned = {
        "olist_customers_dataset.csv": tracker.attach_status("olist_customers_dataset.csv", customers),
        "olist_sellers_dataset.csv": tracker.attach_status("olist_sellers_dataset.csv", sellers),
        "olist_products_dataset.csv": tracker.attach_status("olist_products_dataset.csv", products),
        "product_category_name_translation.csv": translations.assign(dq_status="valid", dq_issue_codes=""),
        "olist_orders_dataset.csv": tracker.attach_status("olist_orders_dataset.csv", orders),
        "olist_order_items_dataset.csv": tracker.attach_status("olist_order_items_dataset.csv", items),
        "olist_order_payments_dataset.csv": tracker.attach_status("olist_order_payments_dataset.csv", payments),
        "olist_order_reviews_dataset.csv": tracker.attach_status("olist_order_reviews_dataset.csv", reviews),
        "olist_geolocation_dataset.csv": canonical_geo,
    }

    # Write cleaned tables and error quarantines. Quarantine rows remain in clean outputs
    # with dq_status=error to preserve relationships and are duplicated here for review.
    table_profiles = []
    for table, clean_df in cleaned.items():
        write_csv(clean_df, clean_dir / table)
        counts = clean_df["dq_status"].value_counts().to_dict() if "dq_status" in clean_df else {}
        table_profiles.append({
            "table": table,
            "raw_rows": int(raw_counts.get(table, 0)),
            "clean_rows": int(len(clean_df)),
            "valid_rows": int(counts.get("valid", 0)),
            "corrected_rows": int(counts.get("corrected", 0)),
            "warning_rows": int(counts.get("warning", 0)),
            "error_rows": int(counts.get("error", 0)),
            "raw_exact_duplicate_rows": int(raw[table].duplicated().sum()),
            "clean_exact_duplicate_rows": int(clean_df.duplicated().sum()),
        })
        if table != "olist_geolocation_dataset.csv" and "dq_status" in clean_df:
            quarantine = clean_df.loc[clean_df["dq_status"].eq("error")]
            if not quarantine.empty:
                write_csv(quarantine, quarantine_dir / table)

    issues_df = pd.DataFrame(tracker.issues)
    if issues_df.empty:
        issues_df = pd.DataFrame(columns=[
            "table", "record_key", "rule_id", "dimension", "severity", "column",
            "original_value", "action", "disposition", "detail",
        ])
    rule_results = tracker.rule_results()
    profile_df = pd.DataFrame(table_profiles)
    transformations_df = pd.DataFrame(tracker.transformations)
    dictionary_df = build_dictionary(cleaned)

    source_rows = []
    for name in CSV_FILES:
        source_path = raw_dir / name
        source_rows.append({
            "source_file": name,
            "sha256": sha256_file(source_path),
            "raw_rows": int(raw_counts[name]),
            "processed_at_utc": processed_at,
        })
    sources_df = pd.DataFrame(source_rows)

    write_csv(issues_df, metadata_dir / "quality_issues.csv")
    write_csv(rule_results, metadata_dir / "quality_rule_results.csv")
    write_csv(profile_df, metadata_dir / "table_profile.csv")
    write_csv(transformations_df, metadata_dir / "transformation_log.csv")
    write_csv(dictionary_df, metadata_dir / "data_dictionary.csv")
    write_csv(sources_df, metadata_dir / "sources.csv")

    dimension_summary = (
        issues_df.groupby(["dimension", "severity"], as_index=False)
        .size()
        .rename(columns={"size": "issue_count"})
        .sort_values(["issue_count", "dimension"], ascending=[False, True])
    )
    write_csv(dimension_summary, metadata_dir / "dimension_summary.csv")

    summary = {
        "processed_at_utc": processed_at,
        "source_zip": str(source_zip),
        "source_zip_sha256": sha256_file(source_zip),
        "output_dir": str(output_dir),
        "raw_total_rows": int(sum(raw_counts.values())),
        "clean_total_rows": int(sum(len(df) for df in cleaned.values())),
        "quality_issue_rows": int(len(issues_df)),
        "open_issue_rows": int(issues_df["disposition"].eq("open").sum()),
        "corrected_issue_rows": int(issues_df["disposition"].eq("corrected").sum()),
        "quarantined_issue_rows": int(issues_df["disposition"].eq("quarantined").sum()),
        "tables": table_profiles,
    }
    (metadata_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Final manifest after every CSV exists.
    manifest_files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            manifest_files.append({
                "relative_path": str(path.relative_to(output_dir)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    manifest = {
        "dataset": "Olist OLTP data quality output",
        "processed_at_utc": processed_at,
        "source_zip_sha256": summary["source_zip_sha256"],
        "files": manifest_files,
    }
    (metadata_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
