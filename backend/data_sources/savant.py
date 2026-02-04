"""
Baseball Savant data fetcher

Fetches Statcast data including expected stats, pitch data, and advanced metrics.
Uses pybaseball library for most data access.
"""

import requests
import pandas as pd
import numpy as np
from io import StringIO
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta

from config import Config
from backend.utils.cache import cached_data


class SavantClient:
    """Client for fetching data from Baseball Savant."""

    # Pitch type mappings
    PITCH_TYPES = {
        'FF': '4-Seam Fastball',
        'SI': 'Sinker',
        'FC': 'Cutter',
        'SL': 'Slider',
        'CU': 'Curveball',
        'CH': 'Changeup',
        'FS': 'Splitter',
        'KC': 'Knuckle Curve',
        'KN': 'Knuckleball',
        'EP': 'Eephus',
        'SC': 'Screwball',
        'SV': 'Sweeper',
        'ST': 'Sweeping Curve',
    }

    # Batted ball event types
    EVENT_TYPES = {
        'single': 'Single',
        'double': 'Double',
        'triple': 'Triple',
        'home_run': 'Home Run',
        'field_out': 'Field Out',
        'strikeout': 'Strikeout',
        'walk': 'Walk',
        'hit_by_pitch': 'HBP',
        'sac_fly': 'Sac Fly',
        'sac_bunt': 'Sac Bunt',
        'force_out': 'Force Out',
        'grounded_into_double_play': 'GIDP',
        'field_error': 'Error',
    }

    def __init__(self):
        self.base_url = Config.SAVANT_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; OttoneuRosterTool/1.0)'
        })

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Make a GET request with error handling."""
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _get_season_dates(self, season: int) -> Tuple[str, str]:
        """Get start and end dates for a season."""
        # MLB season typically runs April 1 - October 31
        start_date = f"{season}-03-20"  # Spring training games sometimes count
        end_date = f"{season}-11-05"  # Include postseason

        # If current season, use today as end date
        today = datetime.now()
        if season == today.year:
            end_date = today.strftime("%Y-%m-%d")

        return start_date, end_date

    # -------------------------------------------------------------------------
    # Player ID Lookup
    # -------------------------------------------------------------------------

    def lookup_player_id(self, last_name: str, first_name: str) -> Optional[int]:
        """
        Look up a player's MLB ID by name.

        Args:
            last_name: Player's last name
            first_name: Player's first name

        Returns:
            MLB player ID or None if not found
        """
        try:
            from pybaseball import playerid_lookup
            result = playerid_lookup(last_name, first_name)
            if not result.empty:
                return int(result.iloc[0]['key_mlbam'])
        except Exception as e:
            print(f"Error looking up player: {e}")
        return None

    def lookup_player_by_name(self, full_name: str) -> Optional[int]:
        """
        Look up player ID from full name (e.g., "Mike Trout").

        Args:
            full_name: Player's full name

        Returns:
            MLB player ID or None
        """
        parts = full_name.strip().split()
        if len(parts) >= 2:
            first_name = parts[0]
            last_name = ' '.join(parts[1:])
            return self.lookup_player_id(last_name, first_name)
        return None

    # -------------------------------------------------------------------------
    # Pitch-Level Statcast Data
    # -------------------------------------------------------------------------

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_batter_statcast(
        self,
        player_id: int,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch Statcast data for a batter.

        Args:
            player_id: MLB player ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with pitch-level Statcast data
        """
        try:
            from pybaseball import statcast_batter
            df = statcast_batter(start_date, end_date, player_id)
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            print(f"Error fetching batter statcast: {e}")
            return pd.DataFrame()

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_pitcher_statcast(
        self,
        player_id: int,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch Statcast data for a pitcher.

        Args:
            player_id: MLB player ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with pitch-level Statcast data
        """
        try:
            from pybaseball import statcast_pitcher
            df = statcast_pitcher(start_date, end_date, player_id)
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            print(f"Error fetching pitcher statcast: {e}")
            return pd.DataFrame()

    def get_batter_season_statcast(
        self,
        player_id: int,
        season: int
    ) -> pd.DataFrame:
        """Get full season Statcast data for a batter."""
        start_date, end_date = self._get_season_dates(season)
        return self.get_batter_statcast(player_id, start_date, end_date)

    def get_pitcher_season_statcast(
        self,
        player_id: int,
        season: int
    ) -> pd.DataFrame:
        """Get full season Statcast data for a pitcher."""
        start_date, end_date = self._get_season_dates(season)
        return self.get_pitcher_statcast(player_id, start_date, end_date)

    # -------------------------------------------------------------------------
    # Expected Stats
    # -------------------------------------------------------------------------

    def get_expected_stats(self, player_id: int, season: int) -> Dict:
        """
        Calculate expected stats (xBA, xSLG, xwOBA) for a batter.

        Args:
            player_id: MLB player ID
            season: The season year

        Returns:
            Dict with expected statistics
        """
        df = self.get_batter_season_statcast(player_id, season)

        if df.empty:
            return self._empty_expected_stats()

        # Filter to batted ball events
        batted = df[df['type'] == 'X'].copy()

        if batted.empty:
            return self._empty_expected_stats()

        stats = {
            'player_id': player_id,
            'season': season,
            'pa': len(df[df['events'].notna()]),
            'batted_balls': len(batted),
        }

        # Calculate expected stats from available columns
        if 'estimated_ba_using_speedangle' in batted.columns:
            stats['xBA'] = round(batted['estimated_ba_using_speedangle'].mean(), 3)

        if 'estimated_slg_using_speedangle' in batted.columns:
            stats['xSLG'] = round(batted['estimated_slg_using_speedangle'].mean(), 3)

        if 'estimated_woba_using_speedangle' in batted.columns:
            stats['xwOBA'] = round(batted['estimated_woba_using_speedangle'].mean(), 3)

        # Batted ball quality metrics
        if 'launch_speed' in batted.columns:
            stats['avg_exit_velo'] = round(batted['launch_speed'].mean(), 1)
            stats['max_exit_velo'] = round(batted['launch_speed'].max(), 1)
            # Hard hit rate (95+ mph)
            hard_hit = batted[batted['launch_speed'] >= 95]
            stats['hard_hit_rate'] = round(len(hard_hit) / len(batted) * 100, 1)

        if 'launch_angle' in batted.columns:
            stats['avg_launch_angle'] = round(batted['launch_angle'].mean(), 1)

        # Barrel rate
        if 'barrel' in batted.columns:
            barrels = batted['barrel'].sum()
            stats['barrels'] = int(barrels)
            stats['barrel_rate'] = round(barrels / len(batted) * 100, 1)

        # Sweet spot rate (8-32 degree launch angle)
        if 'launch_angle' in batted.columns:
            sweet_spot = batted[(batted['launch_angle'] >= 8) & (batted['launch_angle'] <= 32)]
            stats['sweet_spot_rate'] = round(len(sweet_spot) / len(batted) * 100, 1)

        return stats

    def get_pitcher_expected_stats(self, player_id: int, season: int) -> Dict:
        """
        Calculate expected stats for a pitcher.

        Args:
            player_id: MLB player ID
            season: The season year

        Returns:
            Dict with expected statistics
        """
        df = self.get_pitcher_season_statcast(player_id, season)

        if df.empty:
            return self._empty_pitcher_expected_stats()

        batted = df[df['type'] == 'X'].copy()

        stats = {
            'player_id': player_id,
            'season': season,
            'pitches': len(df),
            'batted_balls_against': len(batted),
        }

        if batted.empty:
            return stats

        # Expected stats against
        if 'estimated_ba_using_speedangle' in batted.columns:
            stats['xBA_against'] = round(batted['estimated_ba_using_speedangle'].mean(), 3)

        if 'estimated_slg_using_speedangle' in batted.columns:
            stats['xSLG_against'] = round(batted['estimated_slg_using_speedangle'].mean(), 3)

        if 'estimated_woba_using_speedangle' in batted.columns:
            stats['xwOBA_against'] = round(batted['estimated_woba_using_speedangle'].mean(), 3)

        # Quality of contact against
        if 'launch_speed' in batted.columns:
            stats['avg_exit_velo_against'] = round(batted['launch_speed'].mean(), 1)
            hard_hit = batted[batted['launch_speed'] >= 95]
            stats['hard_hit_rate_against'] = round(len(hard_hit) / len(batted) * 100, 1)

        if 'barrel' in batted.columns:
            barrels = batted['barrel'].sum()
            stats['barrel_rate_against'] = round(barrels / len(batted) * 100, 1)

        return stats

    def _empty_expected_stats(self) -> Dict:
        """Return empty expected stats dict."""
        return {
            'xBA': None, 'xSLG': None, 'xwOBA': None,
            'avg_exit_velo': None, 'max_exit_velo': None,
            'hard_hit_rate': None, 'barrel_rate': None,
            'avg_launch_angle': None, 'sweet_spot_rate': None
        }

    def _empty_pitcher_expected_stats(self) -> Dict:
        """Return empty pitcher expected stats dict."""
        return {
            'xBA_against': None, 'xSLG_against': None, 'xwOBA_against': None,
            'avg_exit_velo_against': None, 'hard_hit_rate_against': None,
            'barrel_rate_against': None
        }

    # -------------------------------------------------------------------------
    # Statcast Leaderboards
    # -------------------------------------------------------------------------

    @cached_data(hours=6)
    def get_statcast_leaderboard(
        self,
        season: int,
        player_type: str = 'batter',
        min_pa: int = 50
    ) -> pd.DataFrame:
        """
        Fetch Statcast leaderboard data.

        Args:
            season: Season year
            player_type: 'batter' or 'pitcher'
            min_pa: Minimum plate appearances

        Returns:
            DataFrame with leaderboard data
        """
        try:
            if player_type == 'batter':
                from pybaseball import statcast_batter_exitvelo_barrels
                return statcast_batter_exitvelo_barrels(season, min_pa)
            else:
                from pybaseball import statcast_pitcher_exitvelo_barrels
                return statcast_pitcher_exitvelo_barrels(season, min_pa)
        except Exception as e:
            print(f"Error fetching statcast leaderboard: {e}")
            return pd.DataFrame()

    @cached_data(hours=6)
    def get_expected_stats_leaderboard(
        self,
        season: int,
        player_type: str = 'batter',
        min_pa: int = 50
    ) -> pd.DataFrame:
        """
        Fetch expected stats leaderboard.

        Args:
            season: Season year
            player_type: 'batter' or 'pitcher'
            min_pa: Minimum plate appearances

        Returns:
            DataFrame with xwOBA, xBA, etc.
        """
        try:
            if player_type == 'batter':
                from pybaseball import statcast_batter_expected_stats
                return statcast_batter_expected_stats(season, min_pa)
            else:
                from pybaseball import statcast_pitcher_expected_stats
                return statcast_pitcher_expected_stats(season, min_pa)
        except Exception as e:
            print(f"Error fetching expected stats leaderboard: {e}")
            return pd.DataFrame()

    # -------------------------------------------------------------------------
    # Pitch Arsenal Analysis
    # -------------------------------------------------------------------------

    def get_pitch_arsenal(self, player_id: int, season: int) -> pd.DataFrame:
        """
        Get pitch arsenal breakdown for a pitcher.

        Args:
            player_id: MLB player ID
            season: The season year

        Returns:
            DataFrame with pitch types and their metrics
        """
        df = self.get_pitcher_season_statcast(player_id, season)

        if df.empty or 'pitch_type' not in df.columns:
            return pd.DataFrame()

        # Group by pitch type
        arsenal = []
        total_pitches = len(df)

        for pitch_type in df['pitch_type'].dropna().unique():
            pitch_df = df[df['pitch_type'] == pitch_type]

            pitch_data = {
                'pitch_type': pitch_type,
                'pitch_name': self.PITCH_TYPES.get(pitch_type, pitch_type),
                'count': len(pitch_df),
                'usage_pct': round(len(pitch_df) / total_pitches * 100, 1),
            }

            # Velocity
            if 'release_speed' in pitch_df.columns:
                pitch_data['avg_velocity'] = round(pitch_df['release_speed'].mean(), 1)
                pitch_data['max_velocity'] = round(pitch_df['release_speed'].max(), 1)

            # Spin rate
            if 'release_spin_rate' in pitch_df.columns:
                pitch_data['avg_spin_rate'] = round(pitch_df['release_spin_rate'].mean(), 0)

            # Movement
            if 'pfx_x' in pitch_df.columns:
                pitch_data['horizontal_break'] = round(pitch_df['pfx_x'].mean() * 12, 1)  # Convert to inches
            if 'pfx_z' in pitch_df.columns:
                pitch_data['vertical_break'] = round(pitch_df['pfx_z'].mean() * 12, 1)

            # Results
            if 'description' in pitch_df.columns:
                swings = pitch_df[pitch_df['description'].isin([
                    'swinging_strike', 'swinging_strike_blocked', 'foul',
                    'foul_tip', 'hit_into_play'
                ])]
                whiffs = pitch_df[pitch_df['description'].isin([
                    'swinging_strike', 'swinging_strike_blocked'
                ])]
                if len(swings) > 0:
                    pitch_data['whiff_rate'] = round(len(whiffs) / len(swings) * 100, 1)

            # Called strikes
            if 'description' in pitch_df.columns:
                called_strikes = pitch_df[pitch_df['description'] == 'called_strike']
                takes = pitch_df[pitch_df['description'].isin(['called_strike', 'ball'])]
                if len(takes) > 0:
                    pitch_data['called_strike_pct'] = round(len(called_strikes) / len(takes) * 100, 1)

            arsenal.append(pitch_data)

        result = pd.DataFrame(arsenal)
        if not result.empty:
            result = result.sort_values('usage_pct', ascending=False)
        return result

    @cached_data(hours=6)
    def get_pitch_arsenal_leaderboard(
        self,
        season: int,
        pitch_type: str = 'FF',
        min_pitches: int = 100
    ) -> pd.DataFrame:
        """
        Get leaderboard for a specific pitch type.

        Args:
            season: Season year
            pitch_type: Pitch type code (FF, SL, CH, etc.)
            min_pitches: Minimum pitches thrown

        Returns:
            DataFrame with pitch-specific leaderboard
        """
        try:
            from pybaseball import statcast_pitcher_pitch_arsenal
            return statcast_pitcher_pitch_arsenal(season, min_pitches, pitch_type)
        except Exception as e:
            print(f"Error fetching pitch arsenal leaderboard: {e}")
            return pd.DataFrame()

    # -------------------------------------------------------------------------
    # Sprint Speed & Baserunning
    # -------------------------------------------------------------------------

    @cached_data(hours=12)
    def get_sprint_speed_leaderboard(self, season: int, min_opps: int = 10) -> pd.DataFrame:
        """
        Get sprint speed leaderboard.

        Args:
            season: Season year
            min_opps: Minimum opportunities

        Returns:
            DataFrame with sprint speed data
        """
        try:
            from pybaseball import statcast_sprint_speed
            return statcast_sprint_speed(season, min_opps)
        except Exception as e:
            print(f"Error fetching sprint speed: {e}")
            return pd.DataFrame()

    def get_player_sprint_speed(self, player_id: int, season: int) -> Optional[Dict]:
        """
        Get sprint speed for a specific player.

        Args:
            player_id: MLB player ID
            season: Season year

        Returns:
            Dict with sprint speed data or None
        """
        leaderboard = self.get_sprint_speed_leaderboard(season)

        if leaderboard.empty:
            return None

        # Find player in leaderboard
        id_col = 'player_id' if 'player_id' in leaderboard.columns else 'mlbam_id'
        if id_col not in leaderboard.columns:
            return None

        player_row = leaderboard[leaderboard[id_col] == player_id]

        if player_row.empty:
            return None

        row = player_row.iloc[0]
        return {
            'player_id': player_id,
            'season': season,
            'sprint_speed': row.get('sprint_speed', row.get('hp_to_1b', None)),
            'competitive_runs': row.get('competitive_runs', None),
            'hp_to_1b': row.get('hp_to_1b', None),
            'bolts': row.get('bolts', None),  # 30+ ft/sec runs
        }

    # -------------------------------------------------------------------------
    # Batted Ball Analysis
    # -------------------------------------------------------------------------

    def get_batted_ball_profile(self, player_id: int, season: int) -> Dict:
        """
        Get detailed batted ball profile for a batter.

        Args:
            player_id: MLB player ID
            season: Season year

        Returns:
            Dict with batted ball metrics
        """
        df = self.get_batter_season_statcast(player_id, season)

        if df.empty:
            return {}

        batted = df[df['type'] == 'X'].copy()

        if batted.empty:
            return {}

        profile = {
            'player_id': player_id,
            'season': season,
            'batted_balls': len(batted),
        }

        # Launch angle distribution
        if 'launch_angle' in batted.columns:
            la = batted['launch_angle'].dropna()
            profile['avg_launch_angle'] = round(la.mean(), 1)

            # Batted ball types by launch angle
            grounders = la[la < 10]
            line_drives = la[(la >= 10) & (la < 25)]
            fly_balls = la[(la >= 25) & (la < 50)]
            popups = la[la >= 50]

            total = len(la)
            profile['gb_pct'] = round(len(grounders) / total * 100, 1)
            profile['ld_pct'] = round(len(line_drives) / total * 100, 1)
            profile['fb_pct'] = round(len(fly_balls) / total * 100, 1)
            profile['popup_pct'] = round(len(popups) / total * 100, 1)

        # Exit velocity distribution
        if 'launch_speed' in batted.columns:
            ev = batted['launch_speed'].dropna()
            profile['avg_exit_velo'] = round(ev.mean(), 1)
            profile['max_exit_velo'] = round(ev.max(), 1)
            profile['ev_50th_pct'] = round(ev.quantile(0.5), 1)
            profile['ev_90th_pct'] = round(ev.quantile(0.9), 1)

            # Hard hit (95+), medium (85-95), soft (<85)
            profile['hard_pct'] = round(len(ev[ev >= 95]) / len(ev) * 100, 1)
            profile['medium_pct'] = round(len(ev[(ev >= 85) & (ev < 95)]) / len(ev) * 100, 1)
            profile['soft_pct'] = round(len(ev[ev < 85]) / len(ev) * 100, 1)

        # Spray chart data (pull/center/oppo)
        if 'hc_x' in batted.columns and 'stand' in batted.columns:
            # Home plate is at approximately x=125
            # Pull = towards 3B for RHH, towards 1B for LHH
            rhh = batted[batted['stand'] == 'R']
            lhh = batted[batted['stand'] == 'L']

            total_bb = len(batted)
            pull_count = 0
            center_count = 0
            oppo_count = 0

            # RHH: pull is hc_x > 125, oppo is hc_x < 125
            if not rhh.empty:
                pull_count += len(rhh[rhh['hc_x'] > 145])
                oppo_count += len(rhh[rhh['hc_x'] < 105])
                center_count += len(rhh[(rhh['hc_x'] >= 105) & (rhh['hc_x'] <= 145)])

            # LHH: pull is hc_x < 125, oppo is hc_x > 125
            if not lhh.empty:
                pull_count += len(lhh[lhh['hc_x'] < 105])
                oppo_count += len(lhh[lhh['hc_x'] > 145])
                center_count += len(lhh[(lhh['hc_x'] >= 105) & (lhh['hc_x'] <= 145)])

            if total_bb > 0:
                profile['pull_pct'] = round(pull_count / total_bb * 100, 1)
                profile['center_pct'] = round(center_count / total_bb * 100, 1)
                profile['oppo_pct'] = round(oppo_count / total_bb * 100, 1)

        # Barrel rate
        if 'barrel' in batted.columns:
            barrels = batted['barrel'].sum()
            profile['barrels'] = int(barrels)
            profile['barrel_pct'] = round(barrels / len(batted) * 100, 1)

        return profile

    # -------------------------------------------------------------------------
    # Rolling/Recent Performance
    # -------------------------------------------------------------------------

    def get_rolling_stats(
        self,
        player_id: int,
        season: int,
        window: int = 50,
        player_type: str = 'batter'
    ) -> pd.DataFrame:
        """
        Get rolling statistics for a player.

        Args:
            player_id: MLB player ID
            season: Season year
            window: Number of batted balls for rolling window
            player_type: 'batter' or 'pitcher'

        Returns:
            DataFrame with rolling stats over time
        """
        if player_type == 'batter':
            df = self.get_batter_season_statcast(player_id, season)
        else:
            df = self.get_pitcher_season_statcast(player_id, season)

        if df.empty:
            return pd.DataFrame()

        # Sort by date
        if 'game_date' in df.columns:
            df = df.sort_values('game_date')

        batted = df[df['type'] == 'X'].copy()

        if len(batted) < window:
            return pd.DataFrame()

        rolling_stats = []

        for i in range(window, len(batted) + 1):
            window_df = batted.iloc[i-window:i]

            stat_row = {
                'end_date': window_df['game_date'].iloc[-1] if 'game_date' in window_df.columns else None,
                'batted_balls': window,
            }

            if 'launch_speed' in window_df.columns:
                stat_row['avg_exit_velo'] = round(window_df['launch_speed'].mean(), 1)
                stat_row['hard_hit_pct'] = round(
                    len(window_df[window_df['launch_speed'] >= 95]) / window * 100, 1
                )

            if 'estimated_woba_using_speedangle' in window_df.columns:
                stat_row['xwOBA'] = round(window_df['estimated_woba_using_speedangle'].mean(), 3)

            if 'barrel' in window_df.columns:
                stat_row['barrel_pct'] = round(window_df['barrel'].sum() / window * 100, 1)

            rolling_stats.append(stat_row)

        return pd.DataFrame(rolling_stats)

    # -------------------------------------------------------------------------
    # Plate Discipline
    # -------------------------------------------------------------------------

    def get_plate_discipline(self, player_id: int, season: int) -> Dict:
        """
        Get plate discipline metrics for a batter.

        Args:
            player_id: MLB player ID
            season: Season year

        Returns:
            Dict with discipline metrics
        """
        df = self.get_batter_season_statcast(player_id, season)

        if df.empty:
            return {}

        # Get zone data
        in_zone = df[df['zone'].isin([1, 2, 3, 4, 5, 6, 7, 8, 9])]  # Strike zone
        out_zone = df[~df['zone'].isin([1, 2, 3, 4, 5, 6, 7, 8, 9])]  # Outside zone

        # Swings
        swing_types = ['swinging_strike', 'swinging_strike_blocked', 'foul',
                       'foul_tip', 'hit_into_play', 'foul_bunt', 'missed_bunt']

        swings = df[df['description'].isin(swing_types)]
        swings_in_zone = in_zone[in_zone['description'].isin(swing_types)]
        swings_out_zone = out_zone[out_zone['description'].isin(swing_types)]

        # Whiffs
        whiff_types = ['swinging_strike', 'swinging_strike_blocked']
        whiffs = df[df['description'].isin(whiff_types)]

        discipline = {
            'player_id': player_id,
            'season': season,
            'pitches_seen': len(df),
        }

        # Zone rates
        if len(df) > 0:
            discipline['zone_pct'] = round(len(in_zone) / len(df) * 100, 1)

        # Swing rates
        if len(df) > 0:
            discipline['swing_pct'] = round(len(swings) / len(df) * 100, 1)
        if len(in_zone) > 0:
            discipline['z_swing_pct'] = round(len(swings_in_zone) / len(in_zone) * 100, 1)
        if len(out_zone) > 0:
            discipline['o_swing_pct'] = round(len(swings_out_zone) / len(out_zone) * 100, 1)

        # Whiff rate
        if len(swings) > 0:
            discipline['whiff_pct'] = round(len(whiffs) / len(swings) * 100, 1)

        # Contact rates
        contact = swings[~swings['description'].isin(whiff_types)]
        if len(swings) > 0:
            discipline['contact_pct'] = round(len(contact) / len(swings) * 100, 1)

        # Z-Contact (contact on pitches in zone)
        z_contact = swings_in_zone[~swings_in_zone['description'].isin(whiff_types)]
        if len(swings_in_zone) > 0:
            discipline['z_contact_pct'] = round(len(z_contact) / len(swings_in_zone) * 100, 1)

        # O-Contact (contact on pitches outside zone)
        o_contact = swings_out_zone[~swings_out_zone['description'].isin(whiff_types)]
        if len(swings_out_zone) > 0:
            discipline['o_contact_pct'] = round(len(o_contact) / len(swings_out_zone) * 100, 1)

        return discipline

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def get_current_season(self) -> int:
        """Get current MLB season year."""
        now = datetime.now()
        if now.month < 4:
            return now.year - 1
        return now.year

    def get_player_summary(self, player_id: int, season: int, player_type: str = 'batter') -> Dict:
        """
        Get comprehensive Statcast summary for a player.

        Args:
            player_id: MLB player ID
            season: Season year
            player_type: 'batter' or 'pitcher'

        Returns:
            Dict with all Statcast metrics combined
        """
        summary = {
            'player_id': player_id,
            'season': season,
            'player_type': player_type,
        }

        if player_type == 'batter':
            summary['expected_stats'] = self.get_expected_stats(player_id, season)
            summary['batted_ball'] = self.get_batted_ball_profile(player_id, season)
            summary['discipline'] = self.get_plate_discipline(player_id, season)
            summary['sprint_speed'] = self.get_player_sprint_speed(player_id, season)
        else:
            summary['expected_stats'] = self.get_pitcher_expected_stats(player_id, season)
            arsenal = self.get_pitch_arsenal(player_id, season)
            summary['pitch_arsenal'] = arsenal.to_dict(orient='records') if not arsenal.empty else []

        return summary


# Module-level instance for easy importing
client = SavantClient()
