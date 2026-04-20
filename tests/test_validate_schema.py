import csv
import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


def load_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_schema.py"
    spec = importlib.util.spec_from_file_location("validate_schema", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestValidateSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = load_module()

    def write_csv(self, path: Path, fieldnames, rows):
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_check_required_columns_empty_rows(self):
        errors = self.mod.check_required_columns(Path("dummy.csv"), [], {"match_key"})
        self.assertEqual(errors, ["dummy.csv: file is empty or has no header row"])

    def test_validate_lookup_reports_format_duplicates_and_bad_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lookup.csv"
            self.write_csv(
                path,
                ["match_key", "normalized_type", "category", "tag1", "tag2", "tag3"],
                [
                    {"match_key": "AA", "normalized_type": "Type A", "category": "Trainer", "tag1": "", "tag2": "", "tag3": ""},
                    {"match_key": "A@", "normalized_type": "Type B", "category": "Trainer", "tag1": "", "tag2": "", "tag3": ""},
                    {"match_key": "AA", "normalized_type": "Type C", "category": "Invalid Category", "tag1": "", "tag2": "", "tag3": ""},
                ],
            )
            errors = self.mod.validate_lookup(path)

        self.assertTrue(any("invalid match_key format 'A@'" in e for e in errors))
        self.assertTrue(any("duplicate match_key 'AA'" in e for e in errors))
        self.assertTrue(any("unrecognised category 'Invalid Category'" in e for e in errors))

    def test_validate_aliases_normalizes_case_and_detects_duplicate_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aliases.csv"
            self.write_csv(
                path,
                ["raw_value", "match_key"],
                [
                    {"raw_value": "Boeing 737", "match_key": "b738"},
                    {"raw_value": " boeing 737 ", "match_key": "B738"},
                    {"raw_value": "", "match_key": "A320"},
                    {"raw_value": "Airbus", "match_key": "A@"},
                ],
            )
            errors = self.mod.validate_aliases(path)

        self.assertTrue(any("duplicate alias pair ('boeing 737', 'B738')" in e for e in errors))
        self.assertTrue(any("empty raw_value" in e for e in errors))
        self.assertTrue(any("invalid match_key format 'A@'" in e for e in errors))

    def test_validate_data_file_reports_duplicate_icao_and_category_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            self.write_csv(
                path,
                ["$ICAO", "$Registration", "$Operator", "$Type", "$ICAO Type", "#CMPG", "Category"],
                [
                    {"$ICAO": "ABC123", "$Registration": "N1", "$Operator": "Op", "$Type": "Type", "$ICAO Type": "A320", "#CMPG": "Civ", "Category": "Trainer"},
                    {"$ICAO": "ABC123", "$Registration": "N2", "$Operator": "Op", "$Type": "Type", "$ICAO Type": "A320", "#CMPG": "Civ", "Category": "Not Real"},
                    {"$ICAO": "DEF456", "$Registration": "N3", "$Operator": "Op", "$Type": "Type", "$ICAO Type": "A320", "#CMPG": "Civ", "Category": "Also Bad"},
                ],
            )
            errors = self.mod.validate_data_file(path)

        self.assertTrue(any("duplicate $ICAO 'ABC123'" in e for e in errors))
        self.assertTrue(any("2 row(s) with unrecognised Category values" in e for e in errors))

    def test_main_treats_category_errors_as_warnings_without_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lookup = tmp_path / "lookup.csv"
            aliases = tmp_path / "aliases.csv"
            data = tmp_path / "data.csv"

            self.write_csv(
                lookup,
                ["match_key", "normalized_type", "category", "tag1", "tag2", "tag3"],
                [{"match_key": "A320", "normalized_type": "A320", "category": "Trainer", "tag1": "", "tag2": "", "tag3": ""}],
            )
            self.write_csv(
                aliases,
                ["raw_value", "match_key"],
                [{"raw_value": "airbus a320", "match_key": "A320"}],
            )
            self.write_csv(
                data,
                ["$ICAO", "$Registration", "$Operator", "$Type", "$ICAO Type", "#CMPG", "Category"],
                [{"$ICAO": "ABC123", "$Registration": "N1", "$Operator": "Op", "$Type": "Type", "$ICAO Type": "A320", "#CMPG": "Civ", "Category": "Invalid"}],
            )

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result_non_strict = self.mod.main(["--lookup", str(lookup), "--aliases", str(aliases), "--data-files", str(data)])
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result_strict = self.mod.main(["--lookup", str(lookup), "--aliases", str(aliases), "--data-files", str(data), "--strict"])

        self.assertEqual(result_non_strict, 0)
        self.assertEqual(result_strict, 1)


if __name__ == "__main__":
    unittest.main()
