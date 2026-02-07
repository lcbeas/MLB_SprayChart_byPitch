/**
 * Ottoneu Roster Tool - Main Application JavaScript
 */

// =============================================================================
// State Management
// =============================================================================
const state = {
    teamId: localStorage.getItem('teamId') || null,
    teamName: localStorage.getItem('teamName') || null,
    leagueId: localStorage.getItem('leagueId') || '1395',
    currentPlayerId: null,
    teams: [],
    tradePlayers: {
        give: [],
        get: []
    }
};

// =============================================================================
// API Client
// =============================================================================
const api = {
    baseUrl: '/api',

    async get(endpoint, params = {}) {
        const url = new URL(`${this.baseUrl}${endpoint}`, window.location.origin);
        // Always include league_id in requests
        if (!params.league_id && state.leagueId) {
            params.league_id = state.leagueId;
        }
        Object.entries(params).forEach(([key, value]) => {
            if (value !== null && value !== undefined && value !== '') {
                url.searchParams.append(key, value);
            }
        });

        try {
            showLoading();
            const response = await fetch(url);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        } finally {
            hideLoading();
        }
    },

    async post(endpoint, data) {
        try {
            showLoading();
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        } finally {
            hideLoading();
        }
    },

    // League endpoints
    getTeams(leagueId) {
        return this.get('/league/teams', { league_id: leagueId });
    },

    getLeagueInfo() {
        return this.get('/league/info');
    },

    // Analysis endpoints
    analyzeRoster(teamId, compareTo = 'league') {
        return this.get('/analysis/roster/analyze', { team_id: teamId, compare_to: compareTo });
    },

    getRosterScore(teamId) {
        return this.get('/analysis/roster/score', { team_id: teamId });
    },

    getPositionalAnalysis(teamId) {
        return this.get('/analysis/roster/positions', { team_id: teamId });
    },

    getRosterRecommendations(teamId) {
        return this.get('/analysis/roster/recommendations', { team_id: teamId });
    },

    evaluateTrade(givePlayers, getPlayers, teamId) {
        return this.post('/analysis/trade/evaluate', {
            give_players: givePlayers,
            get_players: getPlayers,
            team_id: teamId
        });
    },

    findTradeTargets(teamId, position, maxSalary) {
        return this.get('/analysis/trade/targets', {
            team_id: teamId,
            position,
            max_salary: maxSalary
        });
    },

    suggestTrades(teamId, targetPosition) {
        return this.get('/analysis/trade/suggest', {
            team_id: teamId,
            target_position: targetPosition
        });
    },

    // ML endpoints
    optimizeLineup(roster, matchups, inningLimits, date) {
        return this.post('/ml/lineup/optimize', { roster, matchups, inning_limits: inningLimits, date });
    },

    getPlayerValue(playerId, playerType, mlbamId) {
        return this.get('/ml/value/predict', {
            player_id: playerId,
            player_type: playerType,
            mlbam_id: mlbamId
        });
    },

    getBidRecommendation(playerId, playerType, currentBid, budget) {
        return this.get('/ml/value/bid-recommendation', {
            player_id: playerId,
            player_type: playerType,
            current_bid: currentBid,
            budget_remaining: budget
        });
    },

    identifyBuyLowSellHigh(roster, threshold = 0.2) {
        return this.post('/ml/value/buy-low-sell-high', { roster, threshold });
    },

    // League endpoints
    getFreeAgents(position) {
        return this.get('/league/free-agents', { position });
    },

    getRoster(teamId) {
        return this.get('/league/roster', { team_id: teamId });
    },

    searchPlayers(query) {
        return this.get('/players/search', { q: query });
    },

    // Search Ottoneu players only (active players for trades)
    searchOttoneuPlayers(query) {
        return this.get('/league/search', { q: query });
    }
};

// =============================================================================
// UI Helpers
// =============================================================================
function showLoading() {
    document.getElementById('loading-overlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function formatCurrency(value) {
    return `$${Math.round(value)}`;
}

function formatPercent(value) {
    return `${Math.round(value * 100)}%`;
}

// =============================================================================
// Tab Navigation
// =============================================================================
function initTabNavigation() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;

            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            tabContents.forEach(content => {
                content.classList.remove('active');
                if (content.id === tabId) {
                    content.classList.add('active');
                }
            });
        });
    });

    // Trade sub-tabs
    const tradeTabBtns = document.querySelectorAll('.trade-tab-btn');
    const tradePanels = document.querySelectorAll('.trade-panel');

    tradeTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const panelId = btn.dataset.tradeTab;

            tradeTabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            tradePanels.forEach(panel => {
                panel.classList.remove('active');
                if (panel.id === `${panelId}-trade-panel` || panel.id === `${panelId}-panel` ||
                    panel.id === `find-targets-panel` && panelId === 'targets' ||
                    panel.id === `suggestions-panel` && panelId === 'suggestions' ||
                    panel.id === `evaluate-trade-panel` && panelId === 'evaluate') {
                    panel.classList.add('active');
                }
            });
        });
    });
}

// =============================================================================
// League & Team Management
// =============================================================================
function initLeagueTeamControls() {
    const leagueInput = document.getElementById('league-id-input');
    const refreshBtn = document.getElementById('refresh-league-btn');
    const teamSelect = document.getElementById('team-select');

    // Set initial values from state
    if (state.leagueId) {
        leagueInput.value = state.leagueId;
    }

    // Load teams on page load
    loadTeams();

    // Refresh league button
    refreshBtn.addEventListener('click', async () => {
        const leagueId = leagueInput.value.trim();
        if (!leagueId) {
            showToast('Please enter a league ID', 'error');
            return;
        }

        state.leagueId = leagueId;
        localStorage.setItem('leagueId', leagueId);

        // Clear current team selection
        state.teamId = null;
        state.teamName = null;
        localStorage.removeItem('teamId');
        localStorage.removeItem('teamName');

        await loadTeams();
        showToast(`Loaded league ${leagueId}`, 'success');
    });

    // Team selection change
    teamSelect.addEventListener('change', () => {
        const selectedOption = teamSelect.options[teamSelect.selectedIndex];
        if (selectedOption.value) {
            state.teamId = selectedOption.value;
            state.teamName = selectedOption.textContent;
            localStorage.setItem('teamId', state.teamId);
            localStorage.setItem('teamName', state.teamName);
            showToast(`Selected team: ${state.teamName}`, 'success');
        } else {
            state.teamId = null;
            state.teamName = null;
            localStorage.removeItem('teamId');
            localStorage.removeItem('teamName');
        }
    });
}

async function loadTeams() {
    const teamSelect = document.getElementById('team-select');

    try {
        const data = await api.getTeams(state.leagueId);
        state.teams = data.teams || [];

        // Clear and populate dropdown
        teamSelect.innerHTML = '<option value="">Select your team...</option>';

        state.teams.forEach(team => {
            const option = document.createElement('option');
            option.value = team.team_id;
            option.textContent = team.team_name || `Team ${team.team_id}`;

            // Add rank info if available
            if (team.rank) {
                option.textContent += ` (#${team.rank})`;
            }

            // Pre-select if matches saved team
            if (state.teamId && String(team.team_id) === String(state.teamId)) {
                option.selected = true;
            }

            teamSelect.appendChild(option);
        });

        if (state.teams.length === 0) {
            teamSelect.innerHTML = '<option value="">No teams found</option>';
        }

    } catch (error) {
        console.error('Failed to load teams:', error);
        teamSelect.innerHTML = '<option value="">Error loading teams</option>';
        showToast('Failed to load teams. Check league ID.', 'error');
    }
}

// =============================================================================
// Roster Optimizer
// =============================================================================
function initRosterOptimizer() {
    const analyzeBtn = document.getElementById('analyze-roster-btn');
    const compareSelect = document.getElementById('compare-to-select');

    analyzeBtn.addEventListener('click', async () => {
        if (!state.teamId) {
            showToast('Please select your team first', 'error');
            return;
        }

        try {
            const compareTo = compareSelect.value;
            const [analysis, score, positions] = await Promise.all([
                api.analyzeRoster(state.teamId, compareTo),
                api.getRosterScore(state.teamId),
                api.getPositionalAnalysis(state.teamId)
            ]);

            renderRosterAnalysis(analysis, score, positions);

            // Get buy low / sell high from ML
            if (analysis.roster) {
                const opportunities = await api.identifyBuyLowSellHigh(analysis.roster);
                renderValueOpportunities(opportunities);
            }

            // Get recommendations
            const recommendations = await api.getRosterRecommendations(state.teamId);
            renderRecommendations(recommendations);

        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
}

function renderRosterAnalysis(analysis, score, positions) {
    // Hide placeholder
    document.querySelector('#roster-analysis .placeholder-message')?.classList.add('hidden');

    // Show score card
    const scoreSection = document.getElementById('roster-score-section');
    scoreSection.classList.remove('hidden');

    document.getElementById('roster-grade').textContent = score.grade || 'B';
    document.getElementById('batting-score').textContent = score.batting_score?.toFixed(1) || '-';
    document.getElementById('pitching-score').textContent = score.pitching_score?.toFixed(1) || '-';
    document.getElementById('total-value').textContent = formatCurrency(score.total_value || 0);

    // Render positional analysis
    const positionSection = document.getElementById('positional-analysis');
    const positionGrid = document.getElementById('position-grid');
    positionSection.classList.remove('hidden');

    positionGrid.innerHTML = '';
    const positionData = positions.positions || {};

    Object.entries(positionData).forEach(([pos, data]) => {
        const card = document.createElement('div');
        const strength = data.rank <= 4 ? 'strong' : data.rank >= 9 ? 'weak' : '';
        card.className = `position-card ${strength}`;
        card.innerHTML = `
            <h4>${pos}</h4>
            <p>Rank: #${data.rank || '-'} in league</p>
            <p>Value: ${formatCurrency(data.value || 0)}</p>
            <p>Players: ${data.player_count || 0}</p>
        `;
        positionGrid.appendChild(card);
    });
}

function renderValueOpportunities(opportunities) {
    const section = document.getElementById('value-opportunities');
    section.classList.remove('hidden');

    const buyLowList = document.getElementById('buy-low-list');
    const sellHighList = document.getElementById('sell-high-list');

    buyLowList.innerHTML = '';
    sellHighList.innerHTML = '';

    (opportunities.buy_low || []).forEach(player => {
        buyLowList.innerHTML += `
            <div class="player-item">
                <span class="name">${player.name || player.Name}</span>
                <span class="value value-positive">+${formatCurrency(player.surplus || 0)} surplus</span>
            </div>
        `;
    });

    (opportunities.sell_high || []).forEach(player => {
        sellHighList.innerHTML += `
            <div class="player-item">
                <span class="name">${player.name || player.Name}</span>
                <span class="value value-negative">${formatCurrency(player.surplus || 0)} overvalued</span>
            </div>
        `;
    });

    if (buyLowList.innerHTML === '') {
        buyLowList.innerHTML = '<p class="text-muted">No buy low candidates found</p>';
    }
    if (sellHighList.innerHTML === '') {
        sellHighList.innerHTML = '<p class="text-muted">No sell high candidates found</p>';
    }
}

function renderRecommendations(data) {
    const section = document.getElementById('recommendations-section');
    const list = document.getElementById('recommendations-list');

    section.classList.remove('hidden');
    list.innerHTML = '';

    (data.recommendations || []).forEach(rec => {
        list.innerHTML += `<li>${rec.message || rec}</li>`;
    });

    if (list.innerHTML === '') {
        list.innerHTML = '<li>No specific recommendations at this time</li>';
    }
}

// =============================================================================
// Lineup Optimizer
// =============================================================================
function initLineupOptimizer() {
    const optimizeBtn = document.getElementById('optimize-lineup-btn');
    const dateInput = document.getElementById('lineup-date');

    // Set default date to today
    dateInput.valueAsDate = new Date();

    optimizeBtn.addEventListener('click', async () => {
        if (!state.teamId) {
            showToast('Please select your team first', 'error');
            return;
        }

        try {
            // Get roster first
            const rosterData = await api.getRoster(state.teamId);

            if (!rosterData.roster || rosterData.roster.length === 0) {
                showToast('No roster data found', 'error');
                return;
            }

            // Optimize lineup
            const result = await api.optimizeLineup(
                rosterData.roster,
                {},  // matchups would come from another API
                {},  // inning limits
                dateInput.value
            );

            renderOptimizedLineup(result);

        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
}

function renderOptimizedLineup(result) {
    // Hide placeholder
    document.querySelector('#lineup-container .placeholder-message')?.classList.add('hidden');

    // Show batting lineup
    const battingSection = document.getElementById('batting-lineup-section');
    const battingTable = document.querySelector('#batting-lineup-table tbody');
    battingSection.classList.remove('hidden');

    document.getElementById('expected-batting-pts').textContent =
        (result.batting_lineup?.expected_points || 0).toFixed(1);

    battingTable.innerHTML = '';
    (result.batting_lineup?.lineup || []).forEach((player, idx) => {
        battingTable.innerHTML += `
            <tr>
                <td>${player.slot || idx + 1}</td>
                <td>${player.name}</td>
                <td>${player.position}</td>
                <td>${player.matchup || '-'}</td>
                <td>${(player.expected_points || 0).toFixed(1)}</td>
            </tr>
        `;
    });

    // Show pitching lineup
    const pitchingSection = document.getElementById('pitching-lineup-section');
    const pitchingTable = document.querySelector('#pitching-lineup-table tbody');
    pitchingSection.classList.remove('hidden');

    document.getElementById('expected-pitching-pts').textContent =
        (result.pitching_lineup?.expected_points || 0).toFixed(1);

    pitchingTable.innerHTML = '';
    (result.pitching_lineup?.lineup || []).forEach((player, idx) => {
        pitchingTable.innerHTML += `
            <tr>
                <td>${player.slot || idx + 1}</td>
                <td>${player.name}</td>
                <td>${player.remaining_ip || '-'}</td>
                <td>${(player.expected_points || 0).toFixed(1)}</td>
            </tr>
        `;
    });

    // Show inning limits
    if (result.inning_limits) {
        const limitsSection = document.getElementById('inning-limits-section');
        limitsSection.classList.remove('hidden');

        document.getElementById('used-ip').textContent = `${result.used_ip || 0} IP`;
        document.getElementById('remaining-ip').textContent = `${result.remaining_ip || 1500} IP`;
    }

    // Show warnings
    if (result.warnings && result.warnings.length > 0) {
        const warningsSection = document.getElementById('lineup-warnings');
        const warningsList = document.getElementById('warnings-list');
        warningsSection.classList.remove('hidden');

        warningsList.innerHTML = '';
        result.warnings.forEach(warning => {
            warningsList.innerHTML += `<li>${warning}</li>`;
        });
    }
}

// =============================================================================
// Trade Analyzer
// =============================================================================
function initTradeAnalyzer() {
    initTradeEvaluator();
    initTradeTargets();
    initTradeSuggestions();
}

function initTradeEvaluator() {
    const evaluateBtn = document.getElementById('evaluate-trade-btn');

    evaluateBtn.addEventListener('click', async () => {
        if (state.tradePlayers.give.length === 0 || state.tradePlayers.get.length === 0) {
            showToast('Please add players to both sides of the trade', 'error');
            return;
        }

        try {
            const result = await api.evaluateTrade(
                state.tradePlayers.give,
                state.tradePlayers.get,
                state.teamId
            );

            renderTradeEvaluation(result);

        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });

    // Player search for trade builder - uses Ottoneu players only (active)
    ['give', 'get'].forEach(side => {
        const searchInput = document.getElementById(`${side}-player-search`);
        const resultsDiv = document.getElementById(`${side}-search-results`);

        searchInput.addEventListener('input', debounce(async (e) => {
            const query = e.target.value.trim();
            if (query.length < 2) {
                resultsDiv.classList.add('hidden');
                return;
            }

            try {
                // Use Ottoneu search for active players only
                const data = await api.searchOttoneuPlayers(query);
                renderSearchResults(data.results || [], resultsDiv, side);
            } catch (error) {
                console.error('Search error:', error);
            }
        }, 300));
    });
}

function renderSearchResults(players, container, side) {
    container.classList.remove('hidden');
    container.innerHTML = '';

    players.slice(0, 8).forEach(player => {
        const item = document.createElement('div');
        item.className = 'search-dropdown-item';

        // Get salary - check various column names
        const salary = player.current_salary || player.salary || player.avg_salary || 0;
        const salaryDisplay = salary > 0 ? `$${parseFloat(salary).toFixed(0)}` : 'FA';

        // Check if rostered
        const ownerDisplay = player.owner_name ? ` - ${player.owner_name}` : '';

        item.textContent = `${player.name} (${player.position || 'N/A'}) ${salaryDisplay}${ownerDisplay}`;
        item.addEventListener('click', () => {
            // Store salary info with player
            player.salary = salary;
            addPlayerToTrade(player, side);
            container.classList.add('hidden');
            document.getElementById(`${side}-player-search`).value = '';
        });
        container.appendChild(item);
    });

    if (players.length === 0) {
        container.innerHTML = '<div class="search-dropdown-item">No players found</div>';
    }
}

function addPlayerToTrade(player, side) {
    state.tradePlayers[side].push(player);
    renderTradePlayers();
}

function removePlayerFromTrade(index, side) {
    state.tradePlayers[side].splice(index, 1);
    renderTradePlayers();
}

function renderTradePlayers() {
    ['give', 'get'].forEach(side => {
        const container = document.getElementById(`${side}-players`);
        container.innerHTML = '';

        state.tradePlayers[side].forEach((player, idx) => {
            const salary = player.salary || player.current_salary || player.avg_salary || 0;
            const salaryDisplay = salary > 0 ? `$${parseFloat(salary).toFixed(0)}` : 'FA';
            container.innerHTML += `
                <div class="trade-player-item">
                    <span>${player.name} (${player.position || 'N/A'}) - ${salaryDisplay}</span>
                    <button class="remove-btn" onclick="removePlayerFromTrade(${idx}, '${side}')">x</button>
                </div>
            `;
        });
    });
}

function renderTradeEvaluation(result) {
    const evalSection = document.getElementById('trade-evaluation');
    evalSection.classList.remove('hidden');

    // Update fairness meter
    const fairnessIndicator = document.getElementById('fairness-indicator');
    const fairnessLabel = document.getElementById('fairness-label');

    const fairnessScore = result.fairness_score || 0.5;
    fairnessIndicator.style.left = `${fairnessScore * 100}%`;

    if (fairnessScore > 0.6) {
        fairnessLabel.textContent = 'Good Trade for You!';
        fairnessLabel.style.color = 'var(--success)';
    } else if (fairnessScore < 0.4) {
        fairnessLabel.textContent = 'Bad Trade for You';
        fairnessLabel.style.color = 'var(--danger)';
    } else {
        fairnessLabel.textContent = 'Fair Trade';
        fairnessLabel.style.color = 'var(--warning)';
    }

    // Update values
    document.getElementById('your-trade-value').textContent = formatCurrency(result.give_value || 0);
    document.getElementById('their-trade-value').textContent = formatCurrency(result.get_value || 0);

    const netValue = (result.get_value || 0) - (result.give_value || 0);
    document.getElementById('net-trade-value').textContent = formatCurrency(netValue);
    document.getElementById('net-trade-value').className =
        `value ${netValue >= 0 ? 'value-positive' : 'value-negative'}`;

    // Recommendation
    const recBox = document.getElementById('trade-recommendation');
    if (result.recommendation === 'accept') {
        recBox.className = 'recommendation-box accept';
        recBox.textContent = 'Recommend: ACCEPT this trade';
    } else if (result.recommendation === 'decline') {
        recBox.className = 'recommendation-box decline';
        recBox.textContent = 'Recommend: DECLINE this trade';
    } else {
        recBox.className = 'recommendation-box consider';
        recBox.textContent = 'Consider carefully - close to fair value';
    }
}

function initTradeTargets() {
    const findBtn = document.getElementById('find-targets-btn');

    findBtn.addEventListener('click', async () => {
        if (!state.teamId) {
            showToast('Please select your team first', 'error');
            return;
        }

        const position = document.getElementById('target-position').value;
        const maxSalary = document.getElementById('max-salary').value;

        try {
            const result = await api.findTradeTargets(state.teamId, position, maxSalary);
            renderTradeTargets(result);
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
}

function renderTradeTargets(result) {
    const container = document.getElementById('trade-targets-list');
    container.innerHTML = '';

    (result.targets || []).forEach(target => {
        container.innerHTML += `
            <div class="card">
                <h4>${target.name}</h4>
                <p>Position: ${target.position} | Team: ${target.team_name || 'Unknown'}</p>
                <p>Salary: ${formatCurrency(target.salary)} | Value: ${formatCurrency(target.predicted_value || target.value)}</p>
                <p>Owner likely to trade: ${target.trade_likelihood || 'Unknown'}</p>
            </div>
        `;
    });

    if (container.innerHTML === '') {
        container.innerHTML = '<div class="placeholder-message"><p>No trade targets found matching criteria</p></div>';
    }
}

function initTradeSuggestions() {
    const getBtn = document.getElementById('get-suggestions-btn');

    getBtn.addEventListener('click', async () => {
        if (!state.teamId) {
            showToast('Please select your team first', 'error');
            return;
        }

        const targetPosition = document.getElementById('improve-position').value;

        try {
            const result = await api.suggestTrades(state.teamId, targetPosition);
            renderTradeSuggestions(result);
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
}

function renderTradeSuggestions(result) {
    const container = document.getElementById('trade-suggestions-list');
    container.innerHTML = '';

    (result.suggestions || []).forEach(suggestion => {
        container.innerHTML += `
            <div class="card">
                <h4>Trade with ${suggestion.partner_team || 'Team'}</h4>
                <p><strong>Give:</strong> ${(suggestion.give || []).map(p => p.name).join(', ')}</p>
                <p><strong>Get:</strong> ${(suggestion.get || []).map(p => p.name).join(', ')}</p>
                <p>Net Value: <span class="${suggestion.net_value >= 0 ? 'value-positive' : 'value-negative'}">
                    ${formatCurrency(suggestion.net_value || 0)}
                </span></p>
                <p>Reason: ${suggestion.reason || 'Improves roster balance'}</p>
            </div>
        `;
    });

    if (container.innerHTML === '') {
        container.innerHTML = '<div class="placeholder-message"><p>No trade suggestions available</p></div>';
    }
}

// =============================================================================
// Player Value Tool
// =============================================================================
function initPlayerValue() {
    const getValueBtn = document.getElementById('get-value-btn');
    const searchInput = document.getElementById('value-player-search');
    const typeSelect = document.getElementById('player-type-select');
    const getBidBtn = document.getElementById('get-bid-rec-btn');

    getValueBtn.addEventListener('click', async () => {
        const query = searchInput.value.trim();
        if (!query) {
            showToast('Please enter a player name', 'error');
            return;
        }

        try {
            // Search for player first
            const searchResult = await api.searchPlayers(query);
            if (!searchResult.results || searchResult.results.length === 0) {
                showToast('Player not found', 'error');
                return;
            }

            const player = searchResult.results[0];
            state.currentPlayerId = player.player_id || player.fg_id;

            // Get player value
            const result = await api.getPlayerValue(
                state.currentPlayerId,
                typeSelect.value,
                player.mlbam_id
            );

            renderPlayerValue(player, result);

        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });

    getBidBtn.addEventListener('click', async () => {
        if (!state.currentPlayerId) {
            showToast('Please search for a player first', 'error');
            return;
        }

        const currentBid = parseFloat(document.getElementById('current-bid').value) || 0;
        const budget = parseFloat(document.getElementById('budget-remaining').value) || 400;

        try {
            const result = await api.getBidRecommendation(
                state.currentPlayerId,
                document.getElementById('player-type-select').value,
                currentBid,
                budget
            );

            renderBidRecommendation(result);

        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
}

function renderPlayerValue(player, result) {
    const valueSection = document.getElementById('player-value-result');
    const bidSection = document.getElementById('bid-section');

    valueSection.classList.remove('hidden');
    bidSection.classList.remove('hidden');

    document.getElementById('value-player-name').textContent = player.name;
    document.getElementById('value-player-type').textContent =
        document.getElementById('player-type-select').value === 'pitcher' ? 'Pitcher' : 'Batter';

    document.getElementById('predicted-value').textContent = formatCurrency(result.predicted_value || 0);

    const confidence = result.confidence || 0.5;
    document.getElementById('confidence-fill').style.width = `${confidence * 100}%`;
    document.getElementById('confidence-pct').textContent = formatPercent(confidence);

    // Model breakdown
    const predictions = result.model_predictions || {};
    document.getElementById('gbm-value').textContent = predictions.gbm ? `${predictions.gbm.toFixed(1)} WAR` : '-';
    document.getElementById('rf-value').textContent = predictions.rf ? `${predictions.rf.toFixed(1)} WAR` : '-';
    document.getElementById('ridge-value').textContent = predictions.ridge ? `${predictions.ridge.toFixed(1)} WAR` : '-';
}

function renderBidRecommendation(result) {
    const bidSection = document.getElementById('bid-recommendation');
    bidSection.classList.remove('hidden');

    const verdict = document.getElementById('bid-verdict');
    if (result.should_bid) {
        verdict.textContent = 'BID!';
        verdict.className = 'verdict bid';
    } else {
        verdict.textContent = 'PASS';
        verdict.className = 'verdict pass';
    }

    document.getElementById('max-bid').textContent = formatCurrency(result.max_recommended_bid || 0);
    document.getElementById('adjusted-value').textContent = formatCurrency(result.adjusted_value || 0);

    const reasoningList = document.getElementById('bid-reasoning');
    reasoningList.innerHTML = '';
    (result.reasoning || []).forEach(reason => {
        reasoningList.innerHTML += `<li>${reason}</li>`;
    });
}

// =============================================================================
// Free Agents
// =============================================================================
function initFreeAgents() {
    const loadBtn = document.getElementById('load-fa-btn');
    const positionFilter = document.getElementById('fa-position-filter');

    loadBtn.addEventListener('click', async () => {
        try {
            const position = positionFilter.value;
            const result = await api.getFreeAgents(position);
            renderFreeAgents(result);
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
}

function renderFreeAgents(result) {
    const container = document.getElementById('fa-results');

    if (!result.free_agents || result.free_agents.length === 0) {
        container.innerHTML = '<div class="placeholder-message"><p>No free agents found</p></div>';
        return;
    }

    const table = document.createElement('table');
    table.innerHTML = `
        <thead>
            <tr>
                <th>Name</th>
                <th>Position</th>
                <th>Team</th>
                <th>Avg Value</th>
                <th>Projected Value</th>
            </tr>
        </thead>
        <tbody>
            ${result.free_agents.map(player => `
                <tr>
                    <td>${player.name}</td>
                    <td>${player.position || '-'}</td>
                    <td>${player.mlb_team || player.team || '-'}</td>
                    <td>${formatCurrency(player.avg_salary || player.avg_value || 0)}</td>
                    <td>${formatCurrency(player.projected_value || player.avg_salary || player.avg_value || 0)}</td>
                </tr>
            `).join('')}
        </tbody>
    `;

    container.innerHTML = '';
    container.appendChild(table);
}

// =============================================================================
// Utilities
// =============================================================================
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Make removePlayerFromTrade available globally
window.removePlayerFromTrade = removePlayerFromTrade;

// =============================================================================
// Initialize App
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    initTabNavigation();
    initLeagueTeamControls();
    initRosterOptimizer();
    initLineupOptimizer();
    initTradeAnalyzer();
    initPlayerValue();
    initFreeAgents();

    // Hide loading overlay initially
    hideLoading();

    console.log('Ottoneu Roster Tool initialized');
});
