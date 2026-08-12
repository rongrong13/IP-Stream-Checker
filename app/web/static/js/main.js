// IP-Stream-Checker 前端JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // 标签页切换
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.getAttribute('data-tab');
            
            // 移除所有活动状态
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // 添加活动状态
            button.classList.add('active');
            document.getElementById(tabName).classList.add('active');
        });
    });
    
    // IP检测表单提交
    const ipCheckForm = document.getElementById('ip-check-form');
    if (ipCheckForm) {
        ipCheckForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const proxyUrl = document.getElementById('proxy-url').value;
            const source = document.getElementById('source').value;
            const timeout = document.getElementById('timeout').value;
            
            if (!proxyUrl) {
                alert('请输入代理URL');
                return;
            }
            
            const resultsDiv = document.getElementById('ip-results');
            resultsDiv.innerHTML = '<p>正在检测...</p>';
            
            try {
                const response = await fetch('/api/ip-check', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        url: proxyUrl,
                        source: source,
                        timeout: parseInt(timeout)
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    displayIpResults(result.data, resultsDiv);
                } else {
                    resultsDiv.innerHTML = `<p class="error">检测失败: ${result.message}</p>`;
                }
            } catch (error) {
                resultsDiv.innerHTML = `<p class="error">请求失败: ${error.message}</p>`;
            }
        });
    }
    
    // 流媒体测试表单提交
    const streamTestForm = document.getElementById('stream-test-form');
    if (streamTestForm) {
        streamTestForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const selectedProviders = Array.from(document.getElementById('providers').selectedOptions).map(option => option.value);
            const proxy = document.getElementById('proxy').value;
            
            if (selectedProviders.length === 0) {
                alert('请选择至少一个流媒体服务');
                return;
            }
            
            const resultsDiv = document.getElementById('stream-results');
            resultsDiv.innerHTML = '<p>正在测试...</p>';
            
            try {
                const response = await fetch('/api/stream-test', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        providers: selectedProviders,
                        proxy: proxy
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    displayStreamResults(result.data, resultsDiv);
                } else {
                    resultsDiv.innerHTML = `<p class="error">测试失败: ${result.message}</p>`;
                }
            } catch (error) {
                resultsDiv.innerHTML = `<p class="error">请求失败: ${error.message}</p>`;
            }
        });
    }
});

function displayIpResults(data, container) {
    let html = '<h3>IP检测结果</h3>';
    
    if (data.success) {
        html += `
            <div class="result-item success">
                <p><strong>IP地址:</strong> ${data.ip}</p>
                <p><strong>国家/地区:</strong> ${data.country}</p>
                <p><strong>城市:</strong> ${data.city}</p>
                <p><strong>ISP:</strong> ${data.isp}</p>
                <p><strong>类型:</strong> ${data.type}</p>
                <p><strong>响应时间:</strong> ${data.response_time.toFixed(2)}秒</p>
                <p><strong>检测时间:</strong> ${data.timestamp}</p>
            </div>
        `;
    } else {
        html += `
            <div class="result-item failure">
                <p><strong>检测失败:</strong> ${data.error}</p>
                <p><strong>响应时间:</strong> ${data.response_time.toFixed(2)}秒</p>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

function displayStreamResults(data, container) {
    let html = `<h3>流媒体测试结果</h3>`;
    html += `<p><strong>总测试数:</strong> ${data.total_providers}</p>`;
    html += `<p><strong>成功:</strong> ${data.successful_tests}</p>`;
    html += `<p><strong>失败:</strong> ${data.failed_tests}</p>`;
    html += `<p><strong>测试时间:</strong> ${data.timestamp}</p>`;
    
    data.details.forEach(result => {
        const statusClass = result.success ? 'success' : 'failure';
        const regionInfo = result.region !== 'unknown' ? ` (${result.region})` : '';
        
        html += `
            <div class="result-item ${statusClass}">
                <p><strong>${result.provider}</strong>${regionInfo}</p>
                <p><strong>状态:</strong> ${result.success ? '✅ 可用' : '❌ 不可用'}</p>
                <p><strong>消息:</strong> ${result.message}</p>
                <p><strong>响应时间:</strong> ${result.response_time.toFixed(2)}秒</p>
                <p><strong>测试时间:</strong> ${result.timestamp}</p>
            </div>
        `;
    });
    
    container.innerHTML = html;
}