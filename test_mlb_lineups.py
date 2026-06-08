import unittest

from mlb_lineups import infer_pitcher_role_from_stat_line


class PitcherRoleInferenceTests(unittest.TestCase):
    def test_saves_and_holds_make_swingman_a_reliever(self) -> None:
        stat_line = {
            "gamesPlayed": 23,
            "gamesStarted": 1,
            "saves": 9,
            "holds": 2,
        }

        self.assertEqual(infer_pitcher_role_from_stat_line(stat_line), "reliever")

    def test_relief_heavy_usage_makes_pitcher_a_reliever(self) -> None:
        stat_line = {
            "gamesPlayed": 18,
            "gamesStarted": 3,
            "saves": 0,
            "holds": 0,
        }

        self.assertEqual(infer_pitcher_role_from_stat_line(stat_line), "reliever")

    def test_start_heavy_usage_makes_pitcher_a_starter(self) -> None:
        stat_line = {
            "gamesPlayed": 12,
            "gamesStarted": 11,
            "saves": 0,
            "holds": 0,
        }

        self.assertEqual(infer_pitcher_role_from_stat_line(stat_line), "starter")


if __name__ == "__main__":
    unittest.main()
