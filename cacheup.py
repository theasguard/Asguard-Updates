-- tmdb_cache.sql
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY,
    tmdb_id INTEGER UNIQUE,
    title TEXT,
    year INTEGER,
    data TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tvshows (
    id INTEGER PRIMARY KEY,
    tmdb_id INTEGER UNIQUE,
    title TEXT,
    year INTEGER,
    data TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

modify to use cache 

import requests
import db_utils

API_KEY = 'your_tmdb_api_key'
BASE_URL = 'https://api.themoviedb.org/3'

def get_movie(tmdb_id):
    cached_movie = db_utils.get_movie(tmdb_id)
    if cached_movie:
        return cached_movie

    response = requests.get(f"{BASE_URL}/movie/{tmdb_id}", params={'api_key': API_KEY})
    if response.status_code == 200:
        movie_data = response.json()
        db_utils.cache_movie(tmdb_id, movie_data['title'], movie_data['release_date'][:4], movie_data)
        return movie_data
    return None

def get_tvshow(tmdb_id):
    cached_tvshow = db_utils.get_tvshow(tmdb_id)
    if cached_tvshow:
        return cached_tvshow

    response = requests.get(f"{BASE_URL}/tv/{tmdb_id}", params={'api_key': API_KEY})
    if response.status_code == 200:
        tvshow_data = response.json()
        db_utils.cache_tvshow(tmdb_id, tvshow_data['name'], tvshow_data['first_air_date'][:4], tvshow_data)
        return tvshow_data
    return None
