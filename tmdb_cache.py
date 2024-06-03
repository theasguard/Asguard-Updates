import sqlite3
import os
import json
import time

DB_PATH = os.path.join(xbmc.translatePath("special://database"), 'tmdb_cache.db')

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        with open('tmdb_cache.sql') as f:
            conn.executescript(f.read())

def get_movie(tmdb_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM movies WHERE tmdb_id = ?", (tmdb_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

def cache_movie(tmdb_id, title, year, data):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO movies (tmdb_id, title, year, data, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (tmdb_id, title, year, json.dumps(data), time.time()))
        conn.commit()

def get_tvshow(tmdb_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM tvshows WHERE tmdb_id = ?", (tmdb_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

def cache_tvshow(tmdb_id, title, year, data):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO tvshows (tmdb_id, title, year, data, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (tmdb_id, title, year, json.dumps(data), time.time()))
        conn.commit()
