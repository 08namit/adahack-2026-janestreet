# Green Route

Our submission to the AdaHack 2026 Jane Street challenge.

## Problem Statement

**Sustainable Transport**, the AdaHack 2026 Jane Street challenge.

> A sustainable world is one in which our environmental systems and societies flourish, natural resources are able to replenish themselves, and people are able to live healthy and secure lives. Sustainability can be overlooked in favour of technological advancements, so we should consider how to fit it into our own projects.

**The challenge:** Jane Street workers usually travel to the office by car. Build a program that encourages them to take a more sustainable route instead.

Transport produces 13.7% of global greenhouse gas emissions, and sustainable transport also protects people from volatile fuel prices.

## Our Approach

Telling people to drive less rarely works, so we show them what driving actually costs them. For any commute, Green Route compares car, bus, bike, e-bike and walking on time, money and CO₂, then converts everything into one number: the hours of your life each option costs per year. The greener options often win on that measure too.

## Running the App

```
pip install requests folium matplotlib tkintermapview pillow
```

Desktop app:

```
python green_route_app.py
```

Terminal version, which prints a table and saves `map.html` and `frontier.png`:

```
python green_route.py
```

Put an [OpenRouteService](https://openrouteservice.org) key in `api_key.txt` for real routes. Without one, routes are straight lines.

## Method

A year is 460 trips (there and back, 5 days a week, 46 weeks).

**Time.** Route times from OpenRouteService assume empty roads, so:
- Car: × traffic factor, + 3 min parking
- Bus: × traffic factor × 1.3 for stops, + 8 min wait
- Traffic factor: 1.79 at 7–9am, 1.87 at 4–6pm, 1.58 other daytime, 1.0 at night, each ÷ 1.14 (the service's times already include some delay)
- Time is the average of an 8am and a 5pm journey.

**CO₂ per year** = km × emission factor × 460

| | Car | Bus | E-bike | Bike | Walk |
| --- | --- | --- | --- | --- | --- |
| kg CO₂ per km | 0.164 | 0.1 | 0.006 | 0 | 0 |

**Cost per year**
- Car: £0.106 per km, plus £2470 a year to own the car
- Bus: £2.40 a trip, capped at the £760 annual ticket
- Bike: £500 over 5 years + £100 servicing = £200
- E-bike: £2000 over 5 years + £150 servicing + £10 charging = £560
- Walk: £0

**True time** (hours a year) = travel time + hours worked to pay for it − exercise gained
- Pay: £2400 a month take-home over a 37.5-hour week, about £16.70 an hour
- Exercise: all of a bike or walk trip, half of an e-bike trip, capped at 2.5 hours a week

**Efficient frontier.** Options that no other option beats on both time and CO₂.

**Recommendation.** The app picks the lowest true time. The terminal version picks the cleanest frontier option that's at most 15 minutes slower than driving.

## Files

| File | Contents |
| --- | --- |
| `green_route.py` | Place search, routing, and the time, cost, CO₂ and true-time maths |
| `green_route_app.py` | Desktop app: search boxes, route cards and map |
| `safe_map.py` | Map widget that works with newer versions of tkinter |
