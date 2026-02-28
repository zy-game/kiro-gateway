// Request Logs Page with Search and Pagination

let currentPage = 1;
let pageSize = 20;
let searchModel = '';
let searchStatus = '';
let totalLogs = 0;

// Format duration in milliseconds to human-readable string
function formatDuration(ms) {
    if (!ms && ms !== 0) return 'N/A';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
    return `${(ms / 60000).toFixed(2)}m`;
}

async function loadLogs(page = 1) {
    currentPage = page;
    const container = document.getElementById('logsList');
    const offset = (page - 1) * pageSize;
    
    // Build query params
    const params = new URLSearchParams({
        limit: pageSize,
        offset: offset
    });
    
    if (searchModel) params.append('search_model', searchModel);
    if (searchStatus) params.append('search_status', searchStatus);
    
    container.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const response = await apiRequest(`/admin/logs?${params.toString()}`);
        const { logs, total } = response;
        totalLogs = total;
        
        if (logs.length === 0) {
            container.innerHTML = '<div class="loading">暂无日志</div>';
            updatePagination(0);
            return;
        }
        
        // Render table
        container.innerHTML = `
            <table class="logs-table">
                <thead>
                    <tr>
                        <th>时间</th>
                        <th>模型</th>
                        <th>账号</th>
                        <th>令牌</th>
                        <th>输入</th>
                        <th>输出</th>
                        <th>耗时</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
                    ${logs.map(log => {
                        const statusColor = log.status === 'success' ? '#3fb950' : '#f85149';
                        const date = new Date(log.created_at);
                        const timeStr = date.toLocaleString('zh-CN', {
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                        
                        return `
                            <tr>
                                <td>${timeStr}</td>
                                <td><span class="model-badge">${log.model}</span></td>
                                <td>${log.account_name}</td>
                                <td>${log.api_key_name}</td>
                                <td>${(log.input_tokens || 0).toLocaleString()}</td>
                                <td>${(log.output_tokens || 0).toLocaleString()}</td>
                                <td>${formatDuration(log.duration_ms)}</td>
                                <td><span class="status-badge" style="background-color: ${statusColor};">${log.status}</span></td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
        
        updatePagination(total);
    } catch (error) {
        container.innerHTML = `<div class="loading">加载失败: ${error.message}</div>`;
    }
}

function updatePagination(total) {
    const paginationContainer = document.getElementById('logsPagination');
    if (!paginationContainer) return;
    
    const totalPages = Math.ceil(total / pageSize);
    
    if (totalPages <= 1) {
        paginationContainer.innerHTML = '';
        return;
    }
    
    let paginationHTML = '<div class="pagination">';
    
    // Previous button
    if (currentPage > 1) {
        paginationHTML += `<button class="btn-pagination" onclick="loadLogs(${currentPage - 1})">上一页</button>`;
    } else {
        paginationHTML += `<button class="btn-pagination" disabled>上一页</button>`;
    }
    
    // Page numbers
    paginationHTML += `<span class="pagination-info">第 ${currentPage} / ${totalPages} 页 (共 ${total} 条)</span>`;
    
    // Next button
    if (currentPage < totalPages) {
        paginationHTML += `<button class="btn-pagination" onclick="loadLogs(${currentPage + 1})">下一页</button>`;
    } else {
        paginationHTML += `<button class="btn-pagination" disabled>下一页</button>`;
    }
    
    paginationHTML += '</div>';
    paginationContainer.innerHTML = paginationHTML;
}

function searchLogs() {
    searchModel = document.getElementById('searchModel').value.trim();
    searchStatus = document.getElementById('searchStatus').value;
    loadLogs(1); // Reset to first page
}

function clearSearch() {
    document.getElementById('searchModel').value = '';
    document.getElementById('searchStatus').value = '';
    searchModel = '';
    searchStatus = '';
    loadLogs(1);
}
