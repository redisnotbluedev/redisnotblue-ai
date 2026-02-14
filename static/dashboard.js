const API_BASE = '/v1';
const REFRESH_INTERVAL = 10000;
let autoRefreshTimer;
let autoRefreshEnabled = true;
let currentView = 'overview';
let performanceChart = null;
let efficiencyChart = null;
let historicalData = {
	performance: [],
	efficiency: [],
	timestamps: []
};

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

function showAlert(type, message, duration = 5000) {
	const container = document.getElementById('alerts-container');
	const alertId = Date.now();
	const alertHtml = `<div class="alert alert-${type}" id="alert-${alertId}">
		<span>${message}</span>
		<button onclick="dismissAlert(${alertId})" style="margin-left: auto; background: none; border: none; color: inherit; cursor: pointer;">✕</button>
	</div>`;
	container.insertAdjacentHTML('beforeend', alertHtml);

	if (duration > 0) {
		setTimeout(() => dismissAlert(alertId), duration);
	}
}

function dismissAlert(alertId) {
	const alert = document.getElementById(`alert-${alertId}`);
	if (alert) {
		alert.remove();
	}
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

function formatUptime(seconds) {
	if (!seconds) return '—';
	const days = Math.floor(seconds / 86400);
	const hours = Math.floor((seconds % 86400) / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);

	if (days > 0) return `${days}d ${hours}h ${minutes}m`;
	if (hours > 0) return `${hours}h ${minutes}m`;
	return `${minutes}m`;
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

function getTrendClass(trend) {
	switch (trend) {
		case 'improving': return 'trend-improving';
		case 'degrading': return 'trend-degrading';
		default: return 'trend-stable';
	}
}

function updateTimestamp() {
	const now = new Date();
	document.getElementById('last-updated').textContent = now.toLocaleTimeString();
}

function switchView(viewName) {
	// Update view buttons
	document.querySelectorAll('.view-toggle').forEach(btn => {
		btn.classList.remove('active');
	});
	document.querySelector(`[onclick="switchView('${viewName}')"]`).classList.add('active');

	// Update view containers
	document.querySelectorAll('.view-container').forEach(container => {
		container.classList.remove('active');
	});
	document.getElementById(`${viewName}-view`).classList.add('active');

	currentView = viewName;
	refreshData();
}

function toggleAutoRefresh() {
	autoRefreshEnabled = !autoRefreshEnabled;
	const icon = document.getElementById('auto-refresh-icon');
	const button = document.querySelector('[onclick="toggleAutoRefresh()"]');

	if (autoRefreshEnabled) {
		icon.textContent = '⏸️';
		button.classList.remove('active');
		startAutoRefresh();
		showAlert('info', 'Auto-refresh enabled');
	} else {
		icon.textContent = '▶️';
		button.classList.add('active');
		stopAutoRefresh();
		showAlert('info', 'Auto-refresh paused');
	}
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

	document.getElementById('tps').textContent = (stats.tokens_per_second || 0).toFixed(1);

	document.getElementById('total-tokens').textContent = formatNumber(stats.total_tokens);
	const promptTokens = stats.total_prompt_tokens || 0;
	const completionTokens = stats.total_completion_tokens || 0;
	document.getElementById('token-breakdown').textContent = `${formatNumber(promptTokens)} input / ${formatNumber(completionTokens)} output`;

	document.getElementById('total-credits').textContent = formatNumber(stats.total_credits_used);
	const costEfficiency = stats.advanced_analytics?.cost_efficiency || {};
	document.getElementById('cost-efficiency').textContent = costEfficiency.efficiency_trend || '—';

	document.getElementById('uptime').textContent = formatUptime(stats.uptime_seconds);
	document.getElementById('uptime-seconds').textContent = `${formatNumber(stats.uptime_seconds)} seconds`;

	const providerSummary = health.provider_summary || {};
	const totalProviders = providerSummary.total_providers || 0;
	const enabledProviders = providerSummary.enabled_provider_instances || 0;

	document.getElementById('enabled-providers').textContent = enabledProviders;
	document.getElementById('total-providers-text').textContent = `of ${totalProviders} total`;
	document.getElementById('avg-health').textContent = (providerSummary.avg_provider_health_score || 0).toFixed(1);
	document.getElementById('avg-providers-per-model-text').textContent = `${(providerSummary.avg_providers_per_model || 0).toFixed(1)} models`;

	const loadPrediction = stats.advanced_analytics?.predictions?.load_forecast || {};
	document.getElementById('load-prediction').textContent = `${(loadPrediction.requests_per_minute || 0).toFixed(0)} req/min`;
	document.getElementById('prediction-confidence').textContent = `${formatPercent((loadPrediction.confidence || 0) * 100)} confidence`;

	// Check for alerts
	checkForAlerts(health);
}

function checkForAlerts(health) {
	const stats = health.global_stats || {};
	const analytics = stats.advanced_analytics || {};

	// High error rate alert
	if (stats.error_rate_percent > 10) {
		showAlert('error', `High error rate: ${stats.error_rate_percent.toFixed(1)}%`, 10000);
	}

	// Degraded system status
	if (health.status === 'degraded' || health.status === 'unhealthy') {
		showAlert('warning', `System status: ${health.status}`, 15000);
	}

	// Anomalies detected
	const anomalyCount = analytics.anomaly_detection?.anomalies_count || 0;
	if (anomalyCount > 0) {
		showAlert('warning', `${anomalyCount} performance anomalies detected`, 10000);
	}

	// Rate limit predictions
	const predictions = analytics.predictions || {};
	if (predictions.seconds_until_limit && predictions.seconds_until_limit < 300) {
		showAlert('warning', `Rate limit approaching in ${Math.round(predictions.seconds_until_limit / 60)} minutes`, 15000);
	}
}

async function updateAnalytics() {
	const analytics = await fetchJSON('/analytics');
	if (!analytics) return;

	// Update analytics metrics
	const globalStats = analytics.global_metrics || {};
	document.getElementById('anomaly-count').textContent = analytics.anomaly_detection?.anomalies_count || 0;

	const costEfficiency = analytics.cost_analysis || {};
	document.getElementById('cost-per-token').textContent = formatNumber(costEfficiency.cost_per_token);
	document.getElementById('cost-trend').textContent = costEfficiency.efficiency_trend || '—';

	const performanceTrends = analytics.performance_trends || {};
	const rtTrendEl = document.getElementById('rt-trend');
	rtTrendEl.textContent = performanceTrends.response_time_trend || '—';
	rtTrendEl.parentElement.className = `metric-card ${getTrendClass(performanceTrends.response_time_trend)}`;

	document.getElementById('rt-trend-desc').textContent = getTrendDescription(performanceTrends.response_time_trend);

	// Calculate average efficiency
	const rateLimiters = analytics.rate_limiter_analytics || {};
	const efficiencies = Object.values(rateLimiters).map(rl => rl.efficiency_score).filter(e => e > 0);
	const avgEfficiency = efficiencies.length > 0 ? efficiencies.reduce((a, b) => a + b, 0) / efficiencies.length : 0;
	document.getElementById('avg-efficiency').textContent = formatPercent(avgEfficiency * 100);

	// Update charts
	updatePerformanceChart(analytics);
	updateEfficiencyChart(analytics);

	// Update anomaly display
	updateAnomalyDisplay(analytics);

	// Update rate limiter display
	updateRateLimiterDisplay(analytics);
}

function getTrendDescription(trend) {
	switch (trend) {
		case 'improving': return 'Response times decreasing';
		case 'degrading': return 'Response times increasing';
		default: return 'Response times stable';
	}
}

function updatePerformanceChart(analytics) {
	const ctx = document.getElementById('performance-chart');
	if (!ctx) return;

	const globalStats = analytics.global_metrics || {};
	const timestamp = analytics.timestamp;

	// Add current data point
	historicalData.timestamps.push(timestamp);
	historicalData.performance.push({
		responseTime: globalStats.avg_response_time || 0,
		ttft: globalStats.avg_ttft || 0,
		throughput: globalStats.tokens_per_second || 0
	});

	// Keep last 20 data points
	if (historicalData.timestamps.length > 20) {
		historicalData.timestamps.shift();
		historicalData.performance.shift();
	}

	const labels = historicalData.timestamps.map(ts =>
		luxon.DateTime.fromSeconds(ts).toFormat('HH:mm:ss')
	);

	if (performanceChart) {
		performanceChart.destroy();
	}

	performanceChart = new Chart(ctx, {
		type: 'line',
		data: {
			labels: labels,
			datasets: [{
				label: 'Avg Response Time (s)',
				data: historicalData.performance.map(p => p.responseTime),
				borderColor: '#3b82f6',
				backgroundColor: 'rgba(59, 130, 246, 0.1)',
				tension: 0.4,
				yAxisID: 'y'
			}, {
				label: 'Avg TTFT (s)',
				data: historicalData.performance.map(p => p.ttft),
				borderColor: '#22c55e',
				backgroundColor: 'rgba(34, 197, 94, 0.1)',
				tension: 0.4,
				yAxisID: 'y'
			}, {
				label: 'Throughput (tokens/sec)',
				data: historicalData.performance.map(p => p.throughput),
				borderColor: '#eab308',
				backgroundColor: 'rgba(234, 179, 8, 0.1)',
				tension: 0.4,
				yAxisID: 'y1'
			}]
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			interaction: {
				mode: 'index',
				intersect: false,
			},
			scales: {
				y: {
					type: 'linear',
					display: true,
					position: 'left',
					title: {
						display: true,
						text: 'Time (seconds)'
					}
				},
				y1: {
					type: 'linear',
					display: true,
					position: 'right',
					title: {
						display: true,
						text: 'Throughput (tokens/sec)'
					},
					grid: {
						drawOnChartArea: false,
					}
				}
			},
			plugins: {
				legend: {
					display: true,
					position: 'top'
				}
			}
		}
	});
}

function updateEfficiencyChart(analytics) {
	const ctx = document.getElementById('efficiency-chart');
	if (!ctx) return;

	const providerAnalytics = analytics.provider_analytics || {};
	const providers = Object.entries(providerAnalytics);

	const labels = providers.map(([key, data]) => `${data.model}:${data.provider}`);
	const efficiencies = providers.map(([key, data]) => data.health_score || 0);

	if (efficiencyChart) {
		efficiencyChart.destroy();
	}

	efficiencyChart = new Chart(ctx, {
		type: 'bar',
		data: {
			labels: labels,
			datasets: [{
				label: 'Provider Health Score',
				data: efficiencies,
				backgroundColor: efficiencies.map(score => {
					if (score >= 80) return 'rgba(34, 197, 94, 0.8)';
					if (score >= 50) return 'rgba(234, 179, 8, 0.8)';
					return 'rgba(239, 68, 68, 0.8)';
				}),
				borderColor: efficiencies.map(score => {
					if (score >= 80) return 'rgba(34, 197, 94, 1)';
					if (score >= 50) return 'rgba(234, 179, 8, 1)';
					return 'rgba(239, 68, 68, 1)';
				}),
				borderWidth: 1
			}]
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			scales: {
				y: {
					beginAtZero: true,
					max: 100,
					title: {
						display: true,
						text: 'Health Score'
					}
				}
			},
			plugins: {
				legend: {
					display: false
				}
			}
		}
	});
}

function updateAnomalyDisplay(analytics) {
	const container = document.getElementById('anomaly-container');
	const anomalies = analytics.anomaly_detection?.recent_anomalies || [];

	if (anomalies.length === 0) {
		container.innerHTML = '<div class="no-data">No recent anomalies detected</div>';
		return;
	}

	let html = '<div class="anomaly-list">';
	anomalies.forEach(anomaly => {
		const timestamp = luxon.DateTime.fromSeconds(anomaly[0]).toFormat('HH:mm:ss');
		const responseTime = formatTime(anomaly[1]);
		const score = anomaly[2].toFixed(2);

		html += `<div class="anomaly-item">
			<div class="anomaly-info">
				<div class="anomaly-timestamp">${timestamp}</div>
				<div class="anomaly-details">Response time: ${responseTime}</div>
			</div>
			<div class="anomaly-score">Score: ${score}</div>
		</div>`;
	});
	html += '</div>';

	container.innerHTML = html;
}

function updateRateLimiterDisplay(analytics) {
	const container = document.getElementById('rate-limiter-container');
	const rateLimiters = analytics.rate_limiter_analytics || {};
	const entries = Object.entries(rateLimiters);

	if (entries.length === 0) {
		container.innerHTML = '<div class="no-data">No rate limiter data available</div>';
		return;
	}

	let html = '';
	entries.forEach(([key, data]) => {
		const statusClass = data.rate_limited ? 'enabled-false' : 'enabled-true';
		const statusText = data.rate_limited ? 'Limited' : 'OK';
		const efficiency = formatPercent((data.efficiency_score || 0) * 100);
		const timeUntilLimit = data.seconds_until_limit || 0;
		const timeText = timeUntilLimit > 0 ? `${Math.round(timeUntilLimit / 60)}min` : '—';

		html += `<div class="rate-limiter-item">
			<div class="rate-limiter-key">${key}</div>
			<div class="rate-limiter-status">
				<span class="enabled-badge ${statusClass}">${statusText}</span>
			</div>
			<div class="rate-limiter-metrics">
				<div class="rate-limiter-metric">Efficiency: <span class="rate-limiter-metric-value">${efficiency}</span></div>
				<div class="rate-limiter-metric">Until limit: <span class="rate-limiter-metric-value">${timeText}</span></div>
			</div>
		</div>`;
	});

	container.innerHTML = html;
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
		const modelStatus = getModelStatus(model.id);
		const statusClass = modelStatus === 'healthy' ? '' : modelStatus === 'degraded' ? 'degraded' : 'unhealthy';

		html += `<a href="#provider-section-${escapeHtml(model.id)}" class="model-card ${statusClass}">
			<div class="model-card-name">${escapeHtml(model.id)}</div>
			<div class="model-card-count">${escapeHtml(model.owned_by)}</div>
			<div class="model-status"></div>
		</a>`;
	});
	html += '</div>';

	container.innerHTML = html;
}

function getModelStatus(modelId) {
	// This would need to be implemented based on provider health
	// For now, return a placeholder
	return 'healthy';
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
		const avgHealth = providers.length > 0 ?
			providers.reduce((sum, p) => sum + (p.health_score || 0), 0) / providers.length : 0;

		html += `<div id="provider-section-${escapeHtml(modelId)}" class="provider-table-section">
			<div class="table-container">
				<div class="table-title">
					📌 ${escapeHtml(modelId)}
					<span class="model-health">Avg Health: ${avgHealth.toFixed(1)}</span>
				</div>
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

async function updateRoutingConfig() {
	const models = await fetchJSON('/models');
	if (!models) return;

	const container = document.getElementById('routing-config-container');
	const modelData = models.data || [];

	if (modelData.length === 0) {
		container.innerHTML = '<div class="no-data">No models available for routing configuration</div>';
		return;
	}

	let html = '<div class="routing-config">';

	for (const model of modelData) {
		const routingConfig = await fetchJSON(`/models/${model.id}/routing`);
		const config = routingConfig || {
			routing_algorithm: 'health_priority',
			load_balance_weights: {},
			cost_optimization_enabled: false,
			predictive_routing_enabled: false
		};

		html += `<div class="routing-model">
			<h3>${escapeHtml(model.id)}</h3>

			<div class="routing-setting">
				<label for="algorithm-${model.id}">Routing Algorithm</label>
				<select id="algorithm-${model.id}" onchange="updateRoutingSetting('${model.id}', 'routing_algorithm', this.value)">
					<option value="health_priority" ${config.routing_algorithm === 'health_priority' ? 'selected' : ''}>Health Priority</option>
					<option value="round_robin" ${config.routing_algorithm === 'round_robin' ? 'selected' : ''}>Round Robin</option>
					<option value="least_loaded" ${config.routing_algorithm === 'least_loaded' ? 'selected' : ''}>Least Loaded</option>
					<option value="weighted_random" ${config.routing_algorithm === 'weighted_random' ? 'selected' : ''}>Weighted Random</option>
					<option value="cost_optimized" ${config.routing_algorithm === 'cost_optimized' ? 'selected' : ''}>Cost Optimized</option>
					<option value="predictive" ${config.routing_algorithm === 'predictive' ? 'selected' : ''}>Predictive</option>
				</select>
			</div>

			<div class="routing-setting">
				<label for="cost-opt-${model.id}">Cost Optimization</label>
				<select id="cost-opt-${model.id}" onchange="updateRoutingSetting('${model.id}', 'cost_optimization_enabled', this.value === 'true')">
					<option value="false" ${!config.cost_optimization_enabled ? 'selected' : ''}>Disabled</option>
					<option value="true" ${config.cost_optimization_enabled ? 'selected' : ''}>Enabled</option>
				</select>
			</div>

			<div class="routing-setting">
				<label for="predictive-${model.id}">Predictive Routing</label>
				<select id="predictive-${model.id}" onchange="updateRoutingSetting('${model.id}', 'predictive_routing_enabled', this.value === 'true')">
					<option value="false" ${!config.predictive_routing_enabled ? 'selected' : ''}>Disabled</option>
					<option value="true" ${config.predictive_routing_enabled ? 'selected' : ''}>Enabled</option>
				</select>
			</div>

			<div class="routing-actions">
				<button onclick="saveRoutingConfig('${model.id}')">Save Changes</button>
				<button class="secondary" onclick="resetRoutingConfig('${model.id}')">Reset to Default</button>
			</div>
		</div>`;
	}

	html += '</div>';
	container.innerHTML = html;
}

async function updateRoutingSetting(modelId, setting, value) {
	// Store the change locally for batch saving
	if (!window.routingChanges) window.routingChanges = {};
	if (!window.routingChanges[modelId]) window.routingChanges[modelId] = {};
	window.routingChanges[modelId][setting] = value;
}

async function saveRoutingConfig(modelId) {
	const changes = window.routingChanges?.[modelId];
	if (!changes) {
		showAlert('info', 'No changes to save');
		return;
	}

	try {
		const response = await fetch(`${API_BASE}/models/${modelId}/routing`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(changes)
		});

		if (response.ok) {
			showAlert('success', `Routing configuration saved for ${modelId}`);
			delete window.routingChanges[modelId];
		} else {
			throw new Error(`HTTP ${response.status}`);
		}
	} catch (error) {
		showAlert('error', `Failed to save routing config: ${error.message}`);
	}
}

async function resetRoutingConfig(modelId) {
	if (!confirm(`Reset routing configuration for ${modelId} to defaults?`)) return;

	try {
		const response = await fetch(`${API_BASE}/models/${modelId}/routing`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				routing_algorithm: 'health_priority',
				load_balance_weights: {},
				cost_optimization_enabled: false,
				predictive_routing_enabled: false
			})
		});

		if (response.ok) {
			showAlert('success', `Routing configuration reset for ${modelId}`);
			updateRoutingConfig();
		} else {
			throw new Error(`HTTP ${response.status}`);
		}
	} catch (error) {
		showAlert('error', `Failed to reset routing config: ${error.message}`);
	}
}

function escapeHtml(text) {
	const div = document.createElement('div');
	div.textContent = text;
	return div.innerHTML;
}

async function refreshData() {
	try {
		if (currentView === 'overview') {
			await Promise.all([updateHealth(), updateModels(), updateProviderStats()]);
		} else if (currentView === 'analytics') {
			await updateAnalytics();
		} else if (currentView === 'routing') {
			await updateRoutingConfig();
		}
	} catch (error) {
		console.error('Error refreshing data:', error);
	}
}

function startAutoRefresh() {
	if (autoRefreshEnabled) {
		autoRefreshTimer = setInterval(refreshData, REFRESH_INTERVAL);
	}
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
	} else if (autoRefreshEnabled) {
		refreshData();
		startAutoRefresh();
	}
});
