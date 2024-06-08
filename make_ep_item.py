def make_episode_item(show, episode, show_subs=True, menu_items=None):
    if menu_items is None:
        menu_items = []
    if isinstance(show, dict) and 'title' in show:
        # Remove year from the show title using regular expression
        show['title'] = re.sub(r' \(\d{4}\)$', '', show['title'])
    else:
        logger.log(f'Invalid show format: {show}', log_utils.LOGERROR)
        return None, None

    if isinstance(episode, dict):
        episode_season = episode.get('season', '')
        episode_number = episode.get('number', '')
        episode_title = episode.get('title', None)
        if episode_title is None:
            label = f'{episode_season}x{episode_number}'
        else:
            label = f'{episode_season}x{episode_number} {episode_title}'
    else:
        logger.log(f'Invalid episode format: {episode}', log_utils.LOGERROR)
        return None, None

    utc_air_time = None
    if 'first_aired' in episode and episode['first_aired']:
        utc_air_time = utils.iso_2_utc(episode['first_aired'])
        try:
            time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(utc_air_time))
        except Exception as e:
            logger.log(f'Error converting time: {str(e)}', log_utils.LOGERROR)
            time_str = i18n('unavailable')
    else:
        time_str = i18n('unavailable')

    logger.log(f'First Aired: Title: {show["title"]} S/E: {episode_season}/{episode_number} fa: {episode["first_aired"]}, utc: {utc_air_time}, local: {time_str}', log_utils.LOGDEBUG)

    if kodi.get_setting('unaired_indicator') == 'true' and (not episode['first_aired'] or utc_air_time > time.time()):
        label = f'[I][COLOR chocolate]{label}[/COLOR][/I]'

    if show_subs and utils2.srt_indicators_enabled():
        srt_scraper = SRT_Scraper()
        language = kodi.get_setting('subtitle-lang')
        tvshow_id = srt_scraper.get_tvshow_id(show['title'], show.get('year', ''))
        if tvshow_id is not None:
            srts = srt_scraper.get_episode_subtitles(language, tvshow_id, episode_season, episode_number)
        else:
            srts = []
        label = utils2.format_episode_label(label, episode_season, episode_number, srts)

    meta = salts_utils.make_info(episode, show)
    art = image_scraper.get_images(VIDEO_TYPES.EPISODE, show.get('ids', {}), episode_season, episode_number)
    liz = utils.make_list_item(label, meta, art)
    liz.setInfo('video', meta)
    air_date = ''
    if episode['first_aired']:
        air_date = utils2.make_air_date(episode['first_aired'])
    queries = {'mode': MODES.GET_SOURCES, 'video_type': VIDEO_TYPES.EPISODE, 'title': show['title'], 'year': show.get('year', ''), 'season': episode_season, 'episode': episode_number,
               'ep_title': episode_title, 'ep_airdate': air_date, 'trakt_id': show.get('ids', {}).get('trakt', ''), 'random': time.time()}
    liz_url = kodi.get_plugin_url(queries)

    if kodi.get_setting('auto-play') == 'true':
        queries['mode'] = MODES.SELECT_SOURCE
        label = i18n('select_source')
        if kodi.get_setting('source-win') == 'Dialog':
            runstring = 'RunPlugin(%s)' % kodi.get_plugin_url(queries)
        else:
            runstring = 'Container.Update(%s)' % kodi.get_plugin_url(queries)
    else:
        queries['mode'] = MODES.AUTOPLAY
        runstring = 'RunPlugin(%s)' % kodi.get_plugin_url(queries)
        label = i18n('auto-play')
    menu_items.insert(0, (label, runstring),)

    if kodi.get_setting('show_download') == 'true':
        queries = {'mode': MODES.DOWNLOAD_SOURCE, 'video_type': VIDEO_TYPES.EPISODE, 'title': show['title'], 'year': show['year'], 'season': episode_season, 'episode': episode_number,
                   'ep_title': episode_title, 'ep_airdate': air_date, 'trakt_id': show['ids']['trakt']}
        download_label = i18n('download_source') + f": {label}"
        runstring = 'RunPlugin(%s)' % kodi.get_plugin_url(queries)
        menu_items.append((download_label, runstring),)

    show_id = utils2.show_id(show)
    queries = {'mode': MODES.ADD_TO_LIST, 'section': SECTIONS.TV}
    queries.update(show_id)
    menu_items.append((i18n('add_show_to_list'), 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))),)

    if episode.get('watched', False):
        watched = False
        label = i18n('mark_as_unwatched')
    else:
        watched = True
        label = i18n('mark_as_watched')

    queries = {'mode': MODES.REFRESH_IMAGES, 'video_type': VIDEO_TYPES.EPISODE, 'ids': json.dumps(show['ids']), 'season': episode_season, 'episode': episode_number}
    menu_items.append((i18n('refresh_images'), 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))),)
    if TOKEN:
        show_id = utils2.show_id(show)
        queries = {'mode': MODES.RATE, 'section': SECTIONS.TV, 'season': episode_season, 'episode': episode_number}
        # favor imdb_id for ratings to work with official trakt addon
        if show['ids'].get('imdb'):
            queries.update({'id_type': 'imdb', 'show_id': show['ids']['imdb']})
        else:
            queries.update(show_id)

        menu_items.append((i18n('rate_on_trakt'), 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))),)

        queries = {'mode': MODES.TOGGLE_WATCHED, 'section': SECTIONS.TV, 'season': episode_season, 'episode': episode_number, 'watched': watched}
        queries.update(show_id)
        menu_items.append((label, 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))),)

    queries = {'mode': MODES.SET_URL_SEARCH, 'video_type': VIDEO_TYPES.TVSHOW, 'title': show['title'], 'year': show['year'], 'trakt_id': show['ids']['trakt']}
    menu_items.append((i18n('set_rel_show_url_search'), 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))),)
    queries = {'mode': MODES.SET_URL_SEARCH, 'video_type': VIDEO_TYPES.SEASON, 'title': show['title'], 'year': show['year'], 'trakt_id': show['ids']['trakt'], 'season': episode_season}
    menu_items.append((i18n('set_rel_season_url_search'), 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))),)
    queries = {'mode': MODES.SET_URL_MANUAL, 'video_type': VIDEO_TYPES.EPISODE, 'title': show['title'], 'year': show['year'], 'season': episode_season,
               'episode': episode_number, 'ep_title': episode_title, 'ep_airdate': air_date, 'trakt_id': show['ids']['trakt']}
    menu_items.append((i18n('set_rel_url_manual'), 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))),)

    liz.addContextMenuItems(menu_items, replaceItems=True)
    return liz, liz_url
