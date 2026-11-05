import unittest

from beacon_planner import (

    assess_beacon,
   classify_priority,
    process_records,
    read_csv_dataset,
write_report,
    recommend_action
)


class TestBeaconPlanner(unittest.TestCase):

    def test_low_priority(self):
        self.assertEqual(
            classify_priority(10),
            "LOW"
        )

    def test_moderate_priority(self):
        self.assertEqual(
            classify_priority(25),
            "MODERATE"
        )

    def test_high_priority(self):
        self.assertEqual(
            classify_priority(50),
            "HIGH"
        )

    def test_urgent_priority(self):
        self.assertEqual(
            classify_priority(80),
            "URGENT"
        )

    def test_missing_beacon_recommendation(self):
        result = recommend_action(
            "HIGH",
            "missing"
        )

        self.assertIn(
            "surveyor-led investigation",
            result
        )


if __name__ == "__main__":
    unittest.main()