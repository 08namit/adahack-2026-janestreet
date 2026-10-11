"""
GREEN ROUTE  -  find the greenest way to get to the office in Edinburgh.

What it does, in four steps:
  1. You type your home and office (an address, a building name like
     "Appleton Tower", or a postcode). It shows the real places it finds
     and you pick the right one, so it never guesses.
  2. It asks OpenRouteService (a free online map service) for a route by
     car, bus, bike, e-bike and on foot.
  3. It works out the time, cost and CO2 of each route, and finds the
     "efficient frontier": the routes you can't beat on BOTH time and CO2.
  4. It shows you the results three ways:
       - a table in this window
       - an animated map where all the routes race each other (map.html)
       - a chart of time vs CO2 (frontier.png)

Run it with:   python green_route.py
"""


import json
import math
import os
import re
import webbrowser
from datetime import date, datetime, timedelta

import requests
import folium
from folium.plugins import TimestampedGeoJson
import matplotlib.pyplot as plt


KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_key.txt")


def read_api_key():
    """Return the key saved in api_key.txt, or "" if there isn't one."""
    if not os.path.exists(KEY_FILE):
        return ""
    with open(KEY_FILE) as f:
        return f.read().strip()


API_KEY = read_api_key()
DEMO = API_KEY == ""

DAYS_PER_WEEK = 5
WORKING_WEEKS = 46
TRIPS_PER_YEAR = 2 * DAYS_PER_WEEK * WORKING_WEEKS

CO2_PER_KM = {
    "Car": 0.164,
    "Bus": 0.1,
    "E-bike": 0.006,
    "Bike": 0.0,
    "Walk": 0.0,
}

CAR_COST_PER_KM = 0.106
CAR_PARKING_PER_DAY = 0

CAR_OWNING_COST = 2470

BUS_FARE = 2.4
BUS_ANNUAL_TICKET = 760

BIKE_PRICE = 500
EBIKE_PRICE = 2000
BIKE_LIFE_YEARS = 5
BIKE_SERVICING = 100
EBIKE_SERVICING = 150
EBIKE_CHARGING = 10
BIKE_YEARLY_COST = BIKE_PRICE / BIKE_LIFE_YEARS + BIKE_SERVICING
EBIKE_YEARLY_COST = EBIKE_PRICE / BIKE_LIFE_YEARS + EBIKE_SERVICING + EBIKE_CHARGING

HOURS_WORKED_PER_YEAR = 37.5 * WORKING_WEEKS

EXERCISE_SHARE = {"Car": 0, "Bus": 0, "Bike": 1.0, "E-bike": 0.5, "Walk": 1.0}
MAX_EXERCISE_HOURS = 2.5 * WORKING_WEEKS

CYCLE_TO_WORK_SAVING = 0.28

MAP_SERVICE_DELAY = 1.14
MORNING_RUSH = 1.79 / MAP_SERVICE_DELAY
EVENING_RUSH = 1.87 / MAP_SERVICE_DELAY
DAYTIME_TRAFFIC = 1.58 / MAP_SERVICE_DELAY
NIGHT_TRAFFIC = 1.0
PARKING_MINUTES = 3

CHECKED_TIMES = {
    ("Appleton Tower", "EH9 3FG"): {"Car": 12, "Bus": 16, "Bike": 11, "E-bike": 9, "Walk": 40},
}

BUS_STOP_SLOWDOWN = 1.3
BUS_WAIT_MINUTES = 8

RAIN_LIMIT = 1.0
GUST_LIMIT = 60
ICE_LIMIT = 0

MODES = {
    "Car": {"profile": "driving-car", "colour": "#c0392b"},
    "Bus": {"profile": "driving-car", "colour": "#2c7be5"},
    "Bike": {"profile": "cycling-regular", "colour": "#1e9e5a"},
    "E-bike": {"profile": "cycling-electric", "colour": "#12b3a6"},
    "Walk": {"profile": "foot-walking", "colour": "#8e44ad"},
}

HOW_MANY_MATCHES = 5
CACHE_FILE = "routes_cache.json"


def search_addresses(text):
    """
    Look up typed text and return a list of possible matches:
    [ ([lon, lat], "full address"), ... ]  best match first.

    We use two free services, no key needed:
      - postcodes.io, if the text is a UK postcode (exact, official data)
      - Nominatim, OpenStreetMap's own search, for everything else.
        It knows buildings and places by name, like "Appleton Tower".
    """
    if looks_like_postcode(text):
        return search_postcode(text)

    matches = search_openstreetmap(text, edinburgh_only=True)
    if not matches:
        matches = search_openstreetmap(text, edinburgh_only=False)
    return matches


def looks_like_postcode(text):
    """True for things like 'EH8 9LE' or 'eh89le'."""
    return re.fullmatch(r"[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}", text.upper().strip()) is not None


def search_postcode(text):
    url = "https://api.postcodes.io/postcodes/" + text.replace(" ", "")
    answer = requests.get(url, timeout=20).json()
    if answer.get("status") != 200:
        return []
    place = answer["result"]
    label = f"{place['postcode']}, {place['admin_ward']}, {place['admin_district']}"
    return [([place["longitude"], place["latitude"]], label)]


def search_openstreetmap(text, edinburgh_only):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": text, "format": "jsonv2", "limit": HOW_MANY_MATCHES, "countrycodes": "gb"}
    if edinburgh_only:
        params["q"] = re.sub("edinburgh", "", text, flags=re.IGNORECASE).strip(" ,")
        params["viewbox"] = "-3.75,56.10,-2.60,55.75"
        params["bounded"] = 1

    headers = {"User-Agent": "GreenRoute hackathon project"}
    answer = requests.get(url, params=params, headers=headers, timeout=20).json()

    matches = []
    for place in answer:
        parts = [p for p in place["display_name"].split(", ")
                 if p not in ("United Kingdom", "Scotland", "Alba / Scotland")]
        matches.append(([float(place["lon"]), float(place["lat"])], ", ".join(parts)))
    return matches


def ask_for_address(question, cache):
    """
    Ask for an address, show the matches, and keep asking until the user
    picks one. This is how we make sure the program never just guesses.
    """
    while True:
        text = input(question).strip()
        if not text:
            print("  Please type an address. A postcode is the most accurate.")
            continue

        if "search|" + text in cache:
            matches = cache["search|" + text]
        else:
            try:
                matches = search_addresses(text)
            except Exception as error:
                print(f"  Couldn't search: {error}")
                continue
            cache["search|" + text] = matches

        if not matches:
            print("  No matches. Try a postcode, or the street name and number.")
            continue

        print("  Did you mean:")
        for number, (coordinates, label) in enumerate(matches, start=1):
            print(f"    {number}. {label}")
        print("    0. None of these - type it again")

        choice = input("  Pick a number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            coordinates, label = matches[int(choice) - 1]
            print(f"  Using: {label}\n")
            return coordinates, label
        print()


def get_route(start, end, mode):
    """Ask for one route. Returns (points, km, minutes). Points are [lon, lat]."""
    if DEMO:
        return fake_route(start, end, mode)

    url = f"https://api.openrouteservice.org/v2/directions/{MODES[mode]['profile']}/geojson"
    body = {"coordinates": [start, end]}
    answer = requests.post(url, json=body, headers={"Authorization": API_KEY},
                           timeout=30).json()
    if "features" not in answer:
        raise ValueError(f"No {mode} route. Map service said: {answer.get('error', answer)}")

    route = answer["features"][0]
    points = route["geometry"]["coordinates"]
    km = route["properties"]["summary"]["distance"] / 1000
    minutes = route["properties"]["summary"]["duration"] / 60
    return points, km, minutes


def fake_route(start, end, mode):
    """DEMO mode: a straight line, made 30% longer to act like real streets."""
    speeds = {"Car": 30, "Bus": 30, "Bike": 16, "E-bike": 22, "Walk": 5}
    km = straight_line_km(start, end) * 1.3
    points = [[start[0] + (end[0] - start[0]) * i / 50,
               start[1] + (end[1] - start[1]) * i / 50] for i in range(51)]
    return points, km, km / speeds[mode] * 60


def straight_line_km(a, b):
    """Distance between two [lon, lat] points, as the crow flies."""
    lat_km = (b[1] - a[1]) * 111
    lon_km = (b[0] - a[0]) * 111 * math.cos(math.radians(a[1]))
    return math.sqrt(lat_km ** 2 + lon_km ** 2)


def traffic_slowdown(hour):
    """How many times longer a drive takes than on empty roads, leaving at this hour."""
    if 7 <= hour <= 9:
        return MORNING_RUSH
    if 16 <= hour <= 18:
        return EVENING_RUSH
    if 6 <= hour <= 20:
        return DAYTIME_TRAFFIC
    return NIGHT_TRAFFIC


def checked_times(start_name, end_name):
    """The hand-checked times for this trip, or None if we haven't checked it."""
    for (start_word, end_word), times in CHECKED_TIMES.items():
        if start_word in start_name and end_word in end_name:
            return times
    return None


def realistic_minutes(mode, raw_minutes, km, hour=8):
    """The map service assumes empty roads. Make the times honest for this hour."""
    if mode == "Car":
        return raw_minutes * traffic_slowdown(hour) + PARKING_MINUTES
    if mode == "Bus":
        return raw_minutes * traffic_slowdown(hour) * BUS_STOP_SLOWDOWN + BUS_WAIT_MINUTES
    return raw_minutes


def get_weather_history(lon, lat):
    """Last year's weather, hour by hour, from Open-Meteo (free, no key needed)."""
    end = date.today() - timedelta(days=7)
    start = end - timedelta(days=365)
    params = {"latitude": lat, "longitude": lon,
              "start_date": str(start), "end_date": str(end),
              "hourly": "precipitation,wind_gusts_10m,temperature_2m",
              "timezone": "Europe/London"}
    answer = requests.get("https://archive-api.open-meteo.com/v1/archive",
                          params=params, timeout=30).json()
    return answer["hourly"]


def get_forecast(lon, lat):
    """Today's and tomorrow's weather, hour by hour, from Open-Meteo."""
    params = {"latitude": lat, "longitude": lon, "forecast_days": 2,
              "hourly": "precipitation,wind_gusts_10m,temperature_2m",
              "timezone": "Europe/London"}
    answer = requests.get("https://api.open-meteo.com/v1/forecast",
                          params=params, timeout=30).json()
    return answer["hourly"]


def weather_at(weather, i):
    """The rain, gusts and temperature in hour number i. Missing values count as calm."""
    rain = weather["precipitation"][i] or 0
    gusts = weather["wind_gusts_10m"][i] or 0
    temperature = weather["temperature_2m"][i]
    if temperature is None:
        temperature = 10
    return rain, gusts, temperature


def is_bad_weather(rain, gusts, temperature):
    return rain >= RAIN_LIMIT or gusts >= GUST_LIMIT or temperature <= ICE_LIMIT


def bad_weather_share(weather, hours):
    """What share of last year's weekday commutes, leaving at these hours, had bad weather."""
    trips = 0
    bad = 0
    for i in range(len(weather["time"])):
        moment = datetime.fromisoformat(weather["time"][i])
        if moment.weekday() < 5 and moment.hour in hours:
            trips += 1
            rain, gusts, temperature = weather_at(weather, i)
            if is_bad_weather(rain, gusts, temperature):
                bad += 1
    return bad / max(trips, 1)


def apply_weather(routes, bad_share):
    """On bad-weather days, bikers and walkers take the bus. Blend that into their numbers."""
    bus = None
    for route in routes:
        if route["mode"] == "Bus":
            bus = route
    good_share = 1 - bad_share
    for route in routes:
        if route["mode"] in ("Bike", "E-bike", "Walk"):
            route["active_minutes"] = route["minutes"] * good_share
            route["minutes"] = route["minutes"] * good_share + bus["minutes"] * bad_share
            route["co2_year"] = route["co2_year"] * good_share + bus["co2_year"] * bad_share
            route["cost_year"] = route["cost_year"] * good_share + bus["cost_year"] * bad_share


def score(mode, points, km, raw_minutes, hours=(8, 17)):
    """
    Work out everything we want to know about one route.
    `hours` is when you leave home and when you leave work, like (8, 17).
    """
    if mode == "Car":
        cost_per_day = 2 * km * CAR_COST_PER_KM + CAR_PARKING_PER_DAY
    elif mode == "Bus":
        cost_per_day = 2 * BUS_FARE
    else:
        cost_per_day = 0

    there = realistic_minutes(mode, raw_minutes, km, hours[0])
    back = realistic_minutes(mode, raw_minutes, km, hours[1])
    minutes = (there + back) / 2

    cost_year = cost_per_day * DAYS_PER_WEEK * WORKING_WEEKS
    if mode == "Bus":
        cost_year = min(cost_year, BUS_ANNUAL_TICKET)

    return {
        "mode": mode,
        "points": points,
        "km": km,
        "minutes": minutes,
        "active_minutes": minutes,
        "co2_year": km * CO2_PER_KM[mode] * TRIPS_PER_YEAR,
        "cost_year": cost_year,
    }


def yearly_cost(route, sell_car):
    """Everything this way of travelling costs you in a year, in pounds."""
    if route["mode"] == "Car" and sell_car:
        return route["cost_year"] + CAR_OWNING_COST
    if route["mode"] == "Bike":
        return BIKE_YEARLY_COST + route["cost_year"]
    if route["mode"] == "E-bike":
        return EBIKE_YEARLY_COST + route["cost_year"]
    return route["cost_year"]


def add_true_time(route, pay_per_hour, sell_car, would_exercise):
    """
    TRUE TIME, in hours a year =   hours spent travelling
                                 + hours you work to pay for it
                                 - hours of exercise you'd have done anyway
    """
    route["travel_hours"] = route["minutes"] * TRIPS_PER_YEAR / 60
    route["money"] = yearly_cost(route, sell_car)
    route["work_hours"] = route["money"] / pay_per_hour

    route["exercise_hours"] = 0
    if would_exercise:
        active_hours = route["active_minutes"] * TRIPS_PER_YEAR / 60
        exercise = active_hours * EXERCISE_SHARE[route["mode"]]
        route["exercise_hours"] = min(exercise, MAX_EXERCISE_HOURS)

    route["true_hours"] = route["travel_hours"] + route["work_hours"] - route["exercise_hours"]

    route["speed"] = route["km"] * TRIPS_PER_YEAR / max(route["true_hours"], 1)


def on_frontier(route, all_routes, time="minutes"):
    """
    A route is on the 'efficient frontier' if NO other route is both
    at least as fast AND at least as clean (and strictly better at one).
    Those are the only sensible choices; everything else is beaten.
    `time` says which time to compare: "minutes" or "true_hours".
    """
    for other in all_routes:
        if other is route:
            continue
        as_fast = other[time] <= route[time]
        as_clean = other["co2_year"] <= route["co2_year"]
        strictly_better = (other[time] < route[time]
                           or other["co2_year"] < route["co2_year"])
        if as_fast and as_clean and strictly_better:
            return False
    return True


def pick_recommendation(routes, car):
    """The cleanest frontier route that's no more than 15 minutes slower than driving."""
    options = [r for r in routes
               if r["frontier"] and r["mode"] != "Car"
               and r["minutes"] <= car["minutes"] + 15]
    if not options:
        options = [r for r in routes if r["frontier"] and r["mode"] != "Car"]
    return min(options, key=lambda r: (r["co2_year"], r["minutes"]))


def print_table(routes, best, car):
    print()
    print(f"{'Mode':<8}{'Time':>9}{'km':>7}{'CO2/year':>12}{'Cost/year':>12}  Frontier")
    print("-" * 60)
    for r in sorted(routes, key=lambda r: r["minutes"]):
        star = "  <- yes" if r["frontier"] else ""
        cost = "£" + format(r["cost_year"], ".0f")
        print(f"{r['mode']:<8}{r['minutes']:>6.0f} min{r['km']:>7.1f}"
              f"{r['co2_year']:>9.0f} kg{cost:>12}{star}")

    saved = car["co2_year"] - best["co2_year"]
    money = car["cost_year"] - best["cost_year"]
    extra = best["minutes"] - car["minutes"]
    print()
    print(f"RECOMMENDED: {best['mode']}")
    print(f"  saves {saved:.0f} kg of CO2 a year (about what "
          f"{saved / 22:.0f} trees soak up in a year)")
    print(f"  saves £{money:.0f} a year")
    if extra <= 0:
        print(f"  and it's {-extra:.0f} min FASTER than driving")
    else:
        print(f"  costs you {extra:.0f} extra min each way")
    print()


def draw_chart(routes):
    """Time vs CO2 chart, with the efficient frontier drawn as a line."""
    plt.figure(figsize=(8, 5))
    for r in routes:
        plt.scatter(r["minutes"], r["co2_year"], s=140,
                    color=MODES[r["mode"]]["colour"], zorder=3)
        plt.annotate(r["mode"], (r["minutes"], r["co2_year"]),
                     xytext=(8, 6), textcoords="offset points")

    frontier = sorted([r for r in routes if r["frontier"]], key=lambda r: r["minutes"])
    plt.plot([r["minutes"] for r in frontier], [r["co2_year"] for r in frontier],
             "--", color="green", label="Efficient frontier")

    plt.xlabel("Journey time, one way (minutes)")
    plt.ylabel("CO2 per year (kg)")
    plt.title("The efficient frontier of your commute")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.savefig("frontier.png", dpi=150, bbox_inches="tight")
    print("Chart saved as frontier.png")
    plt.show()


def draw_map(routes, home, office, home_label, office_label, best):
    """Map with every route, plus a 'race' you can play with the slider."""
    middle = [(home[1] + office[1]) / 2, (home[0] + office[0]) / 2]
    m = folium.Map(location=middle, zoom_start=13, tiles="OpenStreetMap")

    for r in routes:
        folium.PolyLine(
            [[p[1], p[0]] for p in r["points"]],
            color=MODES[r["mode"]]["colour"],
            weight=7 if r is best else 4,
            opacity=0.9 if r is best else 0.45,
            tooltip=f"{r['mode']}: {r['minutes']:.0f} min, {r['co2_year']:.0f} kg CO2/year",
        ).add_to(m)

    folium.Marker([home[1], home[0]], tooltip="Home: " + home_label,
                  icon=folium.Icon(color="gray")).add_to(m)
    folium.Marker([office[1], office[0]], tooltip="Office: " + office_label,
                  icon=folium.Icon(color="green")).add_to(m)

    start = datetime(2026, 1, 1, 8, 0)
    race = []
    for r in routes:
        points = r["points"][::max(1, len(r["points"]) // 120)]
        times = [(start + timedelta(minutes=r["minutes"] * i / (len(points) - 1))).isoformat()
                 for i in range(len(points))]
        race.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": points},
            "properties": {"times": times,
                           "style": {"color": MODES[r["mode"]]["colour"], "weight": 6}},
        })
    TimestampedGeoJson({"type": "FeatureCollection", "features": race},
                       period="PT1M", transition_time=150, auto_play=False,
                       add_last_point=True, loop=False).add_to(m)

    rows = "".join(
        f"<div><span style='color:{MODES[r['mode']]['colour']}'>&#9632;</span> "
        f"{r['mode']}: {r['minutes']:.0f} min, {r['co2_year']:.0f} kg/yr</div>"
        for r in sorted(routes, key=lambda r: r["minutes"]))
    box = ("<div style='position:fixed;top:12px;right:12px;z-index:9999;background:white;"
           "padding:10px 14px;border-radius:8px;font:14px sans-serif;"
           "box-shadow:0 1px 6px rgba(0,0,0,.25)'><b>Recommended: "
           f"{best['mode']}</b>{rows}"
           "<div style='color:#666;margin-top:6px'>Press play (bottom left) to race them</div></div>")
    m.get_root().html.add_child(folium.Element(box))

    m.save("map.html")
    print("Map saved as map.html")
    webbrowser.open("file://" + os.path.abspath("map.html"))


def main():
    if DEMO:
        print("DEMO mode: no key found in api_key.txt, so routes are straight lines.")
        print("Paste your OpenRouteService key into api_key.txt to get real routes.\n")

    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            cache = json.load(f)

    home, home_label = ask_for_address("Home address or postcode: ", cache)
    office, office_label = ask_for_address("Office address or postcode: ", cache)

    routes = []
    for mode in MODES:
        key = f"route|{home_label}|{office_label}|{mode}"
        print(f"Getting {mode} route...")
        if key not in cache:
            try:
                cache[key] = get_route(home, office, mode)
            except Exception as error:
                print(f"  Couldn't get the {mode} route: {error}")
                return
        points, km, minutes = cache[key]
        routes.append(score(mode, points, km, minutes))

    if not DEMO:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)

    for r in routes:
        r["frontier"] = on_frontier(r, routes)

    car = next(r for r in routes if r["mode"] == "Car")
    best = pick_recommendation(routes, car)

    print_table(routes, best, car)
    draw_map(routes, home, office, home_label, office_label, best)
    draw_chart(routes)


if __name__ == "__main__":
    main()
