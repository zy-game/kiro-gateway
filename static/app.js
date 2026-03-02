// Check login status on page load
window.addEventListener('DOMContentLoaded', () => {
    checkLoginStatus();
    initNavigation();
    initChartWheelListeners();
});

// Initialize wheel event listeners for charts
function initChartWheelListeners() {
    const chartContainer = document.getElementById('chartContainer');
    const tokenChartContainer = document.getElementById('tokenChartContainer');
    
    if (chartContainer) {
        chartContainer.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                adjustTimeRange(1);  // Scroll up: increase time range
            } else {
                adjustTimeRange(-1); // Scroll down: decrease time range
            }
        });
    }
    
    if (tokenChartContainer) {
        tokenChartContainer.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                adjustTimeRange(1);
            } else {
                adjustTimeRange(-1);
            }
        });
    }
}

// Check if user is logged in
async function checkLoginStatus() {
    try {
        const response = await fetch('/auth/me', {
            credentials: 'include'
        });
        if (!response.ok) {
            // Prevent redirect loop - only redirect once
            if (!sessionStorage.getItem('redirecting')) {
                sessionStorage.setItem('redirecting', 'true');
                window.location.href = '/login';
            }
            return;
        }
        // Clear redirect flag on successful login check
        sessionStorage.removeItem('redirecting');
        
        const data = await response.json();
        console.log('Logged in as:', data.username);
        
        // Add small delay to ensure cookies are fully propagated (especially in Docker)
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // Load dashboard data
        loadDashboard();
    } catch (error) {
        // Prevent redirect loop
        if (!sessionStorage.getItem('redirecting')) {
            sessionStorage.setItem('redirecting', 'true');
            window.location.href = '/login';
        }
    }
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
            
            return `
                <div class="data-item">
                    <div class="data-item-header">
                        <div class="data-item-title">账号 #${account.id}</div>
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
    document.getElementById('accountModal').classList.add('show');
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
    const configText = document.getElementById('accountConfig').value;
    
    try {
        const config = JSON.parse(configText);
        
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

// ==================== Dashboard & Charts ====================
let hourlyChart = null;
let tokenChart = null;

// Time range state management
let currentTimeRangeIndex = 4; // Default: 24 hours
const timeRanges = [
    { hours: 1, label: '最近 1 小时' },
    { hours: 3, label: '最近 3 小时' },
    { hours: 6, label: '最近 6 小时' },
    { hours: 12, label: '最近 12 小时' },
    { hours: 24, label: '最近 24 小时' },
    { hours: 48, label: '最近 48 小时' },
    { hours: 72, label: '最近 3 天' },
    { hours: 168, label: '最近 7 天' }
];

// Adjust time range
function adjustTimeRange(direction) {
    currentTimeRangeIndex += direction;
    
    // Limit range
    if (currentTimeRangeIndex < 0) currentTimeRangeIndex = 0;
    if (currentTimeRangeIndex >= timeRanges.length) {
        currentTimeRangeIndex = timeRanges.length - 1;
    }
    
    // Update display
    const range = timeRanges[currentTimeRangeIndex];
    document.getElementById('timeRangeDisplay').textContent = range.label;
    
    // Update button states
    document.getElementById('btnDecreaseRange').disabled = (currentTimeRangeIndex === 0);
    document.getElementById('btnIncreaseRange').disabled = (currentTimeRangeIndex === timeRanges.length - 1);
    
    // Update chart titles
    document.getElementById('chartTitle').textContent = `📈 请求统计 (${range.label})`;
    document.getElementById('tokenChartTitle').textContent = `🔢 Token 使用统计 (${range.label})`;
    
    // Reload dashboard data
    loadDashboard();
}

// Format chart label based on time range
function formatChartLabel(dateStr, hours) {
    const date = new Date(dateStr);
    if (hours <= 6) {
        // 1-6 hours: show HH:mm
        return date.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } else if (hours <= 24) {
        // 12-24 hours: show MM/DD HH:mm
        return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    } else {
        // 48+ hours: show MM/DD
        return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' });
    }
}

async function loadDashboard() {
    try {
        const range = timeRanges[currentTimeRangeIndex];
        const hours = range.hours;
        
        const [accounts, tokens, stats] = await Promise.all([
            apiRequest('/admin/accounts'),
            apiRequest('/admin/api-keys'),
            apiRequest(`/admin/stats/hourly?hours=${hours}`)
        ]);
        
        const totalUsage = accounts.reduce((sum, acc) => sum + (acc.usage || 0), 0);
        
        document.getElementById('stat-accounts').textContent = accounts.length;
        document.getElementById('stat-tokens').textContent = tokens.length;
        document.getElementById('stat-usage').textContent = totalUsage.toFixed(2);
        
        // Render charts with current time range
        renderDailyChart(stats, hours);
        renderTokenChart(stats, hours);
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }
}

function renderDailyChart(stats, hours) {
    const ctx = document.getElementById('hourlyChart');
    if (!ctx) return;
    
    // Destroy existing chart
    if (hourlyChart) {
        hourlyChart.destroy();
    }
    
    const labels = stats.map(s => formatChartLabel(s.hour, hours));
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

function renderTokenChart(stats, hours) {
    const ctx = document.getElementById('tokenChart');
    if (!ctx) return;
    
    // Destroy existing chart
    if (tokenChart) {
        tokenChart.destroy();
    }
    
    const labels = stats.map(s => formatChartLabel(s.hour, hours));
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
