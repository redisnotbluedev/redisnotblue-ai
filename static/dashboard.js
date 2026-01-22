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
	const totalProviders = providerSummary.total_providers || 0;
	const enabledProviders = providerSummary.enabled_provider_instances || 0;
	const totalModels = providerSummary.total_providers || 0;
	
	document.getElementById('enabled-providers').textContent = enabledProviders;
	document.getElementById('total-providers-text').textContent = `of ${totalProviders} total`;
	document.getElementById('avg-health').textContent = (providerSummary.avg_provider_health_score || 0).toFixed(1);
	document.getElementById('avg-providers-per-model-text').textContent = `${(providerSummary.avg_providers_per_model || 0).toFixed(1)} models`;
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

	let html = '<div class="models-grid">';
	modelData.forEach(model => {
		html += `<div class="model-card">
			<div class="model-card-name">${escapeHtml(model.id)}</div>
			<div class="model-card-count">${escapeHtml(model.owned_by)}</div>
		</div>`;
	});
	html += '</div>';

	container.innerHTML = html;
}

async function updateProviderStats() {
	const stats = await fetchJSON('/providers/stats');
	if (!stats) return;

	const container = document.getElementById('providers-container');
	const modelKeys = Object.keys(stats).sort();

	if (modelKeys.length === 0) {
		container.innerHTML = '<div class="no-data">No provider statistics available</div>';
		return;
	}

	let html = '';

	modelKeys.forEach(modelId => {
		const modelStats = stats[modelId];
		const providers = modelStats.providers || [];

		html += `<div class="provider-table-section">
			<div class="table-container">
				<div class="table-title">📌 ${escapeHtml(modelId)}</div>
				<table>
					<thead>
						<tr>
							<th style="width: 20%;">Provider</th>
							<th style="width: 10%;">Priority</th>
							<th style="width: 10%;">Enabled</th>
							<th style="width: 20%;">Health</th>
							<th style="width: 12%;">Tok/Sec</th>
							<th style="width: 14%;">Avg TTFT</th>
							<th style="width: 14%;">P95 TTFT</th>
						</tr>
					</thead>
					<tbody>`;

		providers.forEach(provider => {
			const healthScore = provider.health_score || 0;
			const hasData = provider.avg_response_time > 0;
			const healthDisplay = hasData ? healthScore.toFixed(0) : '—';
			const healthClass = hasData ? getHealthBarClass(healthScore) : '';
			const tokensPerSec = (provider.tokens_per_second || 0).toFixed(1);
			const avgTTFT = formatTime(provider.average_ttft);
			const p95TTFT = formatTime(provider.p95_ttft);

			html += `<tr>
				<td class="provider-name">${escapeHtml(provider.provider || '—')}</td>
				<td style="text-align: center;">${provider.priority || 0}</td>
				<td style="text-align: center;"><span class="enabled-badge enabled-${provider.enabled}">
					${provider.enabled ? '✓' : '✗'}
				</span></td>
				<td>`;
			
			if (hasData) {
				html += `<div class="metric-bar">
					<div class="bar-bg"><div class="bar-fill ${healthClass}" style="width: ${healthScore}%"></div></div>
					<span class="bar-value">${healthDisplay}</span>
				</div>`;
			} else {
				html += `<span style="color: #64748b;">—</span>`;
			}

			html += `</td>
				<td style="text-align: right;">${tokensPerSec}</td>
				<td style="text-align: right;">${avgTTFT}</td>
				<td style="text-align: right;">${p95TTFT}</td>
			</tr>`;
		});

		html += `</tbody></table></div></div>`;
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