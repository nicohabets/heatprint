"""Physical constants, conversion factors and reference tables (METHODS section 1).

Everything in this module is a plain Python constant so that the values can be
inspected, documented and unit-tested without any runtime dependency.
"""

from __future__ import annotations

import math

# --- Energy content and unit conversions (METHODS section 1) ---------------------------------

#: Higher heating value (Hs) of Groningen-quality natural gas, kWh per m3 (31.65 MJ/m3).
#: Dutch suppliers bill on the higher heating value.
GAS_HS_KWH_PER_M3: float = 8.792

#: Lower heating value (Hi) of natural gas, kWh per m3 (about 28.5 MJ/m3).
GAS_HI_KWH_PER_M3: float = 7.92

#: 1 GJ = 277.78 kWh (district heat meters report GJ).
GJ_TO_KWH: float = 277.78

#: 1 MJ/m2 = 100 J/cm2 (Open-Meteo daily radiation sum to the KNMI unit).
MJ_M2_TO_J_CM2: float = 100.0

#: 1 Wh/m2 = 0.36 J/cm2 (Open-Meteo hourly radiation sum to the KNMI unit).
WH_M2_TO_J_CM2: float = 0.36

#: Wind speed km/h to m/s.
KMH_TO_MS: float = 1 / 3.6

#: KNMI reports TG, FG, TN and TX in tenths of a unit; Q is already in J/cm2.
KNMI_TENTHS: float = 0.1

#: Default CO2 emission factor for natural gas in the Netherlands, kg per m3 (configurable).
GAS_CO2_KG_PER_M3: float = 1.78

#: Default CO2 emission factor for electricity in the Netherlands, kg per kWh (configurable).
ELEC_CO2_KG_PER_KWH: float = 0.30

#: kWh per (K day) to W/K: a slope of 1 kWh/(K day) equals 1000 W h / 24 h = 41.67 W/K.
W_PER_K_FROM_KWH_PER_K_DAY: float = 1000 / 24

#: KNMI "effective temperature" wind divisor: T_eff = T - wind / 1.5 (METHODS section 3).
KNMI_WIND_DIVISOR: float = 1.5

#: Daily KEV-SJV square-root wind coefficient (PBL 2022 eq. 17/20): T - sqrt(wind).
#: The hourly gas-profile term sqrt(wind)/0.35 (Informatiecode appendix 3) is a
#: different formula and is not used here. See METHODS section 3.
PBL_WIND_SQRT_COEF: float = 1.0

#: PBL solar term: 1/480 degree per J/cm2 of daily global radiation (optional).
PBL_SUN_COEF: float = 1 / 480

#: Thermal inertia weights of the PBL / house presets (today, yesterday).
PBL_TAC_WEIGHTS: tuple[float, float] = (0.65, 0.35)

#: KNMI gas-year degree-day base temperature (METHODS section 4.2).
KNMI14_BASE_TEMP: float = 14.0

#: Balance temperature used for the house method as long as no fit exists (METHODS section 4.4).
HOUSE_FALLBACK_BALANCE_TEMP: float = 15.5

# --- Rooms (METHODS section 12.2 / 12.4) -------------------------------------------------------

#: Default ceiling height used only to derive ``volume_m3`` from floor area.
#: Volume is captured for a future ventilation/thermal-mass method; unused in v0.2.
DEFAULT_CEILING_HEIGHT_M: float = 2.5

#: Indicative emitter output per m² (W/m²) by ``emitter_kind``. Placeholders until
#: verified against a published source (ROADMAP research item); rooms that use these
#: defaults are flagged ``ROOM_WEIGHT_ASSUMED`` (METHODS section 12.2).
DEFAULT_OUTPUT_W_PER_M2: dict[str, float] = {
    "radiator": 70.0,
    "underfloor": 50.0,
    "electric": 100.0,
    "other": 70.0,
}

# --- Data-source health checks (METHODS section 14) --------------------------------------------

#: Consecutive zero-increment days before ``STUCK_VALUE`` fires.
HEALTH_STUCK_DAYS: int = 3

#: A day is implausible when it exceeds this multiple of the trailing median.
HEALTH_IMPLAUSIBLE_MULTIPLE: float = 5.0

#: Lookback window for the implausible-value median (days before the checked day).
HEALTH_IMPLAUSIBLE_LOOKBACK_DAYS: int = 30

#: Minimum samples in that lookback before ``IMPLAUSIBLE_VALUE`` may fire.
HEALTH_IMPLAUSIBLE_MIN_SAMPLES: int = 7

#: Length of each trailing window compared by ``SCALE_DRIFT`` (days 1-15 vs 16-30).
HEALTH_SCALE_WINDOW_DAYS: int = 15

#: Order-of-magnitude ratio between the two scale-drift window medians.
HEALTH_SCALE_RATIO: float = 10.0

#: Minimum samples in each scale-drift window.
HEALTH_SCALE_MIN_SAMPLES: int = 7

#: Skip heat/demand scale-drift when the two windows' median degree days differ
#: by more than this factor (seasonal drop, not a sensor unit change).
HEALTH_SCALE_DD_COMPARABLE_RATIO: float = 3.0

#: Normal provisional-weather window per provider. Longer than this is stalled.
#: KNMI: 1-2 days (METHODS §2). Open-Meteo: ERA5 archive delay (8 days).
HEALTH_PROVISIONAL_WINDOW_DAYS: dict[str, int] = {
    "knmi": 2,
    "open_meteo": 8,
    "ha_sensors": 2,
}

# --- mindergas month weights (METHODS section 4.1) ---------------------------------------------

#: Month factors of the classic weighted degree days: Nov-Feb 1.1, Mar and Oct 1.0, Apr-Sep 0.8.
MONTH_WEIGHTS: dict[int, float] = {
    1: 1.1,
    2: 1.1,
    3: 1.0,
    4: 0.8,
    5: 0.8,
    6: 0.8,
    7: 0.8,
    8: 0.8,
    9: 0.8,
    10: 1.0,
    11: 1.1,
    12: 1.1,
}

# --- KNMI stations with daily data (station id -> (name, latitude, longitude)) -----------------

#: Approximate coordinates (2 decimals) of the KNMI stations that publish daily data.
KNMI_STATIONS: dict[int, tuple[str, float, float]] = {
    209: ("IJmond", 52.47, 4.52),
    210: ("Valkenburg Zh", 52.17, 4.43),
    215: ("Voorschoten", 52.14, 4.44),
    225: ("IJmuiden", 52.46, 4.56),
    235: ("De Kooy", 52.93, 4.78),
    240: ("Schiphol", 52.32, 4.79),
    242: ("Vlieland", 53.24, 4.92),
    249: ("Berkhout", 52.64, 4.98),
    251: ("Hoorn Terschelling", 53.39, 5.35),
    257: ("Wijk aan Zee", 52.51, 4.60),
    260: ("De Bilt", 52.10, 5.18),
    267: ("Stavoren", 52.90, 5.38),
    269: ("Lelystad", 52.46, 5.52),
    270: ("Leeuwarden", 53.22, 5.75),
    273: ("Marknesse", 52.70, 5.89),
    275: ("Deelen", 52.06, 5.87),
    277: ("Lauwersoog", 53.41, 6.20),
    278: ("Heino", 52.44, 6.26),
    279: ("Hoogeveen", 52.75, 6.57),
    280: ("Eelde", 53.12, 6.59),
    283: ("Hupsel", 52.07, 6.66),
    286: ("Nieuw Beerta", 53.20, 7.15),
    290: ("Twenthe", 52.27, 6.89),
    310: ("Vlissingen", 51.44, 3.60),
    319: ("Westdorpe", 51.23, 3.86),
    323: ("Wilhelminadorp", 51.53, 3.88),
    330: ("Hoek van Holland", 51.99, 4.12),
    340: ("Woensdrecht", 51.45, 4.34),
    344: ("Rotterdam", 51.96, 4.45),
    348: ("Cabauw", 51.97, 4.93),
    350: ("Gilze-Rijen", 51.57, 4.94),
    356: ("Herwijnen", 51.86, 5.15),
    370: ("Eindhoven", 51.45, 5.38),
    375: ("Volkel", 51.66, 5.71),
    377: ("Ell", 51.20, 5.76),
    380: ("Maastricht", 50.91, 5.76),
    391: ("Arcen", 51.50, 6.20),
}

EARTH_RADIUS_KM: float = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_station(lat: float, lon: float) -> list[tuple[int, str, float]]:
    """Return all KNMI stations as ``(station_id, name, distance_km)`` sorted by distance.

    The first element is the nearest station; the config flow shows the list with
    distances so the user can pick a different one.
    """
    result = [
        (station_id, name, round(haversine_km(lat, lon, slat, slon), 1))
        for station_id, (name, slat, slon) in KNMI_STATIONS.items()
    ]
    result.sort(key=lambda item: (item[2], item[0]))
    return result
