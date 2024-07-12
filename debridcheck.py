# -*- coding: utf-8 -*-
##-- all credits to Tikipeter --##
##-- Please retain this credit  --##
##-- Edited by MrBlamo for the Asguard addon --##

import abc, logging, os, sys, time, datetime
import sqlite3
import json, requests
import cache, utils
import kodi
import urllib3
from asguard_lib import utils2, control
import xbmc, xbmcaddon, xbmcgui, xbmcvfs

from threading import Thread
logging.basicConfig(level=logging.DEBUG)

addonInfo = xbmcaddon.Addon().getAddonInfo
progressDialogBG = xbmcgui.DialogProgressBG()
makeFile = xbmcvfs.mkdir
dataPath = xbmcvfs.translatePath(addonInfo('profile'))

__r_url__ = xbmcaddon.Addon('script.module.resolveurl')
rd_enabled = (__r_url__.getSetting('RealDebridResolver_enabled') == 'true' and __r_url__.getSetting('RealDebridResolver_token') != '')
ad_enabled = (__r_url__.getSetting('AllDebridResolver_enabled') == 'true' and __r_url__.getSetting('AllDebridResolver_token') != '')
pm_enabled = (__r_url__.getSetting('PremiumizeMeResolver_enabled') == 'true' and __r_url__.getSetting('PremiumizeMeResolver_token') != '')
progressDialog = progressDialogBG

abstractstaticmethod = abc.abstractmethod
class abstractclassmethod(classmethod):
    """
    A decorator indicating abstract classmethods.
    Similar to abstractmethod.
    """
    __isabstractmethod__ = True

    def __init__(self, callable):
        callable.__isabstractmethod__ = True
        super(abstractclassmethod, self).__init__(callable)

class RDapi:
    """
    Real-Debrid API handler class.
    Handles authentication and cache checking for Real-Debrid.
    """
    def __init__(self):
        __metaclass__ = abc.ABCMeta
        self.token = __r_url__.getSetting('RealDebridResolver_token')
        self.client_id = __r_url__.getSetting('RealDebridResolver_client_id')
        self.client_secret = __r_url__.getSetting('RealDebridResolver_client_secret')
        self.refresh = __r_url__.getSetting('RealDebridResolver_refresh')
        self.rest_base_url = 'https://api.real-debrid.com/rest/1.0/'
        self.oauth_url = 'https://api.real-debrid.com/oauth/v2/'

    def _get(self, url):
        """
        Perform a GET request to the Real-Debrid API.
        Refreshes token if necessary.

        :param url: The endpoint URL to request.
        :return: The response from the API.
        """
        original_url = url
        url = self.rest_base_url + url
        if '?' not in url:
            url += "?auth_token=%s" % self.token
        else:
            url += "&auth_token=%s" % self.token
        response = requests.get(url).text
        if 'bad_token' in response or 'Bad Request' in response:
            self.refreshToken()
            response = self._get(original_url)
        try: resp = utils.json_loads_as_str(response)
        except: resp = utils._byteify(response)
        return resp

    def refreshToken(self):
        data = {'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': self.refresh,
                'grant_type': 'http://oauth.net/grant_type/device/1.0'}
        url = self.oauth_url + 'token'
        response = requests.post(url, data=data)
        response = json.loads(response.text)
        if 'access_token' in response: self.token = response['access_token']
        if 'refresh_token' in response: self.refresh = response['refresh_token']
        __r_url__.setSetting('RealDebridResolver_token', self.token)
        __r_url__.setSetting('RealDebridResolver_refresh', self.refresh)

    def check_cache(self, hashes):
        """
        Check the cache status of given torrent hashes.

        :param hashes: List of torrent hashes to check.
        :return: The response from the API.
        """
        hash_string = '/'.join(hashes)
        url = 'torrents/instantAvailability/%s' % hash_string
        response = self._get(url)
        return response

class ADapi:
    """
    AllDebrid API handler class.
    Handles cache checking for AllDebrid.
    """
    def __init__(self):
        __metaclass__ = abc.ABCMeta
        self.base_url = 'https://api.alldebrid.com/v4/'
        self.token = __r_url__.getSetting('AllDebridResolver_token')
        self.user_agent = 'Asguard'

    def check_cache(self, hashes):
        data = {'magnets[]': hashes}
        result = self._post('magnet/instant', data)
        logging.debug(f"ADapi check_cache result: {result}")
        return result

    def _post(self, url, data={}):
        """
        Perform a POST request to the AllDebrid API.

        :param url: The endpoint URL to request.
        :param data: The data to send in the POST request.
        :return: The response from the API.
        """
        result = None
        if self.token == '':
            logging.error("ADapi token is empty")
            return None
        url = self.base_url + url + '?agent=%s&apikey=%s' % (self.user_agent, self.token)
        logging.debug(f"ADapi POST URL: {url}")
        resp = requests.post(url, data=data).json()
        logging.debug(f"ADapi POST response: {resp}")
        if resp.get('status') == 'success':
            if 'data' in resp:
                resp = resp['data']['magnets']
        return resp

class PMapi:
    def __init__(self):
        __metaclass__ = abc.ABCMeta
        self.base_url = 'https://www.premiumize.me/api/'
        self.token = __r_url__.getSetting('PremiumizeMeResolver_token')

    def check_cache(self, hashes):
        url = "cache/check"
        data = {'items[]': hashes}
        response = self._post(url, data)
        return response

    def _post(self, url, data={}):
        """
        Perform a POST request to the Premiumize.me API.

        :param url: The endpoint URL to request.
        :param data: The data to send in the POST request.
        :return: The response from the API.
        """
        if self.token == '' and not 'token' in url: return None
        headers = {'Authorization': 'Bearer %s' % self.token}
        if not 'token' in url: url = self.base_url + url
        response = requests.post(url, data=data, headers=headers).text
        try: resp = utils.json_loads_as_str(response)
        except: resp = utils._byteify(response)
        return resp

class DebridCheck:
    """
    Main class to handle debrid cache checking.
    Manages the checking process for Real-Debrid, AllDebrid, and Premiumize.me.
    """
    def __init__(self):
        __metaclass__ = abc.ABCMeta
        self.db_cache = DebridCache()
        self.db_cache.check_database()
        self.cached_hashes = []
        self.main_threads = []
        self.rd_cached_hashes = []
        self.rd_hashes_unchecked = []
        self.rd_query_threads = []
        self.rd_process_results = []
        self.ad_cached_hashes = []
        self.ad_hashes_unchecked = []
        self.ad_query_threads = []
        self.ad_process_results = []
        self.pm_cached_hashes = []
        self.pm_hashes_unchecked = []
        self.pm_process_results = []
        self.starting_debrids = []
        self.starting_debrids_display = []

    def run(self, hash_list):
        """
        Run the debrid cache checking process.

        :param hash_list: List of torrent hashes to check.
        :return: Tuple of cached hashes for Real-Debrid, AllDebrid, and Premiumize.me.
        """
        xbmc.sleep(500)
        self.hash_list = hash_list
        self._query_local_cache(self.hash_list)
        if rd_enabled:
            self.rd_cached_hashes = [str(i[0]) for i in self.cached_hashes if str(i[1]) == 'rd' and str(i[2]) == 'True']
            self.rd_hashes_unchecked = [i for i in self.hash_list if not any([h for h in self.cached_hashes if str(h[0]) == i and str(h[1]) =='rd'])]
            if self.rd_hashes_unchecked: self.starting_debrids.append(('Real-Debrid', self.RD_cache_checker))
        if ad_enabled:
            self.ad_cached_hashes = [str(i[0]) for i in self.cached_hashes if str(i[1]) == 'ad' and str(i[2]) == 'True']
            self.ad_hashes_unchecked = [i for i in self.hash_list if not any([h for h in self.cached_hashes if str(h[0]) == i and str(h[1]) =='ad'])]
            if self.ad_hashes_unchecked: self.starting_debrids.append(('AllDebrid', self.AD_cache_checker))
        if pm_enabled:
            self.pm_cached_hashes = [str(i[0]) for i in self.cached_hashes if str(i[1]) == 'pm' and str(i[2]) == 'True']
            self.pm_hashes_unchecked = [i for i in self.hash_list if not any([h for h in self.cached_hashes if str(h[0]) == i and str(h[1]) =='pm'])]
            if self.pm_hashes_unchecked: self.starting_debrids.append(('Premiumize.me', self.PM_cache_checker))
        if self.starting_debrids:
            for i in list(range(len(self.starting_debrids))):
                self.main_threads.append(Thread(target=self.starting_debrids[i][1]))
                self.starting_debrids_display.append((self.main_threads[i].getName(), self.starting_debrids[i][0]))
            [i.start() for i in self.main_threads]
            [i.join() for i in self.main_threads]
            self.debrid_check_dialog()
        xbmc.sleep(500)
        return self.rd_cached_hashes, self.ad_cached_hashes, self.pm_cached_hashes

    def debrid_check_dialog(self):
        timeout = 20
        progressDialog.create('Checking debrid cache, please wait..')
        #progressDialog.update(0)
        start_time = time.time()
        for i in list(range(0, 200)):
            try:
                if xbmc.abortRequested(): return sys.exit()
                alive_threads = [x.getName() for x in self.main_threads if x.is_alive() is True]
                remaining_debrids = [x[1] for x in self.starting_debrids_display if x[0] in alive_threads]
                current_time = time.time()
                current_progress = current_time - start_time
                try:
                    percent = int((current_progress/float(timeout))*100)
                    msg = 'Remaining Debrid Checks: %s' % ', '.join(remaining_debrids).upper()
                    progressDialog.update(percent, message=msg)
                except: pass
                time.sleep(0.2)
                if len(alive_threads) == 0 or progressDialog.isFinished(): break
            except Exception:
                pass
        try:
            progressDialog.close()
        except Exception:
            pass
        xbmc.sleep(200)

    def RD_cache_checker(self):
        hash_chunk_list = list(utils2.chunks(self.rd_hashes_unchecked, 100))
        for item in hash_chunk_list: self.rd_query_threads.append(Thread(target=self._rd_lookup, args=(item,)))
        [i.start() for i in self.rd_query_threads]
        [i.join() for i in self.rd_query_threads]
        self._add_to_local_cache(self.rd_process_results, 'rd')

    def AD_cache_checker(self):
        hash_chunk_list = list(utils2.chunks(self.ad_hashes_unchecked, 100))
        for item in hash_chunk_list: self.ad_query_threads.append(Thread(target=self._ad_lookup, args=(item,)))
        [i.start() for i in self.ad_query_threads]
        [i.join() for i in self.ad_query_threads]
        self._add_to_local_cache(self.ad_process_results, 'ad')

    def PM_cache_checker(self):
        self._pm_lookup(self.pm_hashes_unchecked)
        self._add_to_local_cache(self.pm_process_results, 'pm')

    def _rd_lookup(self, chunk):
        """
        Perform the Real-Debrid cache lookup for a chunk of hashes.

        :param chunk: List of torrent hashes to check.
        """
        try:
            rd_cache_get = RDapi().check_cache(chunk)
            for h in chunk:
                cached = 'False'
                if h in rd_cache_get:
                    info = rd_cache_get[h]
                    if isinstance(info, dict) and len(info.get('rd')) > 0:
                        self.rd_cached_hashes.append(h)
                        cached = 'True'
                self.rd_process_results.append((h, cached))
        except: pass

    def _ad_lookup(self, hash_list):
        """
        Perform the AllDebrid cache lookup for a list of hashes.

        :param hash_list: List of torrent hashes to check.
        """
        try:
            ad_cache = ADapi().check_cache(hash_list)
            if isinstance(ad_cache, list):
                for i in ad_cache:
                    cached = 'False'
                    if i['instant'] == True:
                        self.ad_cached_hashes.append(i['hash'])
                        cached = 'True'
                    self.ad_process_results.append((i['hash'], cached))
            else:
                for i in hash_list: self.ad_process_results.append((i, 'False'))
        except: pass

    def _pm_lookup(self, hash_list):
        try:
            pm_cache = PMapi().check_cache(hash_list)['response']
            for c, h in enumerate(hash_list):
                cached = 'False'
                if pm_cache[c] is True:
                    self.pm_cached_hashes.append(h)
                    cached = 'True'
                self.pm_process_results.append((h, cached))
        except: pass

    def _query_local_cache(self, _hash):
        """
        Query the local cache for the given hashes.

        :param _hash: List of torrent hashes to check.
        """
        cached = self.db_cache.get_all(_hash)
        if cached:
            self.cached_hashes = cached

    def _add_to_local_cache(self, _hash, debrid):
        self.db_cache.set_many(_hash, debrid)

class DebridCache:
    """
    Class to handle local caching of debrid data.
    Uses SQLite for storage.
    """
    def __init__(self):
        __metaclass__ = abc.ABCMeta
        self.dbfile = os.path.join(dataPath, 'debridcache.db')

    def get_all(self, hash_list):
        result = None
        try:
            current_time = self._get_timestamp(datetime.datetime.now())
            dbcon = sqlite3.connect(self.dbfile, timeout=40.0)
            dbcur = dbcon.cursor()
            dbcur.execute('SELECT * FROM debrid_data WHERE hash in ({0})'.format(', '.join('?' for _ in hash_list)), hash_list)
            cache_data = dbcur.fetchall()
            if cache_data:
                if cache_data[0][3] > current_time:
                    result = cache_data
                else:
                    self.remove_many(cache_data)
        except: pass
        return result

    def remove_many(self, old_cached_data):
        try:
            old_cached_data = [(str(i[0]),) for i in old_cached_data]
            dbcon = sqlite3.connect(self.dbfile, timeout=40.0)
            dbcur = dbcon.cursor()
            dbcur.executemany("DELETE FROM debrid_data WHERE hash=?", old_cached_data)
            dbcon.commit()
        except: pass

    def set_many(self, hash_list, debrid, expiration=datetime.timedelta(hours=1)):
        try:
            expires = self._get_timestamp(datetime.datetime.now() + expiration)
            insert_list = [(i[0], debrid, i[1], expires) for i in hash_list]
            dbcon = sqlite3.connect(self.dbfile, timeout=40.0)
            dbcur = dbcon.cursor()
            dbcur.executemany("INSERT INTO debrid_data VALUES (?, ?, ?, ?)", insert_list)
            dbcon.commit()
        except: pass

    def check_database(self):
        if not os.path.exists(dataPath):
            makeFile(dataPath)
        dbcon = sqlite3.connect(self.dbfile)
        dbcur = dbcon.cursor()
        dbcur.execute("""CREATE TABLE IF NOT EXISTS debrid_data
                      (hash text not null, debrid text not null, cached text, expires integer, unique (hash, debrid))
                        """)
        dbcon.close()

    def clear_database(self):
        try:
            dbcon = sqlite3.connect(self.dbfile)
            dbcur = dbcon.cursor()
            dbcur.execute("DELETE FROM debrid_data")
            dbcur.execute("VACUUM")
            dbcon.commit()
            dbcon.close()
            return 'success'
        except: return 'failure'

    def _get_timestamp(self, date_time):
        return int(time.mktime(date_time.timetuple()))
