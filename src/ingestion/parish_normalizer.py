"""
Parish Tax Roll Normalizer - Universal column mapping for Louisiana parishes.

This module provides auto-detection and normalization of tax roll data from
any Louisiana parish, regardless of column naming conventions.
"""
from __future__ import annotations

import re
import csv
import io
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, BinaryIO
from dataclasses import dataclass, field

import pandas as pd

from core.logging_config import get_logger

LOGGER = get_logger(__name__)


# Standard output column names
class StandardColumns:
    """Standard normalized column names."""
    PARCEL_ID = "parcel_id"
    OWNER_NAME = "owner_name"
    MAILING_ADDRESS = "mailing_address"
    MAILING_CITY = "mailing_city"
    MAILING_STATE = "mailing_state"
    MAILING_ZIP = "mailing_zip"
    SITUS_ADDRESS = "situs_address"
    SITUS_CITY = "situs_city"
    SITUS_STATE = "situs_state"
    SITUS_ZIP = "situs_zip"
    ACRES = "acres"
    ASSESSED_VALUE = "assessed_value"
    LAND_VALUE = "land_value"
    IMPROVEMENT_VALUE = "improvement_value"
    PARISH_NAME = "parish_name"
    PHONE = "phone"
    EMAIL = "email"
    LEGAL_DESCRIPTION = "legal_description"
    SUBDIVISION = "subdivision"
    WARD = "ward"
    ZONING = "zoning"


# Column name patterns for auto-detection (regex patterns)
COLUMN_PATTERNS: Dict[str, List[str]] = {
    StandardColumns.PARCEL_ID: [
        r"parcel.*(?:id|num|no|#|number)",
        r"(?:parcel|prop).*(?:number|id)",
        r"^parcel$",
        r"^parcel.number$",
        r"^parcel.num$",
        r"^apn$",
        r"assessor.*parcel",
        r"tax.*(?:id|number)",
        r"property.*(?:id|key)",
        r"pin",
        r"^pid$",
    ],
    StandardColumns.OWNER_NAME: [
        r"owner.*name",
        r"property.*owner",
        r"^owner$",
        r"owner.*1",
        r"taxpayer.*name",
        r"grantor",
        r"name.*owner",
    ],
    StandardColumns.MAILING_ADDRESS: [
        r"mail.*(?:addr|street)",
        r"(?:owner|taxpayer).*addr",
        r"billing.*addr",
        r"^mailing$",
        r"mail.*line.*1",
    ],
    StandardColumns.MAILING_CITY: [
        r"mail.*city",
        r"(?:owner|taxpayer).*city",
        r"billing.*city",
    ],
    StandardColumns.MAILING_STATE: [
        r"mail.*state",
        r"(?:owner|taxpayer).*state",
        r"billing.*state",
    ],
    StandardColumns.MAILING_ZIP: [
        r"mail.*zip",
        r"(?:owner|taxpayer).*zip",
        r"billing.*zip",
        r"mail.*postal",
    ],
    StandardColumns.SITUS_ADDRESS: [
        r"situs.*addr",
        r"property.*addr",
        r"physical.*addr",
        r"location.*addr",
        r"street.*addr",
        r"^situs$",
        r"site.*addr",
    ],
    StandardColumns.SITUS_CITY: [
        r"situs.*city",
        r"property.*city",
        r"physical.*city",
    ],
    StandardColumns.SITUS_STATE: [
        r"situs.*state",
        r"property.*state",
    ],
    StandardColumns.SITUS_ZIP: [
        r"situs.*zip",
        r"property.*zip",
        r"physical.*zip",
    ],
    StandardColumns.ACRES: [
        r"acre",
        r"lot.*size",
        r"land.*area",
        r"area.*acres",
        r"^acres$",
        r"acreage",
        r"total.*acres",
    ],
    StandardColumns.ASSESSED_VALUE: [
        r"assess.*(?:value|val)",
        r"total.*(?:value|val)",
        r"(?:tax|taxable).*(?:value|val)",
        r"fair.*market",
    ],
    StandardColumns.LAND_VALUE: [
        r"land.*(?:value|val)",
        r"lot.*(?:value|val)",
    ],
    StandardColumns.IMPROVEMENT_VALUE: [
        r"improv.*(?:value|val)",
        r"building.*(?:value|val)",
        r"structure.*(?:value|val)",
    ],
    StandardColumns.PHONE: [
        r"phone",
        r"telephone",
        r"contact.*num",
        r"cell",
        r"mobile",
    ],
    StandardColumns.EMAIL: [
        r"email",
        r"e-mail",
        r"mail.*addr.*@",
    ],
    StandardColumns.LEGAL_DESCRIPTION: [
        r"legal.*desc",
        r"^legal$",
        r"description",
    ],
    StandardColumns.SUBDIVISION: [
        r"subdiv",
        r"^sub$",
        r"plat.*name",
    ],
    StandardColumns.WARD: [
        r"ward",
        r"district",
        r"^wd$",
    ],
    StandardColumns.ZONING: [
        r"zoning",
        r"zone.*code",
        r"land.*use",
    ],
}


@dataclass
class ParishNormalizerResult:
    """Result of parish data normalization."""
    
    df: pd.DataFrame
    column_mapping: Dict[str, str]  # original -> standard
    parish_name: Optional[str] = None
    rows_total: int = 0
    rows_valid: int = 0
    rows_skipped: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "parish_name": self.parish_name,
            "rows_total": self.rows_total,
            "rows_valid": self.rows_valid,
            "rows_skipped": self.rows_skipped,
            "column_mapping": self.column_mapping,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class ParishNormalizer:
    """
    Universal normalizer for Louisiana parish tax roll data.
    
    Handles CSV, XLSX, and ZIP files with auto-detection of:
    - File format and delimiter
    - Column mappings
    - Parish identification
    """
    
    # Louisiana parish names for auto-detection
    LA_PARISHES = [
        "Acadia", "Allen", "Ascension", "Assumption", "Avoyelles",
        "Beauregard", "Bienville", "Bossier", "Caddo", "Calcasieu",
        "Caldwell", "Cameron", "Catahoula", "Claiborne", "Concordia",
        "DeSoto", "East Baton Rouge", "East Carroll", "East Feliciana",
        "Evangeline", "Franklin", "Grant", "Iberia", "Iberville",
        "Jackson", "Jefferson", "Jefferson Davis", "Lafayette", "Lafourche",
        "LaSalle", "Lincoln", "Livingston", "Madison", "Morehouse",
        "Natchitoches", "Orleans", "Ouachita", "Plaquemines", "Pointe Coupee",
        "Rapides", "Red River", "Richland", "Sabine", "St. Bernard",
        "St. Charles", "St. Helena", "St. James", "St. John the Baptist",
        "St. Landry", "St. Martin", "St. Mary", "St. Tammany", "Tangipahoa",
        "Tensas", "Terrebonne", "Union", "Vermilion", "Vernon", "Washington",
        "Webster", "West Baton Rouge", "West Carroll", "West Feliciana", "Winn"
    ]
    
    def __init__(self, parish_override: Optional[str] = None):
        """
        Initialize normalizer.
        
        Args:
            parish_override: Force a specific parish name instead of auto-detecting.
        """
        self.parish_override = parish_override
    
    def normalize_file(
        self, 
        file_path: Path | str,
        encoding: str = "utf-8"
    ) -> ParishNormalizerResult:
        """
        Normalize a tax roll file.
        
        Args:
            file_path: Path to CSV, XLSX, or ZIP file.
            encoding: File encoding (default utf-8).
        
        Returns:
            ParishNormalizerResult with normalized DataFrame.
        """
        path = Path(file_path)
        
        if not path.exists():
            return ParishNormalizerResult(
                df=pd.DataFrame(),
                column_mapping={},
                errors=[f"File not found: {path}"],
            )
        
        suffix = path.suffix.lower()
        
        try:
            if suffix == ".zip":
                return self._normalize_zip(path, encoding)
            elif suffix == ".xlsx" or suffix == ".xls":
                return self._normalize_excel(path)
            else:
                # Assume CSV or similar delimited format
                return self._normalize_csv(path, encoding)
        except Exception as e:
            LOGGER.exception(f"Failed to normalize file: {path}")
            return ParishNormalizerResult(
                df=pd.DataFrame(),
                column_mapping={},
                errors=[f"Failed to process file: {str(e)}"],
            )
    
    def normalize_dataframe(
        self,
        df: pd.DataFrame,
        parish_name: Optional[str] = None,
    ) -> ParishNormalizerResult:
        """
        Normalize an already-loaded DataFrame.
        
        Args:
            df: DataFrame to normalize.
            parish_name: Optional parish name.
        
        Returns:
            ParishNormalizerResult with normalized DataFrame.
        """
        result = ParishNormalizerResult(
            df=pd.DataFrame(),
            column_mapping={},
            rows_total=len(df),
            parish_name=self.parish_override or parish_name,
        )
        
        # Auto-detect column mapping
        column_mapping = self._auto_detect_columns(df.columns.tolist())
        result.column_mapping = column_mapping
        
        # Check for required columns
        if StandardColumns.PARCEL_ID not in column_mapping.values():
            result.warnings.append("Could not detect parcel ID column - will generate placeholder IDs")
        
        if StandardColumns.OWNER_NAME not in column_mapping.values():
            result.warnings.append("Could not detect owner name column")
        
        # Build normalized DataFrame
        normalized_df = pd.DataFrame()
        
        # Reverse mapping: standard -> original
        reverse_map = {v: k for k, v in column_mapping.items()}
        
        # Copy mapped columns
        for std_col in vars(StandardColumns).values():
            if isinstance(std_col, str) and not std_col.startswith("_"):
                orig_col = reverse_map.get(std_col)
                if orig_col and orig_col in df.columns:
                    normalized_df[std_col] = df[orig_col]
                else:
                    normalized_df[std_col] = None
        
        # Auto-detect parish from data if not provided
        if not result.parish_name:
            result.parish_name = self._detect_parish(df, column_mapping)
        
        # Set parish name column
        if result.parish_name:
            normalized_df[StandardColumns.PARISH_NAME] = result.parish_name
        
        # Clean and validate data
        normalized_df = self._clean_data(normalized_df)
        
        # Count valid rows (must have parcel_id)
        if StandardColumns.PARCEL_ID in normalized_df.columns:
            valid_mask = normalized_df[StandardColumns.PARCEL_ID].notna() & \
                        (normalized_df[StandardColumns.PARCEL_ID] != "")
            result.rows_valid = valid_mask.sum()
            result.rows_skipped = result.rows_total - result.rows_valid
        else:
            result.rows_valid = result.rows_total
        
        result.df = normalized_df
        return result
    
    def _normalize_csv(
        self, 
        path: Path, 
        encoding: str = "utf-8"
    ) -> ParishNormalizerResult:
        """Normalize a CSV file with auto-delimiter detection."""
        # Try to detect delimiter
        delimiter = self._detect_delimiter(path, encoding)
        
        try:
            df = pd.read_csv(
                path,
                delimiter=delimiter,
                encoding=encoding,
                low_memory=False,
                on_bad_lines="warn",
            )
        except UnicodeDecodeError:
            # Try latin-1 encoding as fallback
            LOGGER.warning(f"UTF-8 failed, trying latin-1 encoding for {path}")
            df = pd.read_csv(
                path,
                delimiter=delimiter,
                encoding="latin-1",
                low_memory=False,
                on_bad_lines="warn",
            )
        
        return self.normalize_dataframe(df, parish_name=self._guess_parish_from_filename(path))
    
    def _normalize_excel(self, path: Path) -> ParishNormalizerResult:
        """Normalize an Excel file."""
        df = pd.read_excel(path, engine="openpyxl")
        return self.normalize_dataframe(df, parish_name=self._guess_parish_from_filename(path))
    
    def _normalize_zip(
        self, 
        path: Path, 
        encoding: str = "utf-8"
    ) -> ParishNormalizerResult:
        """Normalize a ZIP file containing CSV/Excel files."""
        with zipfile.ZipFile(path, "r") as zf:
            # Find data files in ZIP
            data_files = [
                f for f in zf.namelist()
                if f.lower().endswith((".csv", ".xlsx", ".xls"))
                and not f.startswith("__MACOSX")
                and not f.startswith(".")
            ]
            
            if not data_files:
                return ParishNormalizerResult(
                    df=pd.DataFrame(),
                    column_mapping={},
                    errors=["No CSV or Excel files found in ZIP"],
                )
            
            # Use the first (or largest) data file
            data_file = data_files[0]
            LOGGER.info(f"Processing {data_file} from ZIP archive")
            
            with zf.open(data_file) as f:
                if data_file.lower().endswith(".csv"):
                    content = f.read()
                    try:
                        text = content.decode(encoding)
                    except UnicodeDecodeError:
                        text = content.decode("latin-1")
                    
                    # Detect delimiter
                    delimiter = self._detect_delimiter_from_text(text[:4096])
                    df = pd.read_csv(
                        io.StringIO(text),
                        delimiter=delimiter,
                        low_memory=False,
                        on_bad_lines="warn",
                    )
                else:
                    df = pd.read_excel(io.BytesIO(f.read()), engine="openpyxl")
            
            return self.normalize_dataframe(df, parish_name=self._guess_parish_from_filename(path))
    
    def _detect_delimiter(self, path: Path, encoding: str = "utf-8") -> str:
        """Detect CSV delimiter by sampling the file."""
        try:
            with open(path, "r", encoding=encoding) as f:
                sample = f.read(4096)
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                sample = f.read(4096)
        
        return self._detect_delimiter_from_text(sample)
    
    def _detect_delimiter_from_text(self, text: str) -> str:
        """Detect delimiter from text sample."""
        # Common delimiters to check
        delimiters = [",", "\t", "|", ";"]
        
        # Count occurrences in first few lines
        lines = text.split("\n")[:5]
        
        best_delimiter = ","
        best_consistency = 0
        
        for delim in delimiters:
            counts = [line.count(delim) for line in lines if line.strip()]
            if counts:
                # Check if count is consistent across lines
                if len(set(counts)) == 1 and counts[0] > 0:
                    if counts[0] > best_consistency:
                        best_consistency = counts[0]
                        best_delimiter = delim
        
        return best_delimiter
    
    def _auto_detect_columns(self, columns: List[str]) -> Dict[str, str]:
        """
        Auto-detect column mappings based on patterns.
        
        Args:
            columns: List of original column names.
        
        Returns:
            Dict mapping original column names to standard names.
        """
        mapping: Dict[str, str] = {}
        used_standards: set = set()
        
        # Normalize column names for matching
        col_lower = {col: col.lower().replace("_", " ").replace("-", " ") for col in columns}
        
        for std_col, patterns in COLUMN_PATTERNS.items():
            if std_col in used_standards:
                continue
            
            for col, col_norm in col_lower.items():
                if col in mapping:
                    continue
                
                for pattern in patterns:
                    if re.search(pattern, col_norm, re.IGNORECASE):
                        mapping[col] = std_col
                        used_standards.add(std_col)
                        break
                
                if std_col in used_standards:
                    break
        
        LOGGER.info(f"Auto-detected {len(mapping)} column mappings")
        return mapping
    
    def _detect_parish(
        self, 
        df: pd.DataFrame, 
        column_mapping: Dict[str, str]
    ) -> Optional[str]:
        """Try to detect parish name from data."""
        # Check if there's a parish column
        parish_col = None
        for col in df.columns:
            if "parish" in col.lower():
                parish_col = col
                break
        
        if parish_col and not df[parish_col].isna().all():
            # Get most common value
            parish = df[parish_col].mode().iloc[0] if len(df[parish_col].mode()) > 0 else None
            if parish:
                return str(parish).strip()
        
        return None
    
    def _guess_parish_from_filename(self, path: Path) -> Optional[str]:
        """Try to guess parish from filename."""
        filename = path.stem.lower()
        
        for parish in self.LA_PARISHES:
            # Check for parish name in filename
            parish_lower = parish.lower().replace(" ", "").replace(".", "")
            filename_clean = filename.replace("_", "").replace("-", "")
            
            if parish_lower in filename_clean:
                return parish
        
        # Check for common abbreviations
        abbrev_map = {
            "ebr": "East Baton Rouge",
            "wbr": "West Baton Rouge",
            "orl": "Orleans",
            "jef": "Jefferson",
            "cad": "Caddo",
            "rap": "Rapides",
            "cal": "Calcasieu",
            "laf": "Lafayette",
            "oua": "Ouachita",
            "tan": "Tangipahoa",
            "ter": "Terrebonne",
            "laf": "Lafourche",
            "stm": "St. Mary",
            "stt": "St. Tammany",
            "stl": "St. Landry",
            "stb": "St. Bernard",
            "stc": "St. Charles",
        }
        
        for abbrev, parish in abbrev_map.items():
            if abbrev in filename:
                return parish
        
        return None
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and standardize data values."""
        # Clean string columns
        string_cols = [
            StandardColumns.PARCEL_ID,
            StandardColumns.OWNER_NAME,
            StandardColumns.MAILING_ADDRESS,
            StandardColumns.MAILING_CITY,
            StandardColumns.MAILING_STATE,
            StandardColumns.MAILING_ZIP,
            StandardColumns.SITUS_ADDRESS,
            StandardColumns.SITUS_CITY,
            StandardColumns.SITUS_STATE,
            StandardColumns.SITUS_ZIP,
            StandardColumns.PHONE,
            StandardColumns.EMAIL,
        ]
        
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace(["nan", "None", ""], pd.NA)
        
        # Clean numeric columns
        numeric_cols = [
            StandardColumns.ACRES,
            StandardColumns.ASSESSED_VALUE,
            StandardColumns.LAND_VALUE,
            StandardColumns.IMPROVEMENT_VALUE,
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = self._parse_numeric(df[col])
        
        # Standardize state to LA if empty
        if StandardColumns.MAILING_STATE in df.columns:
            df[StandardColumns.MAILING_STATE] = df[StandardColumns.MAILING_STATE].fillna("LA")
        
        if StandardColumns.SITUS_STATE in df.columns:
            df[StandardColumns.SITUS_STATE] = df[StandardColumns.SITUS_STATE].fillna("LA")
        
        return df
    
    def _parse_numeric(self, series: pd.Series) -> pd.Series:
        """Parse numeric values, handling currency formatting."""
        def clean_value(val):
            if pd.isna(val) or val == "" or str(val).lower() in ["nan", "none"]:
                return None
            try:
                # Remove currency symbols and commas
                clean = str(val).replace("$", "").replace(",", "").strip()
                return float(clean)
            except (ValueError, TypeError):
                return None
        
        return series.apply(clean_value)


__all__ = ["ParishNormalizer", "ParishNormalizerResult", "StandardColumns"]

