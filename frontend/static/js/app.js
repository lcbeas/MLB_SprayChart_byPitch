/**
 * Ottoneu Roster Tool - Main Application JavaScript
 */

// API client
const api = {
    baseUrl: '/api',

    async get(endpoint) {
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    // Player endpoints
    async getPlayers() {
        return this.get('/players/');
    },

    async getPlayer(playerId) {
        return this.get(`/players/${playerId}`);
    },

    async searchPlayers(query) {
        return this.get(`/players/search?q=${encodeURIComponent(query)}`);
    },

    async getPlayerProjections(playerId) {
        return this.get(`/players/${playerId}/projections`);
    },

    async getPlayerStatcast(playerId) {
        return this.get(`/players/${playerId}/statcast`);
    },

    // League endpoints
    async getRoster() {
        return this.get('/league/roster');
    },

    async getFreeAgents(position = null) {
        const params = position ? `?position=${position}` : '';
        return this.get(`/league/free-agents${params}`);
    },

    async getLeagueValues() {
        return this.get('/league/values');
    }
};

// Navigation
function initNavigation() {
    const navLinks = document.querySelectorAll('.nav-links a');
    const sections = document.querySelectorAll('.section');

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetSection = link.dataset.section;

            // Update active states
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            sections.forEach(s => s.classList.remove('active'));
            document.getElementById(targetSection).classList.add('active');
        });
    });
}

// Player Search
function initPlayerSearch() {
    const searchInput = document.getElementById('player-search');
    const searchBtn = document.getElementById('search-btn');
    const resultsContainer = document.getElementById('player-results');

    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        resultsContainer.innerHTML = '<p>Searching...</p>';

        try {
            const data = await api.searchPlayers(query);
            renderPlayerResults(data.results, resultsContainer);
        } catch (error) {
            resultsContainer.innerHTML = '<p>Error searching players. Please try again.</p>';
        }
    }

    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });
}

// Render player results table
function renderPlayerResults(players, container) {
    if (!players || players.length === 0) {
        container.innerHTML = '<p>No players found.</p>';
        return;
    }

    const table = document.createElement('table');
    table.innerHTML = `
        <thead>
            <tr>
                <th>Name</th>
                <th>Team</th>
                <th>Position</th>
                <th>Salary</th>
                <th>Proj. Value</th>
                <th>Surplus</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            ${players.map(player => `
                <tr>
                    <td>${player.name}</td>
                    <td>${player.team || '-'}</td>
                    <td>${player.position || '-'}</td>
                    <td>${player.salary ? '$' + player.salary : 'FA'}</td>
                    <td>${player.projected_value ? '$' + player.projected_value.toFixed(1) : '-'}</td>
                    <td class="${player.surplus_value > 0 ? 'value-positive' : 'value-negative'}">
                        ${player.surplus_value ? '$' + player.surplus_value.toFixed(1) : '-'}
                    </td>
                    <td>
                        <button onclick="viewPlayer(${player.mlbam_id})">View</button>
                    </td>
                </tr>
            `).join('')}
        </tbody>
    `;
    container.innerHTML = '';
    container.appendChild(table);
}

// View player details
async function viewPlayer(playerId) {
    try {
        const player = await api.getPlayer(playerId);
        console.log('Player details:', player);
        // TODO: Show player modal/detail view
        alert(`Player details for ID ${playerId} - implementation pending`);
    } catch (error) {
        console.error('Error fetching player:', error);
    }
}

// Load dashboard data
async function loadDashboard() {
    // TODO: Implement dashboard data loading
    console.log('Loading dashboard...');
}

// Initialize free agents section
function initFreeAgents() {
    const positionFilter = document.getElementById('fa-position-filter');
    const sortSelect = document.getElementById('fa-sort');
    const resultsContainer = document.getElementById('fa-results');

    async function loadFreeAgents() {
        const position = positionFilter.value;
        resultsContainer.innerHTML = '<p>Loading free agents...</p>';

        try {
            const data = await api.getFreeAgents(position);
            renderPlayerResults(data.free_agents, resultsContainer);
        } catch (error) {
            resultsContainer.innerHTML = '<p>Error loading free agents.</p>';
        }
    }

    positionFilter.addEventListener('change', loadFreeAgents);
    sortSelect.addEventListener('change', loadFreeAgents);
}

// Initialize roster section
async function loadRoster() {
    const container = document.getElementById('roster-table');

    try {
        const data = await api.getRoster();
        renderPlayerResults(data.roster, container);
    } catch (error) {
        container.innerHTML = '<p>Error loading roster. Make sure your league is configured.</p>';
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initPlayerSearch();
    initFreeAgents();
    loadDashboard();
});
