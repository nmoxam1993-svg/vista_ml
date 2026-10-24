"""Run with: python -m unittest discover -s tests  (from quickbooks/)"""

import json
import tempfile
import unittest
from pathlib import Path

from vista_qb import analysis as A
from vista_qb.__main__ import run
from vista_qb.io import detect_datasets, load_csv, parse_amount

FIX = Path(__file__).parent / "fixtures"


class TestIO(unittest.TestCase):
    def test_parse_amount_formats(self):
        self.assertEqual(parse_amount("$1,234.56"), 1234.56)
        self.assertEqual(parse_amount("(1,500.00)"), -1500.0)
        self.assertEqual(parse_amount("-20"), -20.0)
        self.assertIsNone(parse_amount(""))
        self.assertIsNone(parse_amount("Rent"))

    def test_header_detection_skips_qbo_title_rows(self):
        t = load_csv(FIX / "coa.csv")
        self.assertEqual(t.headers[0], "Full name")
        self.assertEqual(t.rows[0]["Full name"], "Checking")
        self.assertEqual(t.rows[0]["_line"], 4)  # cites the real file line

    def test_detect_datasets(self):
        found = detect_datasets(FIX)
        for key in ("coa", "pl", "items", "vendor_spend", "customers"):
            self.assertIn(key, found)


class TestModule1(unittest.TestCase):
    def setUp(self):
        self.lines = A.parse_pl(load_csv(FIX / "pl_12months.csv"))

    def test_pl_parse_sections_and_parents(self):
        rent = next(l for l in self.lines if l.name == "Rent")
        self.assertEqual(rent.section, "expense")
        self.assertEqual(rent.parent, "Office Expenses")
        t = A.pl_totals(self.lines)
        self.assertAlmostEqual(t["revenue"], 1_005_000)
        self.assertAlmostEqual(t["cogs"], 600_000)

    def test_remap_matrix_finds_buried_variable_costs(self):
        r = A.cogs_remap_matrix(self.lines)
        names = {m["current_account"] for m in r["matrix"]}
        self.assertEqual(names, {"Merchant Processing Fees", "Workers Comp Insurance"})
        merchant = next(m for m in r["matrix"] if m["signal"] == "merchant")
        self.assertAlmostEqual(merchant["gm_impact_pct_points"], -1.99, places=2)
        self.assertLess(r["pro_forma_gross_margin_pct"], r["totals"]["gross_margin_pct"])

    def test_vague_items(self):
        r = A.vague_items(load_csv(FIX / "item_list.csv"))
        flagged = {i["item"] for i in r["items"]}
        self.assertIn("Custom", flagged)
        self.assertIn("Misc Service Fee", flagged)
        self.assertIn("Patrol Hours", flagged)
        self.assertNotIn("GRD-HLTH-ARMED", flagged)


class TestModule2(unittest.TestCase):
    def test_black_holes_and_allowlist(self):
        tables = {k: load_csv(FIX / f) for k, f in
                  (("pl", "pl_12months.csv"), ("coa", "coa.csv"))}
        hits = A.black_holes(tables)
        texts = {h["text"] for h in hits}
        for expected in ("Uncategorized Income", "Ask My Accountant", "Miscellaneous",
                         "Stripe Clearing", "Uncategorized Asset"):
            self.assertIn(expected, texts)
        self.assertNotIn("Other Income", texts)  # legitimate QBO account type
        ama = next(h for h in hits if h["text"] == "Ask My Accountant")
        self.assertEqual(ama["balance"], -1500.0)
        self.assertTrue(ama["bank_rule"])

    def test_blended_accounts(self):
        lines = A.parse_pl(load_csv(FIX / "pl_12months.csv"))
        found = A.blended_accounts(lines, load_csv(FIX / "vendor_spend.csv"))
        accts = {(f["file"], f["account"]) for f in found}
        self.assertIn(("pl_12months.csv", "Office Expenses"), accts)
        self.assertIn(("vendor_spend.csv", "Office Expenses"), accts)


class TestModule3(unittest.TestCase):
    def test_near_duplicates(self):
        entries = [("Amazon Web Services", "v", 2), ("AWS", "v", 3),
                   ("FedEx Corp", "v", 4), ("FedEx", "v", 5),
                   ("Mercy Hospital", "c", 2), ("Mercy Hospital Inc.", "c", 3),
                   ("Acme Retail", "c", 4)]
        pairs = {frozenset((d["name_a"], d["name_b"])) for d in A.near_duplicates(entries)}
        self.assertIn(frozenset(("Amazon Web Services", "AWS")), pairs)
        self.assertIn(frozenset(("FedEx Corp", "FedEx")), pairs)
        self.assertIn(frozenset(("Mercy Hospital", "Mercy Hospital Inc.")), pairs)
        self.assertFalse(any("Acme Retail" in p for p in pairs))

    def test_over_indexed_and_naming(self):
        coa = load_csv(FIX / "coa.csv")
        oi = A.over_indexed(coa, max_children=1)
        self.assertEqual({t["tool"] for t in oi["tool_named_accounts"]}, {"slack", "zoom"})
        self.assertEqual(oi["crowded_parents"][0]["parent"], "Software")
        bad = {n["name"]: n["reasons"] for n in A.naming_violations(coa)}
        self.assertIn("OFFICE_SUPPLIES 2024", bad)
        self.assertTrue(any("year" in r for r in bad["OFFICE_SUPPLIES 2024"]))
        self.assertNotIn("Utilities - Electric", bad)


class TestRealDataRegressions(unittest.TestCase):
    """Behaviour learned from the first real run (iteration 1)."""

    def test_sub_customers_are_not_duplicates(self):
        entries = [("DSV Contract Logistics Inc.:3210 Airway Drive", "s", 2),
                   ("DSV Contract Logistics Inc.", "s", 3),
                   ("RBC", "v", 4), ("R & B Construction", "v", 5)]
        self.assertEqual(A.near_duplicates(entries), [])

    def test_indented_parent_with_own_postings(self):
        lines = A.parse_pl(load_csv(FIX / "pl_indented.csv"))
        by = {l.name: l for l in lines}
        self.assertEqual(by["Office wages"].parent, "Guard Wages")
        self.assertEqual(by["Guard Wages"].amount, 600.0)
        self.assertIn("Cost of Goods Sold", by)  # account named like its section
        r = A.cogs_remap_matrix(lines)
        names = {m["current_account"] for m in r["matrix"]}
        self.assertIn("Guard Wages", names)
        self.assertIn("WSIB Expense", names)
        self.assertNotIn("Office wages", names)

    def test_non_operating_revenue_and_outliers(self):
        lines = A.parse_pl(load_csv(FIX / "pl_indented.csv"))
        self.assertEqual([x["account"] for x in A.non_operating_revenue(lines)],
                         ["foreign exchange gain/loss"])
        spikes = A.monthly_outliers(lines, min_amount=0, min_delta=0)
        self.assertTrue(any(x["account"] == "Guard Revenue" and x["month"] == "Mar" for x in spikes))


class TestEndToEnd(unittest.TestCase):
    def test_cli_run_writes_reports(self):
        with tempfile.TemporaryDirectory() as out:
            f, summary = run(FIX, out)
            self.assertTrue((Path(out) / "audit_report.md").exists())
            data = json.loads((Path(out) / "findings.json").read_text())
            self.assertGreater(len(data["roadmap"]["remapping_batches"]), 0)
            self.assertIn("vendors", summary["missing"])
            report = (Path(out) / "audit_report.md").read_text()
            self.assertIn("Remapping Matrix", report)
            self.assertIn("No QuickBooks data was changed", report)


if __name__ == "__main__":
    unittest.main()
