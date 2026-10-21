import math
import unittest

from entrance import BODY_RADIUS, HINGE, MAX_WALK_SPEED, PORTAL, door_angle, entrance_plan, path_at, walk_pose


def plan(deadline=8.0, enabled=True):
    turns = [{"action": "welcome", "start": 2.5}, {"action": "explain", "start": deadline}]
    return entrance_plan({"scene": {"entrance": enabled}, "turns": turns}, {"turns": turns})


class EntranceTests(unittest.TestCase):
    def test_candidates_start_outside_and_finish_in_front_of_their_own_chair(self):
        result = plan()
        for name, x in (("candidate_a", -.82), ("candidate_b", .82)):
            blocking = result["actors"][name]
            self.assertGreater(blocking["path"][0][1] - BODY_RADIUS, 3.44)
            self.assertEqual(walk_pose(blocking, 0)[0], blocking["path"][0])
            position, heading = walk_pose(blocking, blocking["seat_start"])
            self.assertEqual(position, (x, .30, 0))
            self.assertEqual(heading, 0)
            self.assertLess(blocking["seat_end"], 8.0)
            self.assertLessEqual(blocking["walk_speed_m_s"], MAX_WALK_SPEED)

    def test_longer_welcome_does_not_slow_candidates_into_each_other(self):
        self.assertEqual(plan(15), plan(8))

    def test_insufficient_timing_fails_before_expensive_blender_baking(self):
        for deadline in (3, 5, 6.9, 7.2):
            with self.subTest(deadline=deadline), self.assertRaisesRegex(ValueError, "Increase the welcome"):
                plan(deadline)

    def test_no_entrance_has_no_paths_and_a_closed_door(self):
        result = plan(enabled=False)
        self.assertEqual(result["actors"], {})
        self.assertEqual(door_angle(result, 1.5), 0)

    def test_realistic_paths_clear_the_wall_other_candidate_and_door_sweep(self):
        for deadline in (7.5, 7.75, 8, 12):
            result = plan(deadline)
            self.assertEqual(door_angle(result, 0), 0)
            self.assertAlmostEqual(door_angle(result, .85), -math.pi / 2)
            self.assertEqual(door_angle(result, result["door"]["close_end"]), 0)
            for sample in range(801):
                t = sample / 100
                points = [walk_pose(blocking, t)[0] for blocking in result["actors"].values()]
                self.assertGreaterEqual(math.dist(*points), 2 * BODY_RADIUS, (deadline, t, points))
                angle = door_angle(result, t)
                for point in points:
                    if point[1] - BODY_RADIUS < 3.44 and point[1] + BODY_RADIUS > 3.26:
                        self.assertGreaterEqual(point[0] - BODY_RADIUS, PORTAL[0])
                        self.assertLessEqual(point[0] + BODY_RADIUS, PORTAL[1])
                    dx, dy = point[0] - HINGE[0], point[1] - HINGE[1]
                    local_x = math.cos(angle) * dx + math.sin(angle) * dy - .51
                    local_y = -math.sin(angle) * dx + math.cos(angle) * dy - .035
                    distance = math.hypot(max(abs(local_x) - .51, 0), max(abs(local_y) - .035, 0))
                    self.assertGreaterEqual(distance, BODY_RADIUS, (deadline, t, point, angle))

    def test_samir_turns_only_after_his_walking_feet_clear_the_frame(self):
        blocking = plan(7.75)["actors"]["candidate_b"]
        self.assertLessEqual(blocking["path"][1][1], 2.35)
        for sample in range(300):
            point, heading = walk_pose(blocking, sample / 100)
            if point[1] >= 2.95:
                self.assertEqual(heading, 0)

    def test_body_heading_is_continuous_at_aisle_corners(self):
        for blocking in plan()["actors"].values():
            previous = walk_pose(blocking, 0)[1]
            for sample in range(1, 801):
                heading = walk_pose(blocking, sample / 100)[1]
                change = (heading - previous + math.pi) % (2 * math.pi) - math.pi
                self.assertLess(abs(change), .11)
                previous = heading

    def test_path_rejects_zero_length_segments_and_clamps_progress(self):
        with self.assertRaisesRegex(ValueError, "nonzero"):
            path_at([(0, 0, 0), (0, 0, 0)], .5)
        points = [(0, 0, 0), (0, -1, 0), (1, -1, 0)]
        self.assertEqual(path_at(points, -1)[0], points[0])
        self.assertEqual(path_at(points, 2)[0], points[-1])


if __name__ == "__main__":
    unittest.main()
