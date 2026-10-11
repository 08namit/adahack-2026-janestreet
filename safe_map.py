"""
A map you can put in a tkinter window.

You don't need to read this file to understand the app.

Why it exists: the tkintermapview library loads map pictures in the
background in a way that crashes newer versions of tkinter. This makes a
fixed version of its map, called Map, that does the risky step safely.
"""

import io
import threading

import requests
from PIL import Image, ImageTk
from tkintermapview import TkinterMapView


class Map(TkinterMapView):

    def __init__(self, *args, **kwargs):
        self.downloaded = {}
        super().__init__(*args, **kwargs)

    def request_image(self, zoom, x, y, db_cursor=None):
        name = f"{zoom}{x}{y}"
        if name not in self.downloaded:
            url = self.tile_server.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
            try:
                answer = requests.get(url, headers={"User-Agent": "GreenRoute"}, timeout=20)
                picture = Image.open(io.BytesIO(answer.content))
                picture.load()
            except Exception:
                return self.empty_tile_image
            self.downloaded[name] = picture
        return self.downloaded[name]

    def get_tile_image_from_cache(self, zoom, x, y):
        name = f"{zoom}{x}{y}"
        if name in self.tile_image_cache:
            return self.tile_image_cache[name]
        if name not in self.downloaded:
            return False
        if threading.current_thread() is not threading.main_thread():
            return self.downloaded[name]
        self.tile_image_cache[name] = ImageTk.PhotoImage(self.downloaded[name])
        return self.tile_image_cache[name]

    def update_canvas_tile_images(self):
        while self.image_load_queue_results and self.running:
            (zoom, x, y), tile, picture = self.image_load_queue_results.pop(0)
            if zoom == round(self.zoom):
                if isinstance(picture, Image.Image):
                    picture = self.get_tile_image_from_cache(zoom, x, y)
                tile.set_image(picture)
        if self.running:
            self.after(10, self.update_canvas_tile_images)
