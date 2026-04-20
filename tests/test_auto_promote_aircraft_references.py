import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "auto_promote_aircraft_references.py"
    spec = importlib.util.spec_from_file_location("auto_promote_aircraft_references", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAutoPromoteAircraftReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = load_module()

    def test_lookup_confidence_high_signal_path(self):
        score, reasons = self.mod.lookup_confidence(
            {
                "match_key": " a320 ",
                "normalized_type": "Airbus A320",
                "validation_status": "validated",
                "validation_reason": "exact_model_match",
                "public_model_count": "2",
                "public_source_count": "4",
            }
        )
        self.assertEqual(score, 1.0)
        self.assertIn("valid_match_key", reasons)
        self.assertIn("exact_model_match", reasons)
        self.assertIn("multi_source_support", reasons)

    def test_lookup_confidence_handles_invalid_numbers(self):
        score, reasons = self.mod.lookup_confidence(
            {
                "match_key": "B738",
                "normalized_type": "Boeing 737-800",
                "validation_status": "validated",
                "validation_reason": "match_key_present",
                "public_model_count": "unknown",
                "public_source_count": "also-unknown",
            }
        )
        self.assertAlmostEqual(score, 0.7)
        self.assertNotIn("public_model_seen", reasons)
        self.assertNotIn("multi_source_support", reasons)

    def test_alias_confidence_collision_penalty_and_floor(self):
        score, reasons = self.mod.alias_confidence(
            {
                "raw_value": "Boeing 737",
                "match_key": "B738",
                "validation_status": "validated",
                "validation_reason": "alias_supported",
                "public_collision_count": "7",
            }
        )
        self.assertAlmostEqual(score, 0.45)
        self.assertIn("collision_penalty", reasons)

        low_score, _ = self.mod.alias_confidence(
            {"raw_value": "x", "match_key": "A1", "public_collision_count": "50"}
        )
        self.assertAlmostEqual(low_score, 0.0)

    def test_merge_lookup_promotes_and_skips_expected_rows(self):
        existing = {"A320": {"match_key": "A320", "normalized_type": "A320", "category": "Trainer", "tag1": "", "tag2": "", "tag3": ""}}
        reviewed = [
            {"match_key": "", "normalized_type": "No Key"},
            {"match_key": "A320", "normalized_type": "Duplicate", "validation_status": "validated", "validation_reason": "exact_model_match"},
            {"match_key": "B738", "normalized_type": "B737-800", "validation_status": "validated", "validation_reason": "exact_model_match", "public_model_count": "1", "public_source_count": "2"},
            {"match_key": "C172", "normalized_type": "Skyhawk", "validation_status": "pending", "validation_reason": "match_key_present"},
        ]
        final_rows, promoted, skipped = self.mod.merge_lookup(existing, reviewed, threshold=0.8)

        self.assertEqual([row["match_key"] for row in final_rows], ["A320", "B738"])
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]["match_key"], "B738")
        self.assertEqual(len(skipped), 3)
        self.assertEqual(skipped[0]["promotion_reason"], "missing_match_key")
        self.assertEqual(skipped[1]["promotion_reason"], "already_exists")
        self.assertEqual(skipped[2]["promotion_reason"], "below_threshold")

    def test_merge_aliases_deduplicates_using_normalized_pair(self):
        existing = {("boeing 737", "B738"): {"raw_value": "boeing 737", "match_key": "B738"}}
        reviewed = [
            {"raw_value": " Boeing 737 ", "match_key": " b738 ", "validation_status": "validated", "validation_reason": "exact_alias_unique_match", "public_collision_count": "1"},
            {"raw_value": "Airbus A320", "match_key": "A320", "validation_status": "validated", "validation_reason": "exact_alias_unique_match", "public_collision_count": "1"},
            {"raw_value": "", "match_key": "A319"},
        ]

        final_rows, promoted, skipped = self.mod.merge_aliases(existing, reviewed, threshold=0.75)
        self.assertEqual(final_rows, [{"raw_value": "airbus a320", "match_key": "A320"}, {"raw_value": "boeing 737", "match_key": "B738"}])
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]["raw_value"], "airbus a320")
        self.assertEqual([s["promotion_reason"] for s in skipped], ["already_exists", "missing_alias_or_match_key"])

    def test_load_lookup_and_alias_maps_normalize_input_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lookup_file = tmp_path / "lookup.csv"
            alias_file = tmp_path / "aliases.csv"

            with lookup_file.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["match_key", "normalized_type", "category"])
                writer.writeheader()
                writer.writerow({"match_key": " a320 ", "normalized_type": " Airbus  A320 ", "category": " Trainer "})

            with alias_file.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["raw_value", "match_key"])
                writer.writeheader()
                writer.writerow({"raw_value": " Airbus A320 ", "match_key": " a320 "})

            lookup = self.mod.load_lookup_map(lookup_file)
            aliases = self.mod.load_alias_map(alias_file)

        self.assertIn("A320", lookup)
        self.assertEqual(lookup["A320"]["normalized_type"], "Airbus A320")
        self.assertIn(("airbus a320", "A320"), aliases)


if __name__ == "__main__":
    unittest.main()
