"""Constants taken from the original Colab notebook (final cells 12-16) and file locations."""
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
REPORTS_FILE = os.path.join(DATA_DIR, "blockage_reports.json")

MAP_CENTER = (12.9815, 80.2180)       # Velachery, Chennai (lat, lon) - notebook cell 1
MAP_RADIUS_M = 2500                    # notebook cell 1
MODERATE_CM = 30                       # notebook final thresholds (cell 12/13)
BLOCKED_CM = 70
MODERATE_COST_MULTIPLIER = 3           # moderate road cost = length x 3 (notebook cell 7/12)
EARTH_RADIUS_M = 6371009               # radius used by osmnx.distance.great_circle

BLOCKAGE_REASONS = ["Flooding", "Fallen tree or debris", "Road damage", "Other obstruction"]
