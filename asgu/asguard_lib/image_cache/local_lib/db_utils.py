"""
    Image Cache Module
    Copyright (C) 2016 tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import kodi
import threading
import json
import os
import requests
from sqlite3 import dbapi2 as db_lib

def __enum(**enums):
    return type('Enum', (), enums)

DB_TYPES = __enum(MYSQL='mysql', SQLITE='sqlite')

class DBCache(object):
    TMDB_API_KEY = kodi.get_setting('tmdb_key')

    def __init__(self, db_path=None):
        self.db_path = os.path.join(os.path.expanduser('~'), 'tmdb_cache.db') if db_path is None else db_path
        self.db_type = DB_TYPES.SQLITE
        self.db = None
        self.__create_db()
        self.__execute('CREATE TABLE IF NOT EXISTS api_cache (tmdb_id INTEGER NOT NULL, object_type CHAR(1) NOT NULL, data TEXT, overview TEXT, PRIMARY KEY(tmdb_id, object_type))')
        self.__execute('CREATE TABLE IF NOT EXISTS db_info (setting TEXT, value TEXT, PRIMARY KEY(setting))')
        
    def __create_db(self):
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        if not os.path.exists(self.db_path):
            open(self.db_path, 'w').close()
            
    def close(self):
        if self.db:
            self.db.close()
    
    def get_movie(self, tmdb_id):
        return self.__get_object(tmdb_id, 'M')
        
    def get_tvshow(self, tmdb_id):
        return self.__get_object(tmdb_id, 'T')
        
    def get_person(self, tmdb_id):
        return self.__get_object(tmdb_id, 'P')
        
    def __get_object(self, tmdb_id, object_type):
        sql = 'SELECT data, overview FROM api_cache WHERE tmdb_id = ? AND object_type = ?'
        rows = self.__execute(sql, (tmdb_id, object_type))
        if rows:
            data = json.loads(rows[0][0])
            overview = rows[0][1]
            return {'data': data, 'overview': overview}
        else:
            return {}
            
    def update_movie(self, tmdb_id, js_data):
        overview = js_data.get('overview', '')
        self.__update_object(tmdb_id, 'M', js_data, overview)

    def update_tvshow(self, tmdb_id, js_data):
        overview = js_data.get('overview', '')
        self.__update_object(tmdb_id, 'T', js_data, overview)

    def update_person(self, tmdb_id, js_data):
        overview = js_data.get('overview', '')
        self.__update_object(tmdb_id, 'P', js_data, overview)

    def __update_object(self, tmdb_id, object_type, js_data, overview):
        self.__execute('REPLACE INTO api_cache (tmdb_id, object_type, data, overview) VALUES (?, ?, ?, ?)', 
                    (tmdb_id, object_type, json.dumps(js_data), overview))
        
    def get_setting(self, setting):
        sql = 'SELECT value FROM db_info WHERE setting = ?'
        rows = self.__execute(sql, (setting,))
        if rows:
            return rows[0][0]

    def set_setting(self, setting, value):
        sql = 'REPLACE INTO db_info (setting, value) VALUES (?, ?)'
        self.__execute(sql, (setting, value))

    def execute(self, sql, params=None):
        return self.__execute(sql, params)
    
    def __get_db_connection(self):
        worker_id = threading.get_ident()
        # create a connection if we don't have one or it was created in a different worker
        if self.db is None or self.worker_id != worker_id:
            self.db = db_lib.connect(self.db_path)
            self.db.text_factory = str
            self.worker_id = worker_id
        return self.db

    def __execute(self, sql, params=None):
        if params is None: params = []
        rows = None
        sql = self.__format(sql)
        is_read = self.__is_read(sql)
        db_con = self.__get_db_connection()
        cur = db_con.cursor()
        cur.execute(sql, params)
        if is_read:
            rows = cur.fetchall()
        cur.close()
        db_con.commit()
        return rows

    # apply formatting changes to make sql work with a particular db driver
    def __format(self, sql):
        if self.db_type == DB_TYPES.MYSQL:
            sql = sql.replace('?', '%s')

        if self.db_type == DB_TYPES.SQLITE:
            if sql[:7] == 'REPLACE':
                sql = 'INSERT OR ' + sql

        return sql

    def __is_read(self, sql):
        fragment = sql[:6].upper()
        return fragment[:6] == 'SELECT' or fragment[:4] == 'SHOW'

    def fetch_and_store_movie(self, tmdb_id):
        url = f'https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_movie(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch movie data: {response.status_code}")

    def fetch_and_store_tvshow(self, tmdb_id):
        url = f'https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_tvshow(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch TV show data: {response.status_code}")

    def fetch_and_store_person(self, tmdb_id):
        url = f'https://api.themoviedb.org/3/person/{tmdb_id}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_person(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch person data: {response.status_code}")