const API_BASE = '/v1';
const REFRESH_INTERVAL = 10000;
let autoRefreshTimer;

async function fetchJSON(endpoint) {
	try {
		const response = await fetch(API_BASE + endpoint);
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		return await response.json();
	} catch (error) {
		console.error(`Error fetching ${endpoint}:`, error);
		showError(`Failed to fetch ${endpoint}: ${error.message}`);
		return null;
	}
}

function showError(message) {
	const container = document.getElementById('error-container');
	container.innerHTML = `<div class="error">⚠️ ${message}</div>`;
	setTimeout(() => {
		container.innerHTML = '';
	}, 5000);
}

function formatNumber(num) {
	if (num === null || num === undefined) return '—';
	if (typeof num === 'number' && num > 1000) {
		return (num / 1000).toFixed(1) + 'k';
	}
	return num.toString();
}

function formatTime(seconds) {
	if (!seconds) return '—';
	if (seconds < 1) return (seconds * 1000).toFixed(0) + 'ms';
	return seconds.toFixed(2) + 's';
}

function formatPercent(value) {
	if (value === null || value === undefined) return '—';
	return value.toFixed(1) + '%';
}

function getStatusClass(status) {
	switch (status) {
		case 'healthy': return 'status-healthy';
		case 'degraded': return 'status-degraded';
		case 'unhealthy': return 'status-unhealthy';
		case 'down': return 'status-down';
		default: return '';
	}
}

function getHealthBarClass(score) {
	if (score >= 80) return 'good';
	if (score >= 50) return 'warning';
	return 'danger';
}

function updateTimestamp() {
	const now = new Date();
	document.getElementById('last-updated').textContent = now.toLocaleTimeString();
}

async function updateHealth() {
	const health = await fetchJSON('/health');
	if (!health) return;

	updateTimestamp();

	const statusEl = document.getElementById('system-status');
	statusEl.textContent = health.status?.toUpperCase() || '—';
	
	const badgeEl = document.getElementById('system-status-badge');
	badgeEl.innerHTML = `<span class="status-badge ${getStatusClass(health.status)}">● ${health.status || 'unknown'}</span>`;

	const stats = health.global_stats || {};
	document.getElementById('total-requests').textContent = formatNumber(stats.total_requests);
	document.getElementById('error-rate').textContent = formatPercent(stats.error_rate_percent);
	document.getElementById('error-count').textContent = `${stats.total_errors || 0} errors`;
	
	document.getElementById('avg-response').textContent = formatTime(stats.avg_response_time_ms ? stats.avg_response_time_ms / 1000 : null);
	document.getElementById('p95-response').textContent = `p95: ${formatTime(stats.p95_response_time_ms ? stats.p95_response_time_ms / 1000 : null)}`;
	
	document.getElementById('avg-ttft').textContent = formatTime(stats.avg_ttft_ms ? stats.avg_ttft_ms / 1000 : null);
	document.getElementById('p95-ttft').textContent = `p95: ${formatTime(stats.p95_ttft_ms ? stats.p95_ttft_ms / 1000 : null)}`;
	
	document.getElementById('total-tokens').textContent = formatNumber(stats.total_tokens);
	const promptTokens = stats.total_prompt_tokens || 0;
	const completionTokens = stats.total_completion_tokens || 0;
	document.getElementById('token-breakdown').textContent = `${formatNumber(promptTokens)} input / ${formatNumber(completionTokens)} output`;

	const providerSummary = health.provider_summary || {};
	document.getElementById('total-providers').textContent = providerSummary.total_providers || 0;
	document.getElementById('enabled-providers').textContent = providerSummary.enabled_provider_instances || 0;
	document.getElementById('disabled-providers').textContent = providerSummary.disabled_provider_instances || 0;
	document.getElementById('avg-health').textContent = (providerSummary.avg_provider_health_score || 0).toFixed(1);

	document.getElementById('total-models').textContent = formatNumber(stats.total_models || 0);
	document.getElementById('avg-providers-per-model').textContent = (providerSummary.avg_providers_per_model || 0).toFixed(1);
}

async function updateModels() {
	const models = await fetchJSON('/models');
	if (!models) return;

	const container = document.getElementById('models-container');
	const modelData = models.data || [];

	if (modelData.length === 0) {
		container.innerHTML = '<div class="no-data">No models available</div>';
		return;
	}

	let html = '<div class="table-wrapper"><table><thead><tr><th>Model ID</th><th>Owner</th><th>Created</th></tr></thead><tbody>';
	
	modelData.forEach(model => {
		html += `<tr>
			<td class="model-name">${escapeHtml(model.id)}</td>
			<td>${escapeHtml(model.owned_by)}</td>
			<td>${new Date(model.created * 1000).toLocaleDateString()}</td>
		</tr>`;
	});

	html += '</tbody></table></div>';
	container.innerHTML = html;
}

async function updateProviderStats() {
	const stats = await fetchJSON('/providers/stats');
	if (!stats) return;

	const container = document.getElementById('providers-container');
	const modelKeys = Object.keys(stats);

	if (modelKeys.length === 0) {
		container.innerHTML = '<div class="no-data">No provider statistics available</div>';
		return;
	}

	let html = '';

	modelKeys.forEach(modelId => {
		const modelStats = stats[modelId];
		const providers = modelStats.providers || [];

		html += `<h3 style="font-size: 16px; margin: 20px 0 10px 0; color: #cbd5e1;">Model: ${escapeHtml(modelId)}</h3>`;
		html += '<div class="table-wrapper"><table><thead><tr><th>Provider</th><th>Priority</th><th>Enabled</th><th>Health Score</th><th>Tokens/Sec</th><th>Avg TTFT</th><th>P95 TTFT</th><th>Models</th></tr></thead><tbody>';

		providers.forEach(provider => {
			const healthScore = provider.health_score || 0;
			const healthClass = getHealthBarClass(healthScore);
			const tokensPerSec = (provider.tokens_per_second || 0).toFixed(1);
			const avgTTFT = formatTime(provider.average_ttft);
			const p95TTFT = formatTime(provider.p95_ttft);

			html += `<tr>
				<td class="provider-name">${escapeHtml(provider.provider || '—')}</td>
				<td>${provider.priority || 0}</td>
				<td><span class="enabled-badge enabled-${provider.enabled}">
					${provider.enabled ? '✓ Yes' : '✗ No'}
				</span></td>
				<td>
					<div class="metric-bar">
						<div class="bar-bg"><div class="bar-fill ${healthClass}" style="width: ${healthScore}%"></div></div>
						<span class="bar-value">${healthScore.toFixed(0)}</span>
					</div>
				</td>
				<td>${tokensPerSec}</td>
				<td>${avgTTFT}</td>
				<td>${p95TTFT}</td>
				<td>${(provider.model_ids || []).join(', ') || '—'}</td>
			</tr>`;
		});

		html += '</tbody></table></div>';
	});

	container.innerHTML = html;
}

function escapeHtml(text) {
	const div = document.createElement('div');
	div.textContent = text;
	return div.innerHTML;
}

async function refreshData() {
	await Promise.all([updateHealth(), updateModels(), updateProviderStats()]);
}

function startAutoRefresh() {
	autoRefreshTimer = setInterval(refreshData, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
	clearInterval(autoRefreshTimer);
}

document.addEventListener('DOMContentLoaded', () => {
	refreshData();
	startAutoRefresh();
});

document.addEventListener('visibilitychange', () => {
	if (document.hidden) {
		stopAutoRefresh();
	} else {
		refreshData();
		startAutoRefresh();
	}
});