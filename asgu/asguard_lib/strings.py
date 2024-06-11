"""
    Asguard Addon
    Copyright (C) 2015 tknorris

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

# Dictionary mapping string keys to integer values for localization
STRINGS = {
    'movies': 30000,
    'tv_shows': 30001,
    'movie': 30002,
    'tv_show': 30003,
    'settings': 30004,
    'scraper_sort_order': 30005,
    'url_resolver_settings': 30006,
    'addon_settings': 30007,
    'auto_config': 30008,
    'auth_death_streams': 30009,
    'set_default_views': 30010,
    'remove_cached_urls': 30011,
    'trending': 30012,
    'popular': 30013,
    'recently_updated': 30014,
    'recommended': 30015,
    'my_collection': 30016,
    'my_favorites': 30017,
    'my_subscriptions': 30018,
    'my_watchlist': 30019,
    'my_lists': 30020,
    'other_lists': 30021,
    'my_next_episodes': 30022,
    'my_calendar': 30023,
    'general_calendar': 30024,
    'premiere_calendar': 30025,
    'search': 30026,
    'recent_searches': 30027,
    'saved_searches': 30028,
    'force_refresh': 30029,
    'clear_all': 30030,
    'forcing_refresh': 30031,
    'force_refresh_complete': 30032,
    'enable_all_scrapers': 30033,
    'disable_all_scrapers': 30034,
    'enable_scraper': 30035,
    'disable_scraper': 30036,
    'move_up': 30037,
    'move_down': 30038,
    'move_to': 30039,
    'new_pos': 30040,
    'set_default_x_view': 30041,
    'set_view_instr': 30042,
    'import': 30043,
    'view_set': 30044,
    'delete_cache': 30045,
    'auto_conf_line1': 30046,
    'auto_conf_line2': 30047,
    'auto_conf_line3': 30048,
    'go_back': 30049,
    'continue': 30050,
    'auto_conf_complete': 30051,
    'set_fav_list': 30052,
    'set_sub_list': 30053,
    'import_collection': 30054,
    'add_other_list': 30055,
    'copy_to_my_list': 30056,
    'add_more_from': 30057,
    'remove_list': 30058,
    'rename_list': 30059,
    'new_name_heading': 30060,
    'username_list_owner': 30061,
    'list_not_exist': 30062,
    'progress_timeouts': 30063,
    'browse_seasons': 30064,
    'update_subs': 30065,
    'cleanup_subs': 30066,
    'pick_sub_list': 30067,
    'pick_fav_list': 30068,
    'blank_searches': 30069,
    'save_search': 30070,
    'remove_from_recent': 30071,
    'delete_search': 30072,
    'recent_cleared': 30073,
    'saved_cleared': 30074,
    'scraper_timeout': 30075,
    'no_useable_sources': 30076,
    'choose_subtitle': 30077,
    'resolve_failed': 30078,
    'all_sources_failed': 30079,
    'choose_stream': 30080,
    'set_related_url': 30081,
    'recv_result': 30082,
    'url_to_change': 30083,
    'rel_url_at': 30084,
    'rel_url_set': 30085,
    'manual_search': 30086,
    'select_related': 30087,
    'enter_search': 30088,
    'scraper_no_search': 30089,
    'enter_rating': 30090,
    'input_tvshow_id': 30091,
    'item_to_collection': 30092,
    'item_from_collection': 30093,
    'item_to_list': 30094,
    'list_copied': 30095,
    'tv': 30096,
    'marked_as': 30097,
    'updating_subscriptions': 30098,
    'next_update': 30099,
    'flush_cache_line1': 30100,
    'flush_cache_line2': 30101,
    'keep': 30102,
    'delete': 30103,
    'flush_web_cache': 30104,
    'db_reset_success': 30105,
    'db_on_sqlite': 30106,
    'select_export_dir': 30107,
    'enter_export_name': 30108,
    'export_successful': 30109,
    'exported_to': 30110,
    'export': 30111,
    'export_failed': 30112,
    'select_import_file': 30113,
    'import_success': 30114,
    'imported_from': 30115,
    'import': 30116,
    'import_failed': 30117,
    'remove_from_list': 30118,
    'subscribe': 30119,
    'require_aired_only': 30120,
    'require_page_only': 30121,
    'next_page': 30122,
    'previous_week': 30123,
    'next_week': 30124,
    'mark_as_unwatched': 30125,
    'mark_as_watched': 30126,
    'rate_on_trakt': 30127,
    'set_as_season_view': 30128,
    'unavailable': 30129,
    'select_source': 30130,
    'download_source': 30131,
    'show_information': 30132,
    'add_show_to_list': 30133,
    'set_rel_show_url_search': 30134,
    'set_rel_url_manual': 30135,
    'remove_from_collection': 30136,
    'add_to_collection': 30137,
    'add_to_list': 30138,
    'add_to_library': 30139,
    'set_addicted_tvshowid': 30140,
    'use_def_ep_matching': 30141,
    'use_ep_title_match': 30142,
    'set_rel_url_search': 30143,
    'play_trailer': 30144,
    'pick_a_list': 30145,
    'no_lists_for_user': 30146,
    'scraper_disabled': 30147,
    'disable_line1': 30148,
    'disable_line2': 30149,
    'disable_line3': 30150,
    'keep_enabled': 30151,
    'disable_it': 30152,
    'trakt_bookmark_exists': 30153,
    'local_bookmark_exists': 30154,
    'resume_from': 30155,
    'start_from_beginning': 30156,
    'resume': 30157,
    'downloading': 30158,
    'download_complete': 30159,
    'download_error': 30160,
    'trakt_acct_auth': 30161,
    # 30162 - 30172 deleted
    'trakt_auth_complete': 30173,
    'enabled': 30174,
    'base_url': 30175,
    'page_existence': 30176,
    'username': 30177,
    'password': 30178,
    'filter_results_days': 30179,
    'auto_select': 30180,
    'include_premium': 30181,
    'max_pages': 30182,
    'no_sources': 30183,
    'season': 30184,
    'disabled': 30185,
    'search': 30186,
    'watched': 30187,
    'unwatched': 30188,
    'updating': 30189,
    'failed_create_dir': 30190,
    'failed_write_file': 30191,
    'reset_base_url': 30192,
    'reset_complete': 30193,
    'req_result': 30194,
    'added_to_lib': 30195,
    'add_to_main': 30196,
    'remove_from_main': 30197,
    'liked_lists': 30198,
    'mosts': 30199,
    'most_played_weekly': 30200,
    'most_played_monthly': 30201,
    'most_played_all': 30202,
    'most_watched_weekly': 30203,
    'most_watched_monthly': 30204,
    'most_watched_all': 30205,
    'most_collected_weekly': 30206,
    'most_collected_monthly': 30207,
    'most_collected_all': 30208,
    'not_added_to_lib': 30209,
    'local_exists': 30210,
    # 30211 & 30212 repurposed to be in settings.xml
    'trakt_on_deck': 30213,
    'on': 30214,
    'delete_bookmark': 30215,
    'bookmark_deleted': 30216,
    'force_no_match': 30217,
    'getting_sources': 30218,
    'requested_sources_from': 30219,
    'received_sources_from': 30220,
    'applying_source_filters': 30221,
    'include_comments': 30222,
    'watched_history': 30223,
    'trying_autoplay': 30224,
    'trying_source': 30225,
    'failed_source': 30226,
    'scraper_timeout_list': 30227,
    'reset_fails': 30228,
    'result_limit': 30229,
    'include_in_mne': 30230,
    'auto-play': 30231,
    'set_trakt_timeout': 30232,
    'set_cal_start': 30233,
    'set_cal_airtime': 30234,
    'set_scraper_timeout': 30235,
    'set_wl_mne': 30236,
    'set_test_direct': 30237,
    'set_filter_unusable': 30238,
    'set_show_debrid': 30239,
    'set_no_limit': 30240,
    'set_source_sort': 30241,
    'set_sso': 30242,
    'set_reset_url': 30243,
    'select_all_none': 30244,
    'auto_pick': 30245,
    'recovery_header': 30246,
    'rec_mig_1': 30247,
    'rec_mig_2': 30248,
    'rec_reset_1': 30249,
    'rec_reset_2': 30250,
    'rec_reset_3': 30251,
    'reset_failed': 30252,
    'no_stream_found': 30253,
    'discover_mne': 30254,
    'retr_history': 30255,
    'retr_watchlist': 30256,
    'retr_hidden': 30257,
    'req_progress': 30258,
    'rec_progress': 30259,
    'reset_rel_urls': 30260,
    'scraper_url_reset': 30261,
    'anticipated': 30262,
    'set_as_sources_view': 30263,
    'set_rel_season_url_search': 30264,
    'trakt_api_offline': 30265,
    'verification_url': 30266,
    'prompt_code': 30267,
    'code_expires': 30268,
    'user_reject_auth': 30269,
    'use_https': 30548,
    'ip_auth_line1': 30270,
    'ip_auth_line2': 30271,
    'my_rewatches': 30272,
    'pick_rewatch_list': 30273,
    'least_watched_method': 30274,
    'most_watched_method': 30275,
    'last_watched_method': 30276,
    'set_rewatch_list': 30277,
    'playback_limited': 30278,
    'size_limit': 30279,
    'include_transcodes': 30281,
    'next_episode': 30282,
    'remaining_over': 30283,
    'remaining_under': 30284,
    'genres': 30285,
    'retr_collection': 30286,
    'adding_items': 30287,
    'working': 30288,
    'rescrape_all': 30289,
    'manual_search_all': 30290,
    'torba_acct_auth': 30291,
    'torba_auth_complete': 30292,
    'torba_auth_failed': 30293,
    'torba_auth': 30294,
    'login_prompt': 30295,
    'flush_image_cache': 30296,
    'flush_image_line1': 30297,
    'flush_image_line2': 30298,
    'flush_complete': 30299,
    'refresh_images': 30300,
    'scraper_updated': 30301,
    'reset_torba': 30302,
    'torba_auth_reset': 30303,
    'repair_urlresolver': 30304,
    'repair_line_1': 30305,
    'smu_failed': 30306,
    'proxy_restarted': 30307,
    'tmdb_search': 30308,
    'tmdb_tv_search': 30309
}