// Check login status on page load
window.addEventListener('DOMContentLoaded', () => {
    checkLoginStatus();
    initNavigation();
});

// Check if user is logged in
async function checkLoginStatus() {
    try {
        const response = await fetch('/auth/me', {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            console.log('Logged in as:', data.username);
        } else {
            // Don't redirect here - the /admin route already handles authentication
            // If we're on this page, it means the backend already validated the session
            console.log('Session check returned non-OK, but continuing (backend already validated)');
        }
    } catch (error) {
        // Don't redirect on error - backend already handled authentication
        console.log('Error checking login status, but continuing:', error);
    }
    
    // Always load dashboard - if session is truly invalid, subsequent API calls will fail
    // and apiRequest() will handle the redirect to /login
    loadDashboard();
}

// Initialize navigation
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item:not(.disabled)');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.getAttribute('data-page');
            if (page) {
                switchPage(page);
            }
        });
    });
}

// Switch page
function switchPage(pageName) {
    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-page="${pageName}"]`)?.classList.add('active');
    
    // Update page visibility
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    document.getElementById(`page-${pageName}`)?.classList.add('active');
    
    // Load page data
    switch(pageName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'models':
            loadModels();
            break;
        case 'accounts':
            loadAccounts();
            break;
        case 'tokens':
            loadTokens();
            break;
        case 'logs':
            loadLogs();
            break;
    }
}

// Logout
async function logout() {
    try {
        await fetch('/auth/logout', { 
            method: 'POST',
            credentials: 'include'
        });
        window.location.href = '/login';
    } catch (error) {
        console.error('Logout failed:', error);
    }
}

// API helper with retry logic for Docker environments
async function apiRequest(url, options = {}, retries = 1) {
    try {
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };
        
        const response = await fetch(url, {
            ...options,
            headers,
            credentials: 'include'
        });
        
        if (!response.ok) {
            if (response.status === 401) {
                // Retry once for 401 errors (cookie might not be ready)
                if (retries > 0) {
                    await new Promise(resolve => setTimeout(resolve, 200));
                    return apiRequest(url, options, retries - 1);
                }
                window.location.href = '/login';
                throw new Error('Session expired. Please login again.');
            }
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        if (response.status === 204) {
            return null;
        }
        
        return await response.json();
    } catch (error) {
        // Retry on network errors (except for explicit redirects)
        if (retries > 0 && !error.message.includes('Session expired')) {
            await new Promise(resolve => setTimeout(resolve, 200));
            return apiRequest(url, options, retries - 1);
        }
        throw error;
    }
}

// Notification
function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type} show`;
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

// ==================== Dashboard ====================
async function loadDashboard() {
    try {
        const [accounts, tokens, users] = await Promise.all([
            apiRequest('/admin/accounts'),
            apiRequest('/admin/api-keys'),
            apiRequest('/admin/users')
        ]);
        
        const totalUsage = accounts.reduce((sum, acc) => sum + (acc.usage || 0), 0);
        
        document.getElementById('stat-accounts').textContent = accounts.length;
        document.getElementById('stat-tokens').textContent = tokens.length;
        document.getElementById('stat-usage').textContent = totalUsage.toFixed(2);
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }
}

// ==================== Accounts ====================
async function loadAccounts() {
    const container = document.getElementById('accountsList');
    container.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const accounts = await apiRequest('/admin/accounts');
        
        if (accounts.length === 0) {
            container.innerHTML = '<div class="loading">暂无账号</div>';
            return;
        }
        
        container.innerHTML = accounts.map(account => {
            const usagePercent = account.limit > 0 ? (account.usage / account.limit * 100) : 0;
            const usageText = account.limit > 0 ? `${account.usage.toFixed(2)} / ${account.limit}` : `${account.usage.toFixed(2)} (无限制)`;
            
            // Format next_reset_at timestamp
            let nextResetText = '未知';
            if (account.next_reset_at) {
                const resetDate = new Date(account.next_reset_at * 1000);
                nextResetText = resetDate.toLocaleString('zh-CN');
            }

            // Cooldown info
            let cooldownHtml = '';
            if (account.cooldown && account.cooldown.active) {
                const cd = account.cooldown;
                const cdUntil = new Date(cd.cooldown_until * 1000).toLocaleTimeString('zh-CN');
                cooldownHtml = `
                <div class="data-field">
                    <div class="data-field-label">冷却状态</div>
                    <div class="data-field-value" style="color: #e74c3c; font-weight: 600;">
                        冷却中 - 剩余 ${cd.remaining_seconds}s (连续429: ${cd.consecutive_429}次, 解除时间: ${cdUntil})
                    </div>
                </div>`;
            }
            
            return `
                <div class="data-item" ${account.cooldown && account.cooldown.active ? 'style="border-left: 4px solid #e74c3c; opacity: 0.75;"' : ''}>
                    <div class="data-item-header">
                        <div class="data-item-title">账号 #${account.id} ${account.cooldown && account.cooldown.active ? '<span style="color:#e74c3c;font-size:0.8em;">[ 冷却中 ]</span>' : ''}</div>
                        <div class="data-item-actions">
                            <button class="btn-sm btn-primary" onclick="editAccount(${account.id})">编辑</button>
                            <button class="btn-sm btn-secondary" onclick="refreshAccountUsage(${account.id})">刷新用量</button>
                            <button class="btn-sm btn-danger" onclick="deleteAccount(${account.id})">删除</button>
                        </div>
                    </div>
                    <div class="data-item-body">
                        <div class="data-field">
                            <div class="data-field-label">类型</div>
                            <div class="data-field-value">${account.type}</div>
                        </div>
                        <div class="data-field">
                            <div class="data-field-label">优先级</div>
                            <div class="data-field-value">${account.priority}</div>
                        </div>
                        ${account.email ? `
                        <div class="data-field">
                            <div class="data-field-label">邮箱</div>
                            <div class="data-field-value">${account.email}</div>
                        </div>
                        ` : ''}
                        <div class="data-field">
                            <div class="data-field-label">用量</div>
                            <div class="data-field-value">
                                ${usageText}
                                ${account.limit > 0 ? `<div class="progress-bar"><div class="progress-fill" style="width: ${Math.min(usagePercent, 100)}%"></div></div>` : ''}
                            </div>
                        </div>
                        ${account.expires_at ? `
                        <div class="data-field">
                            <div class="data-field-label">Token 过期时间</div>
                            <div class="data-field-value">${account.expires_at}</div>
                        </div>
                        ` : ''}
                        ${account.next_reset_at ? `
                        <div class="data-field">
                            <div class="data-field-label">下次重置时间</div>
                            <div class="data-field-value">${nextResetText}</div>
                        </div>
                        ` : ''}
                        ${cooldownHtml}
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        container.innerHTML = `<div class="loading">加载失败: ${error.message}</div>`;
    }
}

function showAddAccountModal() {
    document.getElementById('accountModalTitle').textContent = '添加账号';
    document.getElementById('accountId').value = '';
    document.getElementById('accountType').value = 'kiro';
    document.getElementById('accountPriority').value = '0';
    document.getElementById('accountLimit').value = '0';
    document.getElementById('accountConfig').value = '';
    updateConfigPlaceholder(); // Update placeholder for default type
    document.getElementById('accountModal').classList.add('show');
}

function updateConfigPlaceholder() {
    const accountType = document.getElementById('accountType').value;
    const configTextarea = document.getElementById('accountConfig');
    
    if (accountType === 'glm') {
        configTextarea.placeholder = `直接粘贴 API Key，例如:
your_glm_api_key_here

或使用 JSON 格式:
{
  "api_key": "your_glm_api_key_here"
}`;
    } else {
        // Default Kiro format
        configTextarea.placeholder = `{
  "accessToken": "...",
  "refreshToken": "...",
  "clientId": "...",
  "clientSecret": "...",
  "region": "us-east-1",
  "profileArn": "..."
}`;
    }
}

function closeAccountModal() {
    document.getElementById('accountModal').classList.remove('show');
}

async function saveAccount(event) {
    event.preventDefault();
    
    const id = document.getElementById('accountId').value;
    const type = document.getElementById('accountType').value;
    const priority = parseInt(document.getElementById('accountPriority').value);
    const limit = parseFloat(document.getElementById('accountLimit').value);
    const configText = document.getElementById('accountConfig').value.trim();
    
    try {
        let config;
        
        // Smart config parsing: auto-wrap plain API key for GLM
        if (type === 'glm' && !configText.startsWith('{')) {
            // User entered plain API key, auto-wrap it
            config = { api_key: configText };
            console.log('Auto-wrapped plain API key into JSON format');
        } else {
            // Parse as JSON
            config = JSON.parse(configText);
        }
        
        const data = { type, priority, limit: limit, config };
        
        if (id) {
            await apiRequest(`/admin/accounts/${id}`, {
                method: 'PUT',
                body: JSON.stringify(data)
            });
            showNotification('账号更新成功');
        } else {
            await apiRequest('/admin/accounts', {
                method: 'POST',
                body: JSON.stringify(data)
            });
            showNotification('账号添加成功');
        }
        
        closeAccountModal();
        loadAccounts();
        loadDashboard();
    } catch (error) {
        showNotification('操作失败: ' + error.message, 'error');
    }
}

async function editAccount(id) {
    try {
        const accounts = await apiRequest('/admin/accounts');
        const account = accounts.find(a => a.id === id);
        
        if (!account) {
            showNotification('账号不存在', 'error');
            return;
        }
        
        document.getElementById('accountModalTitle').textContent = '编辑账号';
        document.getElementById('accountId').value = account.id;
        document.getElementById('accountType').value = account.type;
        document.getElementById('accountPriority').value = account.priority;
        document.getElementById('accountLimit').value = account.limit;
        document.getElementById('accountConfig').value = JSON.stringify(account.config, null, 2);
        document.getElementById('accountModal').classList.add('show');
    } catch (error) {
        showNotification('加载失败: ' + error.message, 'error');
    }
}

async function deleteAccount(id) {
    if (!confirm('确定要删除此账号吗？')) return;
    
    try {
        await apiRequest(`/admin/accounts/${id}`, { method: 'DELETE' });
        showNotification('账号删除成功');
        loadAccounts();
        loadDashboard();
    } catch (error) {
        showNotification('删除失败: ' + error.message, 'error');
    }
}

async function refreshAccountUsage(id) {
    try {
        await apiRequest(`/admin/accounts/${id}/refresh-usage`, { method: 'POST' });
        showNotification('用量刷新成功');
        loadAccounts();
        loadDashboard();
    } catch (error) {
        showNotification('刷新失败: ' + error.message, 'error');
    }
}

// ==================== Tokens ====================
async function loadTokens() {
    const container = document.getElementById('tokensList');
    container.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const tokens = await apiRequest('/admin/api-keys');
        
        if (tokens.length === 0) {
            container.innerHTML = '<div class="loading">暂无令牌</div>';
            return;
        }
        
        container.innerHTML = tokens.map(token => `
            <div class="data-item">
                <div class="data-item-header">
                    <div class="data-item-title">${token.name}</div>
                    <div class="data-item-actions">
                        <button class="btn-sm btn-primary" onclick='copyToken(\`${token.full_key}\`)'>复制</button>
                        <button class="btn-sm btn-danger" onclick="deleteToken(${token.id})">删除</button>
                    </div>
                </div>
                <div class="data-item-body">
                    <div class="data-field">
                        <div class="data-field-label">密钥</div>
                        <div class="data-field-value" style="font-family: monospace;">${token.key}</div>
                    </div>
                    <div class="data-field">
                        <div class="data-field-label">创建时间</div>
                        <div class="data-field-value">${new Date(token.created_at).toLocaleString('zh-CN')}</div>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="loading">加载失败: ${error.message}</div>`;
    }
}

function showGenerateTokenModal() {
    document.getElementById('tokenName').value = '';
    document.getElementById('tokenModal').classList.add('show');
}

function closeTokenModal() {
    document.getElementById('tokenModal').classList.remove('show');
}

async function generateToken(event) {
    event.preventDefault();
    
    const name = document.getElementById('tokenName').value;
    
    try {
        const result = await apiRequest('/admin/api-keys', {
            method: 'POST',
            body: JSON.stringify({ name })
        });
        
        showNotification('令牌生成成功');
        closeTokenModal();
        loadTokens();
        loadDashboard();
        
        // Show the generated key
        alert(`令牌已生成:\n\n${result.key}\n\n请妥善保管，此密钥不会再次显示！`);
    } catch (error) {
        showNotification('生成失败: ' + error.message, 'error');
    }
}

async function deleteToken(id) {
    if (!confirm('确定要删除此令牌吗？')) return;
    
    try {
        await apiRequest(`/admin/api-keys/${id}`, { method: 'DELETE' });
        showNotification('令牌删除成功');
        loadTokens();
        loadDashboard();
    } catch (error) {
        showNotification('删除失败: ' + error.message, 'error');
    }
}

// Copy token to clipboard
function copyToken(token) {
    // Use Clipboard API if available
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(token)
            .then(() => {
                showNotification('令牌已复制到剪贴板');
            })
            .catch(err => {
                console.error('Failed to copy:', err);
                fallbackCopyToken(token);
            });
    } else {
        fallbackCopyToken(token);
    }
}

// Fallback copy method for older browsers
function fallbackCopyToken(token) {
    const textarea = document.createElement('textarea');
    textarea.value = token;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
        document.execCommand('copy');
        showNotification('令牌已复制到剪贴板');
    } catch (err) {
        console.error('Failed to copy:', err);
        showNotification('复制失败，请手动复制', 'error');
    }
    
    document.body.removeChild(textarea);
}

// ==================== Models ====================
async function loadModels(providerType = null) {
    const container = document.getElementById('modelsList');
    container.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const url = providerType 
            ? `/admin/models?provider_type=${providerType}&enabled_only=false`
            : '/admin/models?enabled_only=false';
        const models = await apiRequest(url);
        
        if (models.length === 0) {
            container.innerHTML = '<div class="loading">暂无模型</div>';
            return;
        }
        
        // Display all models in a flat list
        let html = '';
        models.forEach(model => {
            const statusBadge = model.enabled 
                ? '<span style="background: #238636; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">启用</span>'
                : '<span style="background: #6e7681; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">禁用</span>';
            
            // Provider badge with different colors
            const providerColors = {
                'kiro': '#58a6ff',
                'glm': '#3fb950'
            };
            const providerColor = providerColors[model.provider_type] || '#8b949e';
            const providerBadge = `<span style="background: ${providerColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; text-transform: uppercase;">${model.provider_type}</span>`;
            
            html += `
                <div class="data-item">
                    <div class="data-item-header">
                        <div class="data-item-title">
                            ${providerBadge}
                            ${model.display_name || model.model_id}
                            ${statusBadge}
                        </div>
                        <div class="data-item-actions">
                            <button class="btn-sm ${model.enabled ? 'btn-secondary' : 'btn-primary'}" 
                                    onclick="toggleModelEnabled(${model.id}, ${!model.enabled})">
                                ${model.enabled ? '禁用' : '启用'}
                            </button>
                            <button class="btn-sm btn-primary" onclick="editModel(${model.id})">编辑</button>
                            <button class="btn-sm btn-danger" onclick="deleteModel(${model.id})">删除</button>
                        </div>
                    </div>
                    <div class="data-item-body">
                        <div class="data-field">
                            <div class="data-field-label">模型 ID</div>
                            <div class="data-field-value" style="font-family: monospace;">${model.model_id}</div>
                        </div>
                        ${model.display_name ? `
                        <div class="data-field">
                            <div class="data-field-label">显示名称</div>
                            <div class="data-field-value">${model.display_name}</div>
                        </div>
                        ` : ''}
                        <div class="data-field">
                            <div class="data-field-label">优先级</div>
                            <div class="data-field-value">${model.priority}</div>
                        </div>
                        <div class="data-field">
                            <div class="data-field-label">创建时间</div>
                            <div class="data-field-value">${new Date(model.created_at).toLocaleString('zh-CN')}</div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="loading">加载失败: ${error.message}</div>`;
    }
}

function showAddModelModal() {
    document.getElementById('modelModalTitle').textContent = '添加模型';
    document.getElementById('modelDbId').value = '';
    document.getElementById('modelProviderType').value = 'kiro';
    document.getElementById('modelProviderType').disabled = false;
    document.getElementById('modelId').value = '';
    document.getElementById('modelId').disabled = false;
    document.getElementById('modelDisplayName').value = '';
    document.getElementById('modelPriority').value = '0';
    document.getElementById('modelModal').classList.add('show');
}

function closeModelModal() {
    document.getElementById('modelModal').classList.remove('show');
}

async function saveModel(event) {
    event.preventDefault();
    
    const id = document.getElementById('modelDbId').value;
    const providerType = document.getElementById('modelProviderType').value;
    const modelId = document.getElementById('modelId').value;
    const displayName = document.getElementById('modelDisplayName').value || null;
    const priority = parseInt(document.getElementById('modelPriority').value);
    
    try {
        if (id) {
            // Update existing model (don't change enabled status)
            const data = { display_name: displayName, priority };
            await apiRequest(`/admin/models/${id}`, {
                method: 'PUT',
                body: JSON.stringify(data)
            });
            showNotification('模型更新成功');
        } else {
            // Create new model (default to enabled)
            const data = {
                provider_type: providerType,
                model_id: modelId,
                display_name: displayName,
                priority,
                enabled: true
            };
            await apiRequest('/admin/models', {
                method: 'POST',
                body: JSON.stringify(data)
            });
            showNotification('模型添加成功');
        }
        
        closeModelModal();
        const filterProvider = document.getElementById('filterProvider').value;
        loadModels(filterProvider || null);
    } catch (error) {
        showNotification('操作失败: ' + error.message, 'error');
    }
}

async function editModel(id) {
    try {
        const model = await apiRequest(`/admin/models/${id}`);
        
        document.getElementById('modelModalTitle').textContent = '编辑模型';
        document.getElementById('modelDbId').value = model.id;
        document.getElementById('modelProviderType').value = model.provider_type;
        document.getElementById('modelProviderType').disabled = true; // Can't change provider
        document.getElementById('modelId').value = model.model_id;
        document.getElementById('modelId').disabled = true; // Can't change model ID
        document.getElementById('modelDisplayName').value = model.display_name || '';
        document.getElementById('modelPriority').value = model.priority;
        document.getElementById('modelModal').classList.add('show');
    } catch (error) {
        showNotification('加载失败: ' + error.message, 'error');
    }
}

async function deleteModel(id) {
    if (!confirm('确定要删除此模型吗？')) return;
    
    try {
        await apiRequest(`/admin/models/${id}`, { method: 'DELETE' });
        showNotification('模型删除成功');
        const filterProvider = document.getElementById('filterProvider').value;
        loadModels(filterProvider || null);
    } catch (error) {
        showNotification('删除失败: ' + error.message, 'error');
    }
}

async function toggleModelEnabled(id, enabled) {
    try {
        await apiRequest(`/admin/models/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ enabled })
        });
        showNotification(enabled ? '模型已启用' : '模型已禁用');
        const filterProvider = document.getElementById('filterProvider').value;
        loadModels(filterProvider || null);
    } catch (error) {
        showNotification('操作失败: ' + error.message, 'error');
    }
}

async function syncModels() {
    if (!confirm('确定要同步默认模型吗？这将添加所有 provider 的默认模型到数据库。')) return;
    
    try {
        // Sync both providers
        const kiroResult = await apiRequest('/admin/models/sync/kiro', { method: 'POST' });
        const glmResult = await apiRequest('/admin/models/sync/glm', { method: 'POST' });
        
        const totalAdded = kiroResult.added.length + glmResult.added.length;
        
        if (totalAdded > 0) {
            showNotification(`同步成功！添加了 ${totalAdded} 个新模型`);
        } else {
            showNotification('同步完成，没有新模型需要添加');
        }
        
        const filterProvider = document.getElementById('filterProvider').value;
        loadModels(filterProvider || null);
    } catch (error) {
        showNotification('同步失败: ' + error.message, 'error');
    }
}

// ==================== Dashboard & Charts ====================
let hourlyChart = null;
let tokenChart = null;

async function loadDashboard() {
    try {
        const [accounts, tokens, stats] = await Promise.all([
            apiRequest('/admin/accounts'),
            apiRequest('/admin/api-keys'),
            apiRequest('/admin/stats/daily?days=30')  // Fixed 30 days
        ]);
        
        // Calculate total usage and total limit
        let totalUsage = 0;
        let totalLimit = 0;
        let hasUnlimited = false;
        
        accounts.forEach(acc => {
            totalUsage += acc.usage || 0;
            if (acc.limit === 0) {
                hasUnlimited = true;
            } else {
                totalLimit += acc.limit || 0;
            }
        });
        
        // Display statistics
        document.getElementById('stat-accounts').textContent = accounts.length;
        document.getElementById('stat-tokens').textContent = tokens.length;
        
        // Display "used/limit" or "used/limit+"
        const usageText = hasUnlimited 
            ? `${totalUsage.toFixed(2)} / ${totalLimit.toFixed(2)}+`
            : `${totalUsage.toFixed(2)} / ${totalLimit.toFixed(2)}`;
        document.getElementById('stat-usage').textContent = usageText;
        
        // Render charts (fixed 30 days)
        renderDailyChart(stats);
        renderTokenChart(stats);
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }
}

function renderDailyChart(stats) {
    const ctx = document.getElementById('hourlyChart');
    if (!ctx) return;
    
    // Destroy existing chart
    if (hourlyChart) {
        hourlyChart.destroy();
    }
    
    // Format date labels: MM/DD
    const labels = stats.map(s => {
        const date = new Date(s.day);
        return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' });
    });
    const data = stats.map(s => s.requests);
    
    hourlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '请求数',
                data: data,
                borderColor: '#58a6ff',
                backgroundColor: 'rgba(88, 166, 255, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    labels: { color: '#e6edf3' }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#8b949e' },
                    grid: { color: '#30363d' }
                },
                y: {
                    ticks: { color: '#8b949e' },
                    grid: { color: '#30363d' },
                    beginAtZero: true
                }
            }
        }
    });
}

function renderTokenChart(stats) {
    const ctx = document.getElementById('tokenChart');
    if (!ctx) return;
    
    // Destroy existing chart
    if (tokenChart) {
        tokenChart.destroy();
    }
    
    // Format date labels: MM/DD
    const labels = stats.map(s => {
        const date = new Date(s.day);
        return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' });
    });
    const inputData = stats.map(s => s.input_tokens);
    const outputData = stats.map(s => s.output_tokens);
    
    tokenChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Input Tokens',
                    data: inputData,
                    borderColor: '#58a6ff',
                    backgroundColor: 'rgba(88, 166, 255, 0.1)',
                    tension: 0.4,
                    fill: true
                },
                {
                    label: 'Output Tokens',
                    data: outputData,
                    borderColor: '#3fb950',
                    backgroundColor: 'rgba(63, 185, 80, 0.1)',
                    tension: 0.4,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    labels: { color: '#e6edf3' }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#8b949e' },
                    grid: { color: '#30363d' }
                },
                y: {
                    ticks: { color: '#8b949e' },
                    grid: { color: '#30363d' },
                    beginAtZero: true
                }
            }
        }
    });
}

// ==================== Request Logs ====================
