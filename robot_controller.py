import json
import math


class LowBatteryError(Exception):
    """Exception yang dilempar ketika level baterai di bawah 10 persen."""
    pass


class RobotController:
    def __init__(self, battery=100.0, x=0.0, y=0.0, heading=0.0):
        if not 0 <= battery <= 100:
            raise ValueError("Level baterai harus berada di antara 0 dan 100.")
        self.battery = float(battery)
        self.x = float(x)
        self.y = float(y)
        self.heading = float(heading) % 360

    def _check_battery(self):
        if self.battery < 10:
            raise LowBatteryError("Level baterai di bawah 10%.")

    def _consume_battery(self, amount):
        self.battery = max(0.0, min(100.0, self.battery - amount))

    def recharge(self, amount):
        """Menambah level baterai hingga maksimum 100."""
        if amount < 0:
            raise ValueError("Jumlah pengisian tidak boleh negatif.")
        self.battery = max(0.0, min(100.0, self.battery + amount))
        return self.battery

    def get_status_summary(self):
        """Mengembalikan ringkasan baterai dan status."""
        return {
            "battery": round(self.battery, 2),
            "status": "CRITICAL" if self.battery < 20 else "NORMAL",
        }

    def move_forward(self, distance):
        self._check_battery()
        if distance < 0:
            raise ValueError("Jarak tidak boleh negatif.")

        radians = math.radians(self.heading)
        self.x += distance * math.cos(radians)
        self.y += distance * math.sin(radians)
        self._consume_battery(distance * 0.5)  # 0.5% per satuan jarak
        return self.x, self.y

    def turn(self, degrees):
        self._check_battery()
        self.heading = (self.heading + degrees) % 360
        self._consume_battery(abs(degrees) * 0.2)  # 0.2% per derajat
        return self.heading

    def scan_surroundings(self):
        self._check_battery()
        self._consume_battery(1.0)  # 1% per scan
        # Simulasi hasil scan; dapat diganti dengan sensor nyata.
        return {
            "obstacles": [],
            "distances": {
                "front": 10.0,
                "left": 10.0,
                "right": 10.0,
                "back": 10.0,
            },
        }

    def to_telemetry_json(self):
        return json.dumps({
            "battery": round(self.battery, 2),
            "position": {
                "x": round(self.x, 2),
                "y": round(self.y, 2),
                "heading": round(self.heading, 2),
            },
        })
