"""
GREEN ROUTE  -  every way to get there, side by side.

Type where you're starting and where you're going, press Enter, and click
the right place in the list. Every way of travelling appears as a card,
with the best one highlighted. Click a card to see that route on the map.

All the route finding and maths is in green_route.py. This file is just the window.

Run it with:   python green_route_app.py
"""

import tkinter as tk

import green_route as gr
from safe_map import Map


BACKGROUND = "#f4f5f7"
WHITE = "#ffffff"
TEXT = "#1d2433"
GREY = "#6b7280"
LINE = "#e3e6eb"
GREEN = "#1e9e5a"
FONT = "Helvetica"

PAY_PER_HOUR = 2400 * 12 / gr.HOURS_WORKED_PER_YEAR
LEAVE_HOURS = (8, 17)

places = {}
matches = {}
boxes = {}
lists = {}
routes = []
cards = {}


def search(which):
    """Look up what was typed, and show the matches in a list under the box."""
    say("Searching...")
    window.update()
    try:
        matches[which] = gr.search_addresses(boxes[which].get())
    except Exception as error:
        say(f"Couldn't search: {error}")
        return

    lists[which].delete(0, tk.END)
    for match in matches[which]:
        lists[which].insert(tk.END, match[1])

    if len(matches[which]) == 0:
        say("No matches. Try a postcode.")
    else:
        lists[which].pack(fill="x", pady=(4, 0))
        say("Click the right place.")


def pick(which):
    """Remember the place that was clicked, and find routes once we have both ends."""
    chosen = lists[which].curselection()
    if len(chosen) == 0:
        return
    places[which] = matches[which][chosen[0]]
    lists[which].pack_forget()

    boxes[which].delete(0, tk.END)
    boxes[which].insert(0, places[which][1].split(",")[0])
    say("")

    map_view.delete_all_marker()
    for name in places:
        lon, lat = places[name][0]
        colour = TEXT if name == "from" else GREEN
        map_view.set_marker(lat, lon, marker_color_outside=colour, marker_color_circle=WHITE)
    lon, lat = places[which][0]
    map_view.set_position(lat, lon)

    if "from" in places and "to" in places:
        find_routes()


def find_routes():
    say("Finding routes...")
    window.update()

    start = places["from"][0]
    end = places["to"][0]
    checked = gr.checked_times(places["from"][1], places["to"][1])
    routes.clear()
    for mode in gr.MODES:
        try:
            points, km, minutes = gr.get_route(start, end, mode)
        except Exception as error:
            say(f"Couldn't get the {mode} route: {error}")
            return
        route = gr.score(mode, points, km, minutes, LEAVE_HOURS)
        if checked is not None:
            route["minutes"] = checked[mode]
            route["active_minutes"] = checked[mode]
        gr.add_true_time(route, PAY_PER_HOUR, True, True)
        routes.append(route)

    say("")
    show_cards()
    zoom_to_routes()
    select(best_route()["mode"])


def best_route():
    """The best option: the one that costs the fewest hours of your life a year,
    once you count travel time, the work it takes to pay for it, and exercise."""
    best = routes[0]
    for route in routes:
        if route["true_hours"] < best["true_hours"]:
            best = route
    return best


def find_mode(mode):
    for route in routes:
        if route["mode"] == mode:
            return route


def show_cards():
    """Make one card for each way of travelling, quickest first."""
    for card in cards.values():
        card.destroy()
    cards.clear()

    best = best_route()
    car = find_mode("Car")

    for route in sorted(routes, key=minutes_of):
        mode = route["mode"]
        card = tk.Frame(card_area, bg=WHITE, highlightthickness=2, highlightbackground=LINE)
        card.pack(fill="x", pady=4)

        tk.Frame(card, bg=gr.MODES[mode]["colour"], width=6).pack(side="left", fill="y")
        inside = tk.Frame(card, bg=WHITE, padx=12, pady=8)
        inside.pack(side="left", fill="x", expand=True)

        tk.Label(inside, text=f"{route['minutes']:.0f} min", font=(FONT, 20, "bold"),
                 bg=WHITE, fg=TEXT).pack(side="right")
        tk.Label(inside, text=mode, font=(FONT, 15, "bold"), bg=WHITE, fg=TEXT).pack(anchor="w")
        tk.Label(inside, text=f"£{route['money']:,.0f} a year  ·  {route['co2_year']:.0f} kg CO₂",
                 font=(FONT, 12), bg=WHITE, fg=GREY).pack(anchor="w")

        if route is best and route is not car:
            hours_back = car["true_hours"] - best["true_hours"]
            tk.Label(inside, text=f"★ Best  ·  gives you back {hours_back:.0f} hours a year",
                     font=(FONT, 12, "bold"), bg=WHITE, fg=GREEN).pack(anchor="w", pady=(2, 0))

        everything = [card, inside] + inside.winfo_children()
        for widget in everything:
            widget.mode = mode
            widget.bind("<Button-1>", card_clicked)

        cards[mode] = card


def minutes_of(route):
    """Used by sorted() above, to put the quickest route first."""
    return route["minutes"]


def card_clicked(event):
    select(event.widget.mode)


def select(mode):
    """Highlight one route: bold on the map and outlined in the list. The rest go grey."""
    map_view.delete_all_path()
    for route in routes:
        if route["mode"] != mode:
            map_view.set_path(flip(route["points"]), color="#b9bfc9", width=3)
    chosen = find_mode(mode)
    map_view.set_path(flip(chosen["points"]), color=gr.MODES[mode]["colour"], width=6)

    for name in cards:
        if name == mode:
            cards[name].config(highlightbackground=gr.MODES[name]["colour"])
        else:
            cards[name].config(highlightbackground=LINE)


def flip(points):
    """The route service gives [longitude, latitude]; the map wants (latitude, longitude)."""
    flipped = []
    for lon, lat in points:
        flipped.append((lat, lon))
    return flipped


def zoom_to_routes():
    """Zoom the map so every route fits."""
    lats = []
    lons = []
    for route in routes:
        for lon, lat in route["points"]:
            lats.append(lat)
            lons.append(lon)
    map_view.fit_bounding_box((max(lats), min(lons)), (min(lats), max(lons)))


def say(message):
    status.config(text=message)


def search_from(event):
    search("from")

def search_to(event):
    search("to")

def pick_from(event):
    pick("from")

def pick_to(event):
    pick("to")


def make_place_box(which, label, search_action, pick_action):
    """A label, a box to type in, and a hidden list of matches."""
    holder = tk.Frame(sidebar, bg=BACKGROUND)
    holder.pack(fill="x", pady=(0, 10))
    tk.Label(holder, text=label, font=(FONT, 11, "bold"), bg=BACKGROUND, fg=GREY).pack(anchor="w")

    boxes[which] = tk.Entry(holder, font=(FONT, 15), relief="flat", bg=WHITE, fg=TEXT, insertbackground=TEXT,
                            highlightthickness=1, highlightbackground=LINE, highlightcolor=GREEN)
    boxes[which].pack(fill="x", ipady=6)
    boxes[which].bind("<Return>", search_action)

    lists[which] = tk.Listbox(holder, height=4, font=(FONT, 12), relief="flat", bg=WHITE, fg=TEXT,
                              highlightthickness=1, highlightbackground=LINE,
                              selectbackground=GREEN, selectforeground=WHITE, exportselection=False)
    lists[which].bind("<<ListboxSelect>>", pick_action)


window = tk.Tk()
window.title("Green Route")
window.geometry("1300x820")
window.configure(bg=BACKGROUND)

sidebar = tk.Frame(window, bg=BACKGROUND, width=400, padx=20, pady=20)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

tk.Label(sidebar, text="Green Route", font=(FONT, 26, "bold"),
         bg=BACKGROUND, fg=GREEN).pack(anchor="w")
tk.Label(sidebar, text="Every way there, side by side.", font=(FONT, 13),
         bg=BACKGROUND, fg=GREY).pack(anchor="w", pady=(0, 18))

make_place_box("from", "FROM", search_from, pick_from)
make_place_box("to", "TO", search_to, pick_to)

status = tk.Label(sidebar, text="Type a place or postcode and press Enter.",
                  font=(FONT, 12), bg=BACKGROUND, fg=GREY, wraplength=360, justify="left")
status.pack(anchor="w", pady=(0, 8))

card_area = tk.Frame(sidebar, bg=BACKGROUND)
card_area.pack(fill="both", expand=True)

map_view = Map(window)
map_view.pack(side="right", fill="both", expand=True)
map_view.set_position(55.9533, -3.1883)
map_view.set_zoom(13)

window.lift()
window.mainloop()
