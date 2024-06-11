"""
    Asguard Addon
    Copyright (C) 2014 tknorris

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
import re
import sys
import xbmc
import xbmcgui
import xbmcaddon
import time
import kodi
import log_utils
import utils
import os
from asguard_lib import salts_utils
from asguard_lib import image_proxy
from asguard_lib import utils2
from asguard_lib.utils2 import i18n
from asguard_lib.constants import MODES
from asguard_lib.db_utils import DB_Connection
from asguard_lib.trakt_api import Trakt_API

logger = log_utils.Logger.get_logger()

class Service(xbmc.Player):
    def __init__(self, *args, **kwargs):
        logger.log('Service: starting...', log_utils.LOGNOTICE)
        self.db_connection = DB_Connection()
        xbmc.Player.__init__(self, *args, **kwargs)
        self.win = xbmcgui.Window(10000)
        self.reset()

    def reset(self):
        logger.log('Service: Resetting...', log_utils.LOGDEBUG)
        self.win.clearProperty('asguard.playing')
        self.win.clearProperty('asguard.playing.trakt_id')
        self.win.clearProperty('asguard.playing.season')
        self.win.clearProperty('asguard.playing.episode')
        self.win.clearProperty('asguard.playing.srt')
        self.win.clearProperty('asguard.playing.trakt_resume')
        self.win.clearProperty('asguard.playing.salts_resume')
        self.win.clearProperty('asguard.playing.library')
        self._from_library = False
        self.tracked = False
        self._totalTime = 999999
        self.trakt_id = None
        self.season = None
        self.episode = None
        self._lastPos = 0

    def onPlayBackStarted(self):
        logger.log('Service: Playback started', log_utils.LOGNOTICE)
        playing = self.win.getProperty('asguard.playing') == 'True'
        self.trakt_id = self.win.getProperty('asguard.playing.trakt_id')
        self.season = self.win.getProperty('asguard.playing.season')
        self.episode = self.win.getProperty('asguard.playing.episode')
        srt_path = self.win.getProperty('asguard.playing.srt')
        trakt_resume = self.win.getProperty('asguard.playing.trakt_resume')
        salts_resume = self.win.getProperty('asguard.playing.salts_resume')
        self._from_library = self.win.getProperty('asguard.playing.library') == 'True'
        if playing:   # Playback is ours
            logger.log('Service: tracking progress...', log_utils.LOGNOTICE)
            self.tracked = True
            if srt_path:
                logger.log('Service: Enabling subtitles: %s' % (srt_path), log_utils.LOGDEBUG)
                self.setSubtitles(srt_path)
            else:
                self.showSubtitles(False)

        self._totalTime = 0
        while self._totalTime == 0:
            try:
                self._totalTime = self.getTotalTime()
            except RuntimeError:
                self._totalTime = 0
                break
            kodi.sleep(1000)

        if salts_resume:
            logger.log("Salts Local Resume: Resume Time: %s Total Time: %s" % (salts_resume, self._totalTime), log_utils.LOGDEBUG)
            self.seekTime(float(salts_resume))
        elif trakt_resume:
            resume_time = float(trakt_resume) * self._totalTime / 100
            logger.log("Salts Trakt Resume: Percent: %s, Resume Time: %s Total Time: %s" % (trakt_resume, resume_time, self._totalTime), log_utils.LOGDEBUG)
            self.seekTime(resume_time)

    def onPlayBackStopped(self):
        logger.log('Service: Playback Stopped', log_utils.LOGNOTICE)
        if self.tracked:
            # clear the playlist if SALTS was playing and only one item in playlist to
            # use playlist to determine playback method in get_sources
            pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
            plugin_url = 'plugin://%s/' % (kodi.get_id())
            if pl.size() == 1 and pl[0].getfilename().lower().startswith(plugin_url):
                logger.log('Service: Clearing Single Item Asguard Playlist', log_utils.LOGDEBUG)
                pl.clear()
                
            playedTime = float(self._lastPos)
            try: 
                percent_played = int((playedTime / self._totalTime) * 100)
            except: 
                percent_played = 0  # guard div by zero
            pTime = utils.format_time(playedTime)
            tTime = utils.format_time(self._totalTime)
            logger.log('Service: Played %s of %s total = %s%%' % (pTime, tTime, percent_played), log_utils.LOGDEBUG)
            if playedTime == 0 and self._totalTime == 999999:
                logger.log('Kodi silently failed to start playback', log_utils.LOGWARNING)
            elif playedTime >= 5:
                if percent_played <= 98:
                    logger.log('Service: Setting bookmark on |%s|%s|%s| to %s seconds' % (self.trakt_id, self.season, self.episode, playedTime), log_utils.LOGDEBUG)
                    self.db_connection.set_bookmark(self.trakt_id, playedTime, self.season, self.episode)
                    
                if percent_played >= 75 and self._from_library:
                    if kodi.has_addon('script.trakt'):
                        run = 'RunScript(script.trakt, action=sync, silent=True)'
                        xbmc.executebuiltin(run)
            self.reset()

    def onPlayBackEnded(self):
        logger.log('Service: Playback completed', log_utils.LOGNOTICE)
        self.onPlayBackStopped()

def disable_global_cx(was_on):
    if kodi.has_addon('plugin.program.super.favourites'):
        active_plugin = xbmc.getInfoLabel('Container.PluginName')
        sf = xbmcaddon.Addon('plugin.program.super.favourites')
        if active_plugin == kodi.get_id():
            if sf.getSetting('CONTEXT') == 'true':
                logger.log('Disabling Global CX while Asguard is active', log_utils.LOGDEBUG)
                was_on = True
                sf.setSetting('CONTEXT', 'false')
        elif was_on:
            logger.log('Re-enabling Global CX while Asguard is not active', log_utils.LOGDEBUG)
            sf.setSetting('CONTEXT', 'true')
            was_on = False
    
    return was_on
    
def check_cooldown(cd_begin):
    cd = int(kodi.get_setting('cooldown'))
    if cd > 0:
        cd_end = cd_begin + (cd * 60)
        now = time.time()
        if now < cd_end:
            logger.log('Service: Cooldown active for %s more seconds' % (cd_end - now), log_utils.LOGNOTICE)
            return True
    return False

def show_next_up(last_label, sf_begin):
    token = kodi.get_setting('trakt_oauth_token')
    if token and xbmc.getInfoLabel('Container.PluginName') == kodi.get_id() and xbmc.getInfoLabel('Container.Content') == 'tvshows':
        if xbmc.getInfoLabel('ListItem.label') != last_label:
            sf_begin = time.time()

        last_label = xbmc.getInfoLabel('ListItem.label')
        if sf_begin and (time.time() - sf_begin) >= int(kodi.get_setting('next_up_delay')):
            liz_url = xbmc.getInfoLabel('ListItem.FileNameAndPath')
            queries = kodi.parse_query(liz_url[liz_url.find('?'):])
            if 'trakt_id' in queries:
                try: 
                    list_size = int(kodi.get_setting('list_size'))
                except: 
                    list_size = 30
                try: 
                    trakt_timeout = int(kodi.get_setting('trakt_timeout'))
                except: 
                    trakt_timeout = 20
                trakt_api = Trakt_API(token, kodi.get_setting('use_https') == 'true', list_size, trakt_timeout, kodi.get_setting('trakt_offline') == 'true')
                progress = trakt_api.get_show_progress(queries['trakt_id'], full=True)
                if 'next_episode' in progress and progress['next_episode']:
                    if progress['completed'] or kodi.get_setting('next_unwatched') == 'true':
                        next_episode = progress['next_episode']
                        date = utils2.make_day(utils2.make_air_date(next_episode['first_aired']))
                        if kodi.get_setting('next_time') != '0':
                            date_time = '%s@%s' % (date, utils2.make_time(utils.iso_2_utc(next_episode['first_aired']), 'next_time'))
                        else:
                            date_time = date
                        msg = '[[COLOR deeppink]%s[/COLOR]] - %sx%s' % (date_time, next_episode['season'], next_episode['number'])
                        if next_episode['title']: msg += ' - %s' % (next_episode['title'])
                        duration = int(kodi.get_setting('next_up_duration')) * 1000
                        kodi.notify(header=i18n('next_episode'), msg=msg, duration=duration)
            sf_begin = 0
    else:
        last_label = ''
    
    return last_label, sf_begin

def main(argv=None):  # @UnusedVariable
    if sys.argv: 
        argv = sys.argv  # @UnusedVariable
    MAX_ERRORS = 10
    errors = 0
    last_label = ''
    sf_begin = 0
    cd_begin = 0
    was_on = False
    
    logger.log('Service: Installed Version: %s' % (kodi.get_version()), log_utils.LOGNOTICE)
    monitor = xbmc.Monitor()
    proxy = image_proxy.ImageProxy()
    service = Service()
    
    salts_utils.do_startup_task(MODES.UPDATE_SUBS)
    salts_utils.do_startup_task(MODES.PRUNE_CACHE)
    
    while not monitor.abortRequested():
        try:
            is_playing = service.isPlaying()
            salts_utils.do_scheduled_task(MODES.UPDATE_SUBS, is_playing)
            salts_utils.do_scheduled_task(MODES.PRUNE_CACHE, is_playing)
            if service.tracked and service.isPlayingVideo():
                service._lastPos = service.getTime()
    
            was_on = disable_global_cx(was_on)
            cd_begin = check_cooldown(cd_begin)
            if not proxy.running: proxy.start_proxy()
            
            if kodi.get_setting('show_next_up') == 'true':
                last_label, sf_begin = show_next_up(last_label, sf_begin)
        except Exception as e:
            errors += 1
            if errors >= MAX_ERRORS:
                logger.log('Service: Error (%s) received..(%s/%s)...Ending Service...' % (e, errors, MAX_ERRORS), log_utils.LOGERROR)
                break
            else:
                logger.log('Service: Error (%s) received..(%s/%s)...Continuing Service...' % (e, errors, MAX_ERRORS), log_utils.LOGERROR)
        else:
            errors = 0
    
        if monitor.waitForAbort(.5):
            break
        
    proxy.stop_proxy()
    logger.log('Service: shutting down...', log_utils.LOGNOTICE)

def update_xml(xml, new_settings, cat_count):
    new_settings.insert(0, '<category label="Settings %s">' % (cat_count))
    new_settings.append('    </category>')
    new_settings = '\n'.join(new_settings)
    match = re.search('(<category label="Settings %s">.*?</category>)' % (cat_count), xml, re.DOTALL | re.I)
    if match:
        old_settings = match.group(1)
        if old_settings != new_settings:
            xml = xml.replace(old_settings, new_settings)
    else:
        logger.log('Unable to match category: %s' % (cat_count), log_utils.LOGWARNING)
    return xml

def update_settings():
    full_path = os.path.join(kodi.get_path(), 'resources', 'settings.xml')
    
    try:
        # open for append; skip update if it fails
        with open(full_path, 'a') as f:
            pass
    except Exception as e:
        logger.log('Dynamic settings update skipped: %s' % (e), log_utils.LOGWARNING)
    else:
        with open(full_path, 'r') as f:
            xml = f.read()

        new_settings = []
        cat_count = 1
        old_xml = xml
        # Assuming you have classes that provide settings
        classes = [Service]  # Add other classes if needed
        for cls in sorted(classes, key=lambda x: x.__name__.upper()):
            new_settings += cls.get_settings() if hasattr(cls, 'get_settings') else []
            if len(new_settings) > 90:
                xml = update_xml(xml, new_settings, cat_count)
                new_settings = []
                cat_count += 1
    
        if new_settings:
            xml = update_xml(xml, new_settings, cat_count)
    
        if xml != old_xml:
            with open(full_path, 'w') as f:
                f.write(xml)
        else:
            logger.log('No Settings Update Needed', log_utils.LOGDEBUG)


if __name__ == '__main__':
    update_settings()
    service = Service()
    was_on = False
    monitor = xbmc.Monitor()  # Use Monitor for checking abort requests
    while not monitor.abortRequested():
        was_on = disable_global_cx(was_on)
        if service.isPlaying():
            service._lastPos = service.getTime()
        kodi.sleep(1000)