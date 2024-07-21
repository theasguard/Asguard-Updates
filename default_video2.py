@url_dispatcher.register(MODES.GET_SOURCES, ['mode', 'video_type', 'title', 'year', 'trakt_id'], ['season', 'episode', 'ep_title', 'ep_airdate'])
@url_dispatcher.register(MODES.SELECT_SOURCE, ['mode', 'video_type', 'title', 'year', 'trakt_id'], ['season', 'episode', 'ep_title', 'ep_airdate'])
@url_dispatcher.register(MODES.DOWNLOAD_SOURCE, ['mode', 'video_type', 'title', 'year', 'trakt_id'], ['season', 'episode', 'ep_title', 'ep_airdate'])
@url_dispatcher.register(MODES.AUTOPLAY, ['mode', 'video_type', 'title', 'year', 'trakt_id'], ['season', 'episode', 'ep_title', 'ep_airdate'])
def get_sources(mode, video_type, title, year, trakt_id, season='', episode='', ep_title='', ep_airdate=''):
    """
    Fetches sources for the given video details.

    Args:
        mode (str): The mode of operation.
        video_type (str): The type of video (e.g., movie, episode).
        title (str): The title of the video.
        year (str): The release year of the video.
        trakt_id (str): The Trakt ID of the video.
        season (str, optional): The season number (for TV shows). Defaults to ''.
        episode (str, optional): The episode number (for TV shows). Defaults to ''.
        ep_title (str, optional): The episode title (for TV shows). Defaults to ''.
        ep_airdate (str, optional): The episode air date (for TV shows). Defaults to ''.
    """
    timeout = max_timeout = int(kodi.get_setting('source_timeout'))
    if max_timeout == 0: timeout = None
    max_results = int(kodi.get_setting('source_results'))
    begin = time.time()
    fails = set()
    counts = {}
    video = ScraperVideo(video_type, title, year, trakt_id, season, episode, ep_title, ep_airdate)
    video2 = ScraperVideoExtended(video, title, year, trakt_id)
    active = False if kodi.get_setting('pd_force_disable') == 'true' else True
    cancelled = False
    with kodi.ProgressDialog(i18n('getting_sources'), utils2.make_progress_msg(video or video2), active=active) as pd:
        try:
            wp = worker_pool.WorkerPool()
            scrapers = salts_utils.relevant_scrapers(video_type)
            total_scrapers = len(scrapers)
            for i, cls in enumerate(scrapers):
                if pd.is_canceled(): return False
                scraper = cls(max_timeout)
                wp.request(salts_utils.parallel_get_sources, [scraper, video or video2])
                progress = i * 25 / total_scrapers
                pd.update(progress, line2=i18n('requested_sources_from') % (cls.get_name()))
                fails.add(cls.get_name())
                counts[cls.get_name()] = 0
