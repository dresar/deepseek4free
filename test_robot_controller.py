import math
import unittest

from robot_controller import RobotController, LowBatteryError


class TestRobotControllerInitialization(unittest.TestCase):
    def test_default_values(self):
        robot = RobotController()
        self.assertEqual(robot.battery, 100.0)
        self.assertEqual(robot.x, 0.0)
        self.assertEqual(robot.y, 0.0)
        self.assertEqual(robot.heading, 0.0)

    def test_custom_values(self):
        robot = RobotController(battery=50.0, x=1.5, y=2.5, heading=90.0)
        self.assertEqual(robot.battery, 50.0)
        self.assertEqual(robot.x, 1.5)
        self.assertEqual(robot.y, 2.5)
        self.assertEqual(robot.heading, 90.0)

    def test_heading_normalization(self):
        robot = RobotController(heading=450.0)
        self.assertEqual(robot.heading, 90.0)
        robot = RobotController(heading=-90.0)
        self.assertEqual(robot.heading, 270.0)

    def test_invalid_battery_low(self):
        with self.assertRaises(ValueError):
            RobotController(battery=-0.1)

    def test_invalid_battery_high(self):
        with self.assertRaises(ValueError):
            RobotController(battery=100.1)

    def test_battery_boundaries_valid(self):
        robot_low = RobotController(battery=0.0)
        self.assertEqual(robot_low.battery, 0.0)
        robot_high = RobotController(battery=100.0)
        self.assertEqual(robot_high.battery, 100.0)


class TestMoveForward(unittest.TestCase):
    def setUp(self):
        self.robot = RobotController()

    def test_move_forward_heading_zero(self):
        x, y = self.robot.move_forward(10.0)
        self.assertAlmostEqual(x, 10.0)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(self.robot.battery, 95.0)

    def test_move_forward_heading_90(self):
        self.robot.heading = 90.0
        x, y = self.robot.move_forward(10.0)
        self.assertAlmostEqual(x, 0.0, places=7)
        self.assertAlmostEqual(y, 10.0)
        self.assertAlmostEqual(self.robot.battery, 95.0)

    def test_move_forward_heading_45(self):
        self.robot.heading = 45.0
        distance = 10.0
        x, y = self.robot.move_forward(distance)
        expected = distance * math.cos(math.radians(45.0))
        self.assertAlmostEqual(x, expected)
        self.assertAlmostEqual(y, expected)
        self.assertAlmostEqual(self.robot.battery, 100.0 - distance * 0.5)

    def test_move_forward_negative_distance_raises(self):
        with self.assertRaises(ValueError):
            self.robot.move_forward(-1.0)

    def test_move_forward_consumes_battery(self):
        self.robot.move_forward(20.0)
        self.assertAlmostEqual(self.robot.battery, 90.0)

    def test_move_forward_battery_capped_at_zero(self):
        self.robot.battery = 10.0
        self.robot.move_forward(30.0)  # konsumsi 15.0
        self.assertAlmostEqual(self.robot.battery, 0.0)
        self.assertAlmostEqual(self.robot.x, 30.0)

    def test_move_forward_low_battery_raises(self):
        self.robot.battery = 9.99
        with self.assertRaises(LowBatteryError):
            self.robot.move_forward(1.0)
        self.assertAlmostEqual(self.robot.battery, 9.99)  # tidak berubah


class TestTurn(unittest.TestCase):
    def setUp(self):
        self.robot = RobotController()

    def test_turn_positive(self):
        heading = self.robot.turn(90.0)
        self.assertAlmostEqual(heading, 90.0)
        self.assertAlmostEqual(self.robot.battery, 82.0)

    def test_turn_negative(self):
        heading = self.robot.turn(-45.0)
        self.assertAlmostEqual(heading, 315.0)
        self.assertAlmostEqual(self.robot.battery, 91.0)

    def test_turn_wrap_around(self):
        self.robot.heading = 350.0
        heading = self.robot.turn(20.0)
        self.assertAlmostEqual(heading, 10.0)

    def test_turn_consumes_battery(self):
        self.robot.turn(180.0)
        self.assertAlmostEqual(self.robot.battery, 64.0)

    def test_turn_low_battery_raises(self):
        self.robot.battery = 5.0
        with self.assertRaises(LowBatteryError):
            self.robot.turn(10.0)
        self.assertAlmostEqual(self.robot.battery, 5.0)


class TestRecharge(unittest.TestCase):
    def setUp(self):
        self.robot = RobotController(battery=50.0)

    def test_recharge_increases_battery(self):
        new_level = self.robot.recharge(30.0)
        self.assertAlmostEqual(new_level, 80.0)
        self.assertAlmostEqual(self.robot.battery, 80.0)

    def test_recharge_caps_at_100(self):
        self.robot.battery = 90.0
        new_level = self.robot.recharge(20.0)
        self.assertAlmostEqual(new_level, 100.0)
        self.assertAlmostEqual(self.robot.battery, 100.0)

    def test_recharge_zero(self):
        new_level = self.robot.recharge(0.0)
        self.assertAlmostEqual(new_level, 50.0)

    def test_recharge_negative_raises(self):
        with self.assertRaises(ValueError):
            self.robot.recharge(-1.0)

    def test_recharge_returns_new_level(self):
        self.assertAlmostEqual(self.robot.recharge(10.0), 60.0)


class TestLowBatteryError(unittest.TestCase):
    def test_move_forward_raises_when_battery_below_10(self):
        robot = RobotController(battery=9.0)
        with self.assertRaises(LowBatteryError):
            robot.move_forward(1.0)

    def test_turn_raises_when_battery_below_10(self):
        robot = RobotController(battery=9.0)
        with self.assertRaises(LowBatteryError):
            robot.turn(1.0)

    def test_scan_surroundings_raises_when_battery_below_10(self):
        robot = RobotController(battery=9.0)
        with self.assertRaises(LowBatteryError):
            robot.scan_surroundings()

    def test_no_error_when_battery_exactly_10(self):
        robot = RobotController(battery=10.0)
        # Tidak boleh melempar LowBatteryError
        robot.move_forward(1.0)
        self.assertAlmostEqual(robot.battery, 9.5)

    def test_error_message(self):
        robot = RobotController(battery=9.0)
        with self.assertRaises(LowBatteryError) as cm:
            robot.move_forward(1.0)
        self.assertIn("Level baterai di bawah 10%", str(cm.exception))


class TestGetStatusSummary(unittest.TestCase):
    def test_status_normal(self):
        robot = RobotController(battery=100.0)
        summary = robot.get_status_summary()
        self.assertEqual(summary["battery"], 100.0)
        self.assertEqual(summary["status"], "NORMAL")

    def test_status_critical(self):
        robot = RobotController(battery=19.99)
        summary = robot.get_status_summary()
        self.assertEqual(summary["battery"], 19.99)
        self.assertEqual(summary["status"], "CRITICAL")

    def test_status_boundary_20_is_normal(self):
        robot = RobotController(battery=20.0)
        summary = robot.get_status_summary()
        self.assertEqual(summary["status"], "NORMAL")

    def test_status_just_below_20_is_critical(self):
        robot = RobotController(battery=19.99)
        summary = robot.get_status_summary()
        self.assertEqual(summary["status"], "CRITICAL")

    def test_status_rounding(self):
        robot = RobotController(battery=33.333)
        summary = robot.get_status_summary()
        self.assertEqual(summary["battery"], 33.33)

    def test_status_rounding_can_show_20_but_still_critical(self):
        robot = RobotController(battery=19.999)
        summary = robot.get_status_summary()
        self.assertEqual(summary["battery"], 20.0)
        self.assertEqual(summary["status"], "CRITICAL")


if __name__ == "__main__":
    unittest.main()
