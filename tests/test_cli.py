import csv
import tempfile
import unittest
from pathlib import Path

from icp_engine.cli import main


class CLITests(unittest.TestCase):
    def test_cli_no_fetch_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "companies.csv"
            input_path.write_text(
                "company,domain,category,founded_year,employee_count,hq,notes\n"
                "Automate Like,example.com,dealership management software,1980,150,ZA,"
                "\"B2B software platform with inventory transactions reporting workflow API integrations.\"\n",
                encoding="utf-8",
            )
            out_dir = tmp_path / "out"

            code = main(["qualify", "--input", str(input_path), "--out", str(out_dir), "--no-fetch"])

            self.assertEqual(code, 0)
            ranked = out_dir / "ranked_companies.csv"
            dossier = out_dir / "dossier.md"
            self.assertTrue(ranked.exists())
            self.assertTrue(dossier.exists())
            with ranked.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["company"], "Automate Like")
            self.assertIn("Automate Like", dossier.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
