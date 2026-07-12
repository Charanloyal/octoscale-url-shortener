let referrerChart = null;

function switchTab(tabName) {
    // Reset alerts
    hideAlert();
    
    // Toggle active tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Toggle active panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    
    if (tabName === 'shorten') {
        event.currentTarget.classList.add('active');
        document.getElementById('panel-shorten').classList.add('active');
    } else {
        event.currentTarget.classList.add('active');
        document.getElementById('panel-analytics').classList.add('active');
    }
}

function showAlert(message, type = 'error') {
    const errorAlert = document.getElementById('alert-error');
    const errorText = document.getElementById('alert-error-text');
    
    errorText.innerText = message;
    errorAlert.className = `alert ${type} active`;
}

function hideAlert() {
    const errorAlert = document.getElementById('alert-error');
    if (errorAlert) {
        errorAlert.classList.remove('active');
    }
}

async function handleShorten(event) {
    event.preventDefault();
    hideAlert();
    
    const originalUrl = document.getElementById('original_url').value;
    let customCode = document.getElementById('custom_code').value.trim();
    if (customCode === '') customCode = null;
    
    const submitBtn = document.getElementById('shorten-btn');
    const resultBox = document.getElementById('result-box');
    
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Generating...';
    
    try {
        const response = await fetch('/api/v1/shorten', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                original_url: originalUrl,
                custom_code: customCode
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            let errorMsg = data.detail || 'Failed to shorten URL';
            if (Array.isArray(errorMsg)) {
                errorMsg = errorMsg.map(err => err.msg).join(', ');
            }
            throw new Error(errorMsg);
        }
        
        const shortUrlLink = document.getElementById('short-url-link');
        shortUrlLink.href = data.short_url;
        shortUrlLink.innerText = data.short_url;
        
        resultBox.classList.add('active');
        
    } catch (err) {
        resultBox.classList.remove('active');
        showAlert(err.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
            Generate Short URL
        `;
    }
}

async function copyToClipboard() {
    const linkText = document.getElementById('short-url-link').innerText;
    const copyBtn = document.querySelector('.copy-btn');
    
    try {
        await navigator.clipboard.writeText(linkText);
        
        // Show success visual state
        copyBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
        `;
        copyBtn.style.borderColor = 'rgba(74, 222, 128, 0.4)';
        
        setTimeout(() => {
            copyBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            `;
            copyBtn.style.borderColor = 'rgba(255, 255, 255, 0.1)';
        }, 2000);
    } catch (err) {
        showAlert('Could not copy text to clipboard', 'error');
    }
}

async function handleAnalytics(event) {
    event.preventDefault();
    hideAlert();
    
    let searchCode = document.getElementById('search_code').value.trim();
    if (searchCode.includes('/')) {
        // extract the last part if they pasted a full short URL
        searchCode = searchCode.split('/').pop();
    }
    
    const submitBtn = document.getElementById('analytics-btn');
    const resultsContainer = document.getElementById('analytics-results');
    
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Fetching...';
    
    try {
        const response = await fetch(`/api/v1/analytics/${searchCode}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Could not fetch analytics for the specified short code');
        }
        
        // Update stats card UI
        document.getElementById('total-clicks').innerText = data.clicks;
        const creationDate = new Date(data.created_at).toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
        document.getElementById('creation-date').innerText = creationDate;
        
        const destLink = document.getElementById('dest-url');
        destLink.href = data.original_url;
        destLink.innerText = data.original_url;
        
        // Update click analytics table
        const tbody = document.getElementById('clicks-tbody');
        tbody.innerHTML = '';
        
        if (data.recent_clicks.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="3" style="text-align: center; color: var(--text-muted);">No clicks recorded yet.</td>
                </tr>
            `;
        } else {
            // Show up to 5 recent clicks
            const displayClicks = data.recent_clicks.slice(0, 5);
            displayClicks.forEach(click => {
                const dateStr = new Date(click.clicked_at).toLocaleString();
                const referrer = click.referrer || 'Direct / None';
                
                // Parse user agent minimally
                let browser = 'Unknown';
                const ua = click.user_agent || '';
                if (ua.includes('Chrome')) browser = 'Chrome';
                else if (ua.includes('Firefox')) browser = 'Firefox';
                else if (ua.includes('Safari') && !ua.includes('Chrome')) browser = 'Safari';
                else if (ua.includes('Edge')) browser = 'Edge';
                else if (ua.includes('Postman')) browser = 'Postman';
                else if (ua.includes('curl')) browser = 'curl';
                else if (ua.length > 0) browser = ua.split(' ')[0] || 'Browser';
                
                tbody.innerHTML += `
                    <tr>
                        <td>${dateStr}</td>
                        <td>${referrer}</td>
                        <td class="muted" title="${ua}">${browser}</td>
                    </tr>
                `;
            });
        }
        
        // Render Chart
        renderReferrerChart(data.recent_clicks);
        
        resultsContainer.style.display = 'block';
        
    } catch (err) {
        resultsContainer.style.display = 'none';
        showAlert(err.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
            Fetch Analytics
        `;
    }
}

function renderReferrerChart(clicks) {
    const referrers = {};
    clicks.forEach(click => {
        const ref = click.referrer ? new URL(click.referrer).hostname : 'Direct / None';
        referrers[ref] = (referrers[ref] || 0) + 1;
    });
    
    const labels = Object.keys(referrers);
    const counts = Object.values(referrers);
    
    if (referrerChart) {
        referrerChart.destroy();
    }
    
    const ctx = document.getElementById('referrer-chart').getContext('2d');
    
    if (labels.length === 0) {
        labels.push('No Traffic Yet');
        counts.push(1);
    }
    
    referrerChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: [
                    '#d4af37', // Metallic Gold
                    '#ebd080', // Soft Gold
                    '#aa7c11', // Dark Bronze/Gold
                    '#f3e5ab', // Pale Champagne
                    '#f0d575', // Amber Yellow
                    '#b8860b'  // Dark Goldenrod
                ],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#f3f4f6',
                        font: {
                            family: 'Outfit'
                        }
                    }
                }
            }
        }
    });
}
