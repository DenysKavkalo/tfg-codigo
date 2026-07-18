"""Regression checks for the result files cited in the memory."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


class ResultOutputTests(unittest.TestCase):
    """Keep documented counts and main scenarios aligned with generated files."""

    def test_review_counts_and_quality_reports(self) -> None:
        expected = {
            "venetian": {
                "agoda": 323,
                "booking_via_agoda": 1151,
                "priceline": 46,
                "tripcom": 346,
            },
            "wynn": {
                "agoda": 96,
                "booking_via_agoda": 510,
                "priceline": 24,
                "tripcom": 309,
            },
        }
        for hotel, counts in expected.items():
            clean = pd.read_csv(
                PROCESSED / f"reviews_{hotel}_2024_2025_clean.csv"
            )
            self.assertEqual(clean.groupby("platform").size().to_dict(), counts)
            quality = pd.read_csv(
                PROCESSED / f"reviews_{hotel}_2024_2025_quality.csv"
            )
            self.assertEqual(int(quality["removed_rows"].sum()), 0)

    def test_main_partition_probabilities(self) -> None:
        expected = {"venetian": 0.724812813, "wynn": 0.558737899}
        partition = "agoda+tripcom | booking_via_agoda+priceline"
        for hotel, probability in expected.items():
            results = pd.read_csv(
                PROCESSED / f"partition_probabilities_{hotel}_2024_2025.csv"
            ).sort_values("posterior_probability", ascending=False)
            self.assertIn(
                "log_bayes_factor_partition_vs_homogeneity",
                results.columns,
            )
            self.assertNotIn("log_bayes_factor_vs_homogeneity", results.columns)
            self.assertEqual(results.iloc[0]["partition"], partition)
            self.assertAlmostEqual(
                float(results.iloc[0]["posterior_probability"]),
                probability,
                places=6,
            )
            self.assertAlmostEqual(results["posterior_probability"].sum(), 1, places=10)
            homogeneous = results.loc[results["n_clusters"].eq(1)].iloc[0]
            self.assertAlmostEqual(
                float(
                    homogeneous[
                        "log_bayes_factor_partition_vs_homogeneity"
                    ]
                ),
                0,
                places=10,
            )

    def test_diagnostics_and_sensitivity_outputs(self) -> None:
        expected_annual = {
            "venetian": {
                "2024": "agoda+priceline | booking_via_agoda | tripcom",
                "2025": "agoda | booking_via_agoda+priceline+tripcom",
            },
            "wynn": {
                "2024": "agoda+tripcom | booking_via_agoda+priceline",
                "2025": "agoda+priceline+tripcom | booking_via_agoda",
            },
        }
        for hotel, annual_partitions in expected_annual.items():
            result_dir = PROCESSED / f"r_reviews_{hotel}_2024_2025"
            diagnostics = pd.read_csv(result_dir / "poisson_diagnostics.csv")
            self.assertEqual(len(diagnostics), 4)
            self.assertTrue((diagnostics["dispersion_index"] > 2).all())
            self.assertTrue((diagnostics["pp_dispersion_upper_p"] < 0.001).all())

            scenarios = pd.read_csv(result_dir / "sensitivity_key_scenarios.csv")
            self.assertEqual(len(scenarios), 9)
            annual = scenarios[
                scenarios["period_scenario"].astype(str).isin(["2024", "2025"])
                & scenarios["source_scenario"].eq("all_sources")
                & scenarios["score_mode"].eq("round")
            ]
            observed = dict(
                zip(annual["period_scenario"].astype(str), annual["top_partition"])
            )
            self.assertEqual(observed, annual_partitions)

    def test_frequentist_results(self) -> None:
        expected = {
            "venetian": {
                "f": 9.040307346,
                "eta_squared": 0.014356372,
            },
            "wynn": {
                "f": 9.267989398,
                "eta_squared": 0.028878120,
            },
        }
        significant_pairs = {
            ("booking_via_agoda", "agoda"),
            ("tripcom", "booking_via_agoda"),
        }

        for hotel, expected_values in expected.items():
            result_dir = PROCESSED / f"r_reviews_{hotel}_2024_2025"
            anova = pd.read_csv(result_dir / "anova_results.csv")
            self.assertEqual(
                set(anova["method"]),
                {"classic_one_way_anova", "welch_one_way_anova"},
            )
            classic = anova.loc[
                anova["method"].eq("classic_one_way_anova")
            ].iloc[0]
            self.assertAlmostEqual(
                float(classic["statistic_f"]), expected_values["f"], places=6
            )
            self.assertAlmostEqual(
                float(classic["eta_squared"]),
                expected_values["eta_squared"],
                places=6,
            )
            self.assertLess(float(classic["p_value"]), 0.001)

            pairwise = pd.read_csv(result_dir / "tukey_pairwise_results.csv")
            detected = {
                (row.platform_1, row.platform_2)
                for row in pairwise.itertuples()
                if row.difference_detected_0_05
            }
            self.assertEqual(detected, significant_pairs)

            within_blocks = pairwise[
                pairwise["same_dominant_bayesian_block"]
            ]
            self.assertEqual(len(within_blocks), 2)
            self.assertFalse(within_blocks["difference_detected_0_05"].any())


if __name__ == "__main__":
    unittest.main()
