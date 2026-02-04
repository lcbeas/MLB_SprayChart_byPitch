"""
Player-related API endpoints
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
from backend.data_sources.fangraphs import FangraphsClient

bp = Blueprint('players', __name__)


def get_fg_client():
    """Get Fangraphs client instance."""
    return FangraphsClient()


def df_to_json(df, limit=None):
    """Convert DataFrame to JSON-serializable list of dicts."""
    if df.empty:
        return []
    if limit:
        df = df.head(limit)
    # Handle NaN values
    return df.fillna('').to_dict(orient='records')


# -----------------------------------------------------------------------------
# Player Stats Endpoints
# -----------------------------------------------------------------------------

@bp.route('/batting', methods=['GET'])
def get_batting_stats():
    """
    Get batting statistics for a season.

    Query params:
        season: Year (default: current season)
        qual: Minimum PA (default: 1, use 'y' for qualified)
        limit: Max results (default: 100)
    """
    try:
        client = get_fg_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        qual = request.args.get('qual', 1)
        limit = request.args.get('limit', 100, type=int)

        # Convert qual to int if it's not 'y'
        if qual != 'y':
            qual = int(qual)

        stats = client.get_batting_stats(season, qual=qual)

        return jsonify({
            'season': season,
            'players': df_to_json(stats, limit=limit),
            'count': len(stats),
            'showing': min(limit, len(stats))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch batting stats: {str(e)}'}), 500


@bp.route('/pitching', methods=['GET'])
def get_pitching_stats():
    """
    Get pitching statistics for a season.

    Query params:
        season: Year (default: current season)
        qual: Minimum IP (default: 1, use 'y' for qualified)
        limit: Max results (default: 100)
    """
    try:
        client = get_fg_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        qual = request.args.get('qual', 1)
        limit = request.args.get('limit', 100, type=int)

        if qual != 'y':
            qual = int(qual)

        stats = client.get_pitching_stats(season, qual=qual)

        return jsonify({
            'season': season,
            'players': df_to_json(stats, limit=limit),
            'count': len(stats),
            'showing': min(limit, len(stats))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch pitching stats: {str(e)}'}), 500


@bp.route('/stats/history', methods=['GET'])
def get_historical_stats():
    """
    Get stats across multiple seasons.

    Query params:
        start_season: First year (default: 3 years ago)
        end_season: Last year (default: current)
        type: 'bat' or 'pit' (default: 'bat')
        limit: Max results per season
    """
    try:
        client = get_fg_client()
        current = client.get_current_season()

        start_season = request.args.get('start_season', current - 3, type=int)
        end_season = request.args.get('end_season', current, type=int)
        player_type = request.args.get('type', 'bat')
        limit = request.args.get('limit', 500, type=int)

        stats = client.get_multi_season_stats(start_season, end_season, player_type)

        return jsonify({
            'start_season': start_season,
            'end_season': end_season,
            'type': player_type,
            'players': df_to_json(stats, limit=limit),
            'count': len(stats)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch historical stats: {str(e)}'}), 500


# -----------------------------------------------------------------------------
# Projections Endpoints
# -----------------------------------------------------------------------------

@bp.route('/projections', methods=['GET'])
def get_projections_list():
    """
    Get player projections from a projection system.

    Query params:
        system: Projection system (steamer, zips, atc, thebat, depthcharts)
        type: 'bat' or 'pit' (default: 'bat')
        team: Filter by MLB team
        limit: Max results (default: 100)
    """
    try:
        client = get_fg_client()
        system = request.args.get('system', 'steamer')
        player_type = request.args.get('type', 'bat')
        team = request.args.get('team', '')
        limit = request.args.get('limit', 100, type=int)

        projections = client.get_projections(
            system=system,
            player_type=player_type,
            team=team
        )

        return jsonify({
            'system': system,
            'type': player_type,
            'team_filter': team or None,
            'projections': df_to_json(projections, limit=limit),
            'count': len(projections),
            'showing': min(limit, len(projections))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch projections: {str(e)}'}), 500


@bp.route('/projections/all', methods=['GET'])
def get_all_projections():
    """
    Get projections from all major systems combined.

    Query params:
        type: 'bat' or 'pit' (default: 'bat')
        systems: Comma-separated list of systems (default: steamer,zips,atc,thebatx)
        limit: Max results (default: 200)
    """
    try:
        client = get_fg_client()
        player_type = request.args.get('type', 'bat')
        systems_str = request.args.get('systems', 'steamer,zips,atc,thebatx')
        systems = [s.strip() for s in systems_str.split(',')]
        limit = request.args.get('limit', 200, type=int)

        projections = client.get_all_projections(systems=systems, player_type=player_type)

        return jsonify({
            'systems': systems,
            'type': player_type,
            'projections': df_to_json(projections, limit=limit),
            'count': len(projections),
            'showing': min(limit, len(projections))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch projections: {str(e)}'}), 500


@bp.route('/projections/depthcharts', methods=['GET'])
def get_depth_charts():
    """
    Get Fangraphs Depth Charts projections (playing time weighted).

    Query params:
        type: 'bat' or 'pit' (default: 'bat')
        limit: Max results (default: 100)
    """
    try:
        client = get_fg_client()
        player_type = request.args.get('type', 'bat')
        limit = request.args.get('limit', 100, type=int)

        projections = client.get_depth_charts(player_type=player_type)

        return jsonify({
            'system': 'depthcharts',
            'type': player_type,
            'projections': df_to_json(projections, limit=limit),
            'count': len(projections),
            'showing': min(limit, len(projections))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch depth charts: {str(e)}'}), 500


# -----------------------------------------------------------------------------
# Auction Values Endpoints
# -----------------------------------------------------------------------------

@bp.route('/values/auction', methods=['GET'])
def get_auction_values():
    """
    Get Ottoneu auction calculator values.

    Query params:
        format: Scoring format (fangraphs_points, sabr_points, 4x4, 5x5)
        teams: Number of teams (default: 12)
        budget: Budget per team (default: 400)
        projection: Projection system (default: steamer)
    """
    try:
        client = get_fg_client()
        scoring_format = request.args.get('format', 'fangraphs_points')
        teams = request.args.get('teams', 12, type=int)
        budget = request.args.get('budget', 400, type=int)
        projection = request.args.get('projection', 'steamer')

        values = client.get_auction_calculator(
            scoring_format=scoring_format,
            teams=teams,
            budget=budget,
            projection=projection
        )

        return jsonify({
            'format': scoring_format,
            'teams': teams,
            'budget': budget,
            'projection': projection,
            'values': df_to_json(values),
            'count': len(values)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch auction values: {str(e)}'}), 500


@bp.route('/values/ottoneu', methods=['GET'])
def get_ottoneu_values():
    """
    Get pre-calculated Ottoneu values from Fangraphs.

    Query params:
        format: Scoring format (fangraphs_points, sabr_points, 4x4, 5x5)
        limit: Max results (default: 100)
    """
    try:
        client = get_fg_client()
        scoring_format = request.args.get('format', 'fangraphs_points')
        limit = request.args.get('limit', 100, type=int)

        values = client.get_ottoneu_values(scoring_format=scoring_format)

        return jsonify({
            'format': scoring_format,
            'values': df_to_json(values, limit=limit),
            'count': len(values),
            'showing': min(limit, len(values))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch Ottoneu values: {str(e)}'}), 500


# -----------------------------------------------------------------------------
# Player Search & Detail Endpoints
# -----------------------------------------------------------------------------

@bp.route('/search', methods=['GET'])
def search_players():
    """
    Search for players by name.

    Query params:
        q: Search query (required)
        type: 'bat', 'pit', or 'all' (default: 'all')
        limit: Max results (default: 25)
    """
    query = request.args.get('q', '')
    player_type = request.args.get('type', 'all')
    limit = request.args.get('limit', 25, type=int)

    if not query:
        return jsonify({'error': 'Search query (q) is required'}), 400

    try:
        client = get_fg_client()
        results = client.search_players(query, player_type=player_type)

        return jsonify({
            'query': query,
            'type': player_type,
            'results': df_to_json(results, limit=limit),
            'count': len(results),
            'showing': min(limit, len(results))
        })
    except Exception as e:
        return jsonify({'error': f'Search failed: {str(e)}'}), 500


@bp.route('/<int:player_id>', methods=['GET'])
def get_player(player_id):
    """
    Get detailed data for a specific player (by Fangraphs ID).

    Query params:
        None currently
    """
    try:
        client = get_fg_client()
        player_info = client.get_player_page(player_id)

        return jsonify(player_info)
    except Exception as e:
        return jsonify({'error': f'Failed to fetch player: {str(e)}'}), 500


@bp.route('/<int:player_id>/stats', methods=['GET'])
def get_player_stats(player_id):
    """
    Get historical stats for a specific player.

    Query params:
        start_season: First year (default: 5 years ago)
        end_season: Last year (default: current)
    """
    try:
        client = get_fg_client()
        current = client.get_current_season()

        start_season = request.args.get('start_season', current - 5, type=int)
        end_season = request.args.get('end_season', current, type=int)

        stats = client.get_player_stats(player_id, start_season, end_season)

        return jsonify({
            'player_id': player_id,
            'start_season': start_season,
            'end_season': end_season,
            'batting': df_to_json(stats['batting']) if not stats['batting'].empty else [],
            'pitching': df_to_json(stats['pitching']) if not stats['pitching'].empty else []
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch player stats: {str(e)}'}), 500


@bp.route('/<int:player_id>/projections', methods=['GET'])
def get_player_projections(player_id):
    """
    Get projections for a specific player from multiple systems.

    Query params:
        systems: Comma-separated list (default: steamer,zips,atc)
        type: 'bat' or 'pit' (default: 'bat')
    """
    try:
        client = get_fg_client()
        systems_str = request.args.get('systems', 'steamer,zips,atc')
        systems = [s.strip() for s in systems_str.split(',')]
        player_type = request.args.get('type', 'bat')

        projections_by_system = {}

        for system in systems:
            proj = client.get_projections(system=system, player_type=player_type)
            if not proj.empty and 'fg_id' in proj.columns:
                player_proj = proj[proj['fg_id'] == player_id]
                if not player_proj.empty:
                    projections_by_system[system] = player_proj.iloc[0].to_dict()

        return jsonify({
            'player_id': player_id,
            'type': player_type,
            'projections': projections_by_system
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch projections: {str(e)}'}), 500


@bp.route('/<int:player_id>/compare', methods=['GET'])
def compare_player_to_projections(player_id):
    """
    Compare a player's actual stats to projections.

    Query params:
        season: Year to compare (default: previous season)
        type: 'bat' or 'pit' (default: 'bat')
    """
    try:
        client = get_fg_client()
        current = client.get_current_season()
        season = request.args.get('season', current - 1, type=int)
        player_type = request.args.get('type', 'bat')

        comparison = client.compare_to_projections(player_id, season, player_type)

        return jsonify(comparison)
    except Exception as e:
        return jsonify({'error': f'Failed to compare stats: {str(e)}'}), 500


# -----------------------------------------------------------------------------
# Utility Endpoints
# -----------------------------------------------------------------------------

@bp.route('/systems', methods=['GET'])
def get_projection_systems():
    """Get list of available projection systems."""
    client = get_fg_client()
    return jsonify({
        'projection_systems': list(client.PROJECTION_SYSTEMS.keys()),
        'scoring_formats': list(client.OTTONEU_FORMATS.keys())
    })


@bp.route('/seasons', methods=['GET'])
def get_seasons():
    """Get current and recent season years."""
    client = get_fg_client()
    current = client.get_current_season()
    previous = client.get_previous_seasons(5)

    return jsonify({
        'current_season': current,
        'previous_seasons': previous,
        'all_seasons': previous + [current]
    })


# -----------------------------------------------------------------------------
# Statcast Endpoints
# -----------------------------------------------------------------------------

def get_savant_client():
    """Get Baseball Savant client instance."""
    from backend.data_sources.savant import SavantClient
    return SavantClient()


@bp.route('/statcast/leaderboard', methods=['GET'])
def get_statcast_leaderboard():
    """
    Get Statcast exit velocity and barrel leaderboard.

    Query params:
        season: Year (default: current)
        type: 'batter' or 'pitcher' (default: 'batter')
        min_pa: Minimum plate appearances (default: 50)
        limit: Max results (default: 100)
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        player_type = request.args.get('type', 'batter')
        min_pa = request.args.get('min_pa', 50, type=int)
        limit = request.args.get('limit', 100, type=int)

        leaderboard = client.get_statcast_leaderboard(season, player_type, min_pa)

        return jsonify({
            'season': season,
            'type': player_type,
            'min_pa': min_pa,
            'leaderboard': df_to_json(leaderboard, limit=limit),
            'count': len(leaderboard),
            'showing': min(limit, len(leaderboard))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch Statcast leaderboard: {str(e)}'}), 500


@bp.route('/statcast/expected', methods=['GET'])
def get_expected_stats_leaderboard():
    """
    Get expected stats (xwOBA, xBA, xSLG) leaderboard.

    Query params:
        season: Year (default: current)
        type: 'batter' or 'pitcher' (default: 'batter')
        min_pa: Minimum plate appearances (default: 50)
        limit: Max results (default: 100)
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        player_type = request.args.get('type', 'batter')
        min_pa = request.args.get('min_pa', 50, type=int)
        limit = request.args.get('limit', 100, type=int)

        leaderboard = client.get_expected_stats_leaderboard(season, player_type, min_pa)

        return jsonify({
            'season': season,
            'type': player_type,
            'min_pa': min_pa,
            'leaderboard': df_to_json(leaderboard, limit=limit),
            'count': len(leaderboard),
            'showing': min(limit, len(leaderboard))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch expected stats: {str(e)}'}), 500


@bp.route('/statcast/sprint-speed', methods=['GET'])
def get_sprint_speed_leaderboard():
    """
    Get sprint speed leaderboard.

    Query params:
        season: Year (default: current)
        min_opps: Minimum opportunities (default: 10)
        limit: Max results (default: 100)
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        min_opps = request.args.get('min_opps', 10, type=int)
        limit = request.args.get('limit', 100, type=int)

        leaderboard = client.get_sprint_speed_leaderboard(season, min_opps)

        return jsonify({
            'season': season,
            'min_opps': min_opps,
            'leaderboard': df_to_json(leaderboard, limit=limit),
            'count': len(leaderboard),
            'showing': min(limit, len(leaderboard))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch sprint speed: {str(e)}'}), 500


@bp.route('/statcast/pitch-arsenal', methods=['GET'])
def get_pitch_arsenal_leaderboard():
    """
    Get pitch arsenal leaderboard for a specific pitch type.

    Query params:
        season: Year (default: current)
        pitch_type: Pitch type code (FF, SL, CH, etc.) (default: FF)
        min_pitches: Minimum pitches thrown (default: 100)
        limit: Max results (default: 100)
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        pitch_type = request.args.get('pitch_type', 'FF')
        min_pitches = request.args.get('min_pitches', 100, type=int)
        limit = request.args.get('limit', 100, type=int)

        leaderboard = client.get_pitch_arsenal_leaderboard(season, pitch_type, min_pitches)

        return jsonify({
            'season': season,
            'pitch_type': pitch_type,
            'min_pitches': min_pitches,
            'leaderboard': df_to_json(leaderboard, limit=limit),
            'count': len(leaderboard),
            'showing': min(limit, len(leaderboard))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch pitch arsenal: {str(e)}'}), 500


@bp.route('/<int:player_id>/statcast', methods=['GET'])
def get_player_statcast(player_id):
    """
    Get comprehensive Statcast summary for a player (by MLBAM ID).

    Query params:
        season: Year (default: current)
        type: 'batter' or 'pitcher' (default: 'batter')
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        player_type = request.args.get('type', 'batter')

        summary = client.get_player_summary(player_id, season, player_type)

        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': f'Failed to fetch Statcast data: {str(e)}'}), 500


@bp.route('/<int:player_id>/statcast/expected', methods=['GET'])
def get_player_expected_stats(player_id):
    """
    Get expected stats for a specific player (by MLBAM ID).

    Query params:
        season: Year (default: current)
        type: 'batter' or 'pitcher' (default: 'batter')
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        player_type = request.args.get('type', 'batter')

        if player_type == 'batter':
            stats = client.get_expected_stats(player_id, season)
        else:
            stats = client.get_pitcher_expected_stats(player_id, season)

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': f'Failed to fetch expected stats: {str(e)}'}), 500


@bp.route('/<int:player_id>/statcast/batted-ball', methods=['GET'])
def get_player_batted_ball(player_id):
    """
    Get batted ball profile for a batter (by MLBAM ID).

    Query params:
        season: Year (default: current)
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)

        profile = client.get_batted_ball_profile(player_id, season)

        return jsonify(profile)
    except Exception as e:
        return jsonify({'error': f'Failed to fetch batted ball profile: {str(e)}'}), 500


@bp.route('/<int:player_id>/statcast/discipline', methods=['GET'])
def get_player_discipline(player_id):
    """
    Get plate discipline metrics for a batter (by MLBAM ID).

    Query params:
        season: Year (default: current)
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)

        discipline = client.get_plate_discipline(player_id, season)

        return jsonify(discipline)
    except Exception as e:
        return jsonify({'error': f'Failed to fetch plate discipline: {str(e)}'}), 500


@bp.route('/<int:player_id>/statcast/arsenal', methods=['GET'])
def get_player_arsenal(player_id):
    """
    Get pitch arsenal breakdown for a pitcher (by MLBAM ID).

    Query params:
        season: Year (default: current)
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)

        arsenal = client.get_pitch_arsenal(player_id, season)

        return jsonify({
            'player_id': player_id,
            'season': season,
            'pitches': df_to_json(arsenal)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch pitch arsenal: {str(e)}'}), 500


@bp.route('/<int:player_id>/statcast/rolling', methods=['GET'])
def get_player_rolling_stats(player_id):
    """
    Get rolling Statcast stats for a player (by MLBAM ID).

    Query params:
        season: Year (default: current)
        window: Rolling window size in batted balls (default: 50)
        type: 'batter' or 'pitcher' (default: 'batter')
    """
    try:
        client = get_savant_client()
        season = request.args.get('season', client.get_current_season(), type=int)
        window = request.args.get('window', 50, type=int)
        player_type = request.args.get('type', 'batter')

        rolling = client.get_rolling_stats(player_id, season, window, player_type)

        return jsonify({
            'player_id': player_id,
            'season': season,
            'window': window,
            'rolling_stats': df_to_json(rolling)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch rolling stats: {str(e)}'}), 500


@bp.route('/statcast/lookup', methods=['GET'])
def lookup_player_mlbam_id():
    """
    Look up a player's MLBAM ID by name.

    Query params:
        name: Full player name (e.g., "Mike Trout")
        -- OR --
        first: First name
        last: Last name
    """
    try:
        client = get_savant_client()

        full_name = request.args.get('name', '')
        first_name = request.args.get('first', '')
        last_name = request.args.get('last', '')

        if full_name:
            player_id = client.lookup_player_by_name(full_name)
        elif first_name and last_name:
            player_id = client.lookup_player_id(last_name, first_name)
        else:
            return jsonify({'error': 'Provide name or first+last parameters'}), 400

        if player_id:
            return jsonify({
                'name': full_name or f"{first_name} {last_name}",
                'mlbam_id': player_id
            })
        else:
            return jsonify({
                'name': full_name or f"{first_name} {last_name}",
                'mlbam_id': None,
                'message': 'Player not found'
            }), 404

    except Exception as e:
        return jsonify({'error': f'Lookup failed: {str(e)}'}), 500
